from sdk.compiler import ContextCompiler
from sdk.registry import ToolRegistry
from sdk.tools.runtime import get_hands


@ToolRegistry.register(intent="query_metric", tool_name="execute_sql")
def execute_sql(envelope: dict) -> str:
    compiler = ContextCompiler()
    rich_prompt = compiler.compile(envelope)
    hands = get_hands()
    sql = hands.generate_sql(question=rich_prompt)
    df = hands.run_sql(sql)
    if hasattr(df, "to_markdown"):
        return df.to_markdown()
    return str(df)
