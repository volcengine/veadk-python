# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A safe arithmetic expression evaluator for model use.

Parses the expression with :mod:`ast` and walks only the small set of numeric
nodes it allows. Names, attribute access, subscripts, comprehensions, lambdas,
strings, booleans, and complex numbers are all rejected, so the tool cannot be
used to execute arbitrary Python.
"""

import ast
import math
import operator

_MAX_EXPRESSION_LENGTH = 1000
_MAX_EXPONENT = 100
_MAX_ABS_RESULT = 1e100
_MAX_PRECISION = 15

_CONSTANTS = {"pi": math.pi, "e": math.e}
_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "floor": math.floor,
    "ceil": math.ceil,
}
_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


class _EvalError(Exception):
    """Internal evaluation error surfaced as ``{"error": ...}``."""


def _check_number(value: object) -> None:
    """Reject non-real, non-finite, or excessively large intermediate values."""
    if type(value) not in (int, float):
        raise _EvalError("result is not a finite real number")
    if isinstance(value, float) and not math.isfinite(value):
        raise _EvalError("result is not a finite real number")
    if abs(value) > _MAX_ABS_RESULT:
        raise _EvalError("result exceeds the allowed magnitude")


def _apply_call(node: ast.Call) -> int | float:
    if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
        raise _EvalError("unsupported function")
    if node.keywords:
        raise _EvalError("keyword arguments are not supported")
    args = [_evaluate(argument) for argument in node.args]
    try:
        result = _FUNCTIONS[node.func.id](*args)
    except ZeroDivisionError as exc:
        raise _EvalError("division by zero") from exc
    except OverflowError as exc:
        raise _EvalError("numeric overflow") from exc
    except (TypeError, ValueError) as exc:
        raise _EvalError("math domain error") from exc
    _check_number(result)
    return result


def _apply_binary(node: ast.BinOp) -> int | float:
    operation = _BINARY_OPERATORS.get(type(node.op))
    if operation is None:
        raise _EvalError("unsupported binary operator")
    left = _evaluate(node.left)
    right = _evaluate(node.right)
    if isinstance(node.op, ast.Pow) and (
        type(right) not in (int, float) or abs(right) > _MAX_EXPONENT
    ):
        raise _EvalError(
            f"exponent must be a number with absolute value <= {_MAX_EXPONENT}"
        )
    try:
        result = operation(left, right)
    except ZeroDivisionError as exc:
        raise _EvalError("division by zero") from exc
    except OverflowError as exc:
        raise _EvalError("numeric overflow") from exc
    _check_number(result)
    return result


def _evaluate(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant):
        if type(node.value) not in (int, float):
            raise _EvalError("unsupported constant")
        _check_number(node.value)
        return node.value
    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise _EvalError(f"unknown name: {node.id}")
    if isinstance(node, ast.UnaryOp):
        operand = _evaluate(node.operand)
        if isinstance(node.op, ast.UAdd):
            result = +operand
        elif isinstance(node.op, ast.USub):
            result = -operand
        else:
            raise _EvalError("unsupported unary operator")
        _check_number(result)
        return result
    if isinstance(node, ast.BinOp):
        return _apply_binary(node)
    if isinstance(node, ast.Call):
        return _apply_call(node)
    raise _EvalError(f"unsupported expression element: {type(node).__name__}")


def calculator(expression: str, precision: int = 10) -> dict:
    """Evaluate a numeric arithmetic expression safely.

    Use this tool for arithmetic, percentages, powers, roots, logarithms, and
    basic trigonometry. Named constants ``pi`` and ``e`` and the functions
    ``abs``, ``round``, ``min``, ``max``, ``sqrt``, ``log``, ``log10``,
    ``exp``, ``sin``, ``cos``, ``tan``, ``floor``, and ``ceil`` are supported.

    Args:
        expression: The arithmetic expression, for example ``"(1 + 2) * 3"``.
        precision: Decimal places for a floating-point result (0-15).

    Returns:
        A dict with ``expression`` and ``result``. On invalid input, a dict with
        an ``error`` key.
    """
    if not isinstance(expression, str) or not expression.strip():
        return {"error": "expression must be a non-empty string"}
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        return {
            "error": f"expression is too long (max {_MAX_EXPRESSION_LENGTH} characters)"
        }
    if type(precision) is not int or not 0 <= precision <= _MAX_PRECISION:
        return {"error": f"precision must be an integer between 0 and {_MAX_PRECISION}"}
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError, TypeError, RecursionError):
        return {"error": "invalid expression"}

    try:
        result = _evaluate(tree)
    except _EvalError as exc:
        return {"error": str(exc)}
    except RecursionError:
        return {"error": "expression is too complex"}
    except Exception:  # noqa: BLE001 - tool results must not raise
        return {"error": "invalid expression"}

    if type(result) is int:
        return {"expression": expression, "result": result}
    rounded = round(float(result), precision)
    return {"expression": expression, "result": rounded}
