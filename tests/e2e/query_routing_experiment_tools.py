"""Deterministic tools shared by both arms of the live cost experiment."""

import ast
import hashlib
from decimal import Decimal

from google.adk.tools import ToolContext


def arithmetic(expression: str) -> dict:
    """Evaluate a numeric expression with parentheses and +, -, *, /, or **.

    Use this tool for exact arithmetic. It does not execute Python code.
    """
    if len(expression) > 500:
        return {"error": "expression_too_long"}

    def evaluate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return Decimal(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow) and abs(right) <= 12:
                return left**right
        raise ValueError("unsupported arithmetic")

    try:
        result = evaluate(ast.parse(expression, mode="eval").body)
        return {"result": str(result)}
    except (ValueError, SyntaxError, ArithmeticError, RecursionError):
        return {"error": "invalid_expression", "retryable": True}


def workflow_step(workflow_id: str, token: str, tool_context: ToolContext) -> dict:
    """Advance a synthetic workflow. Start with token 'start'; reuse each returned
    next_token until done is true. Retry the same token for retryable errors.
    Independent workflows can advance in parallel. Never invent result tokens.
    """
    state = tool_context.state
    length = state.get("workflow_length", 1)
    count = state.get(f"step:{workflow_id}", 0)
    expected = (
        "start"
        if count == 0
        else hashlib.sha256(f"{workflow_id}:{count}".encode()).hexdigest()[:12]
    )
    if token != expected:
        return {"error": "invalid_token", "retryable": True}
    if state.get("inject_retry") and not state.get(f"retried:{workflow_id}"):
        state[f"retried:{workflow_id}"] = True
        return {"error": "temporarily_unavailable", "retryable": True}
    count += 1
    state[f"step:{workflow_id}"] = count
    result = {"done": count >= length, "step": count}
    if result["done"]:
        result["result"] = f"DONE-{workflow_id}"
        from query_routing_http_agent import audit
        from query_routing_usage import REQUEST_SCOPE

        audit(
            kind="workflow_completed",
            **REQUEST_SCOPE.get(),
            workflow_id=workflow_id,
            step=count,
        )
    else:
        result["next_token"] = hashlib.sha256(
            f"{workflow_id}:{count}".encode()
        ).hexdigest()[:12]
    return result


def aggregate_table(column: str, tool_context: ToolContext) -> dict:
    """Sum a named integer column in the CSV table in the latest user message.
    Supply only the column name; the tool reads the original table without
    requiring the model to copy its rows.
    """
    import csv
    import io

    text = "\n".join(
        p.text or "" for p in tool_context._invocation_context.user_content.parts or []
    )
    if "```csv\n" not in text:
        return {"error": "missing_csv_block"}
    table = text.split("```csv\n", 1)[1].split("```", 1)[0]
    try:
        return {
            "total": sum(int(row[column]) for row in csv.DictReader(io.StringIO(table)))
        }
    except (KeyError, ValueError):
        return {"error": "invalid_column_or_value"}
