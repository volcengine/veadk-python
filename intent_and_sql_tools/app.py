from veadk import Agent

from sdk.tools import execute_api, execute_sql, identify_intent, visualize_data


def create_agent() -> Agent:
    return Agent(
        name="HeQu_Data_Agent_v6_13",
        description="HeQu Data Agent",
        instruction=(
            "ALWAYS call identify_intent first. "
            "Read `next_tool` from the JSON output. "
            "Pass the ENTIRE JSON envelope to the next tool without modification."
        ),
        tools=[identify_intent, execute_sql, execute_api, visualize_data],
    )

TOOLS = {
    "execute_sql": execute_sql,
    "execute_api": execute_api,
    "visualize_data": visualize_data,
}


def run_query(query: str):
    envelope = identify_intent(query)
    tool = envelope.get("next_tool") or "unknown_tool"
    print(f"[Chain] identify_intent -> {tool}")
    func = TOOLS.get(tool)
    if func is None:
        return envelope
    return func(envelope)


if __name__ == "__main__":
    print(run_query("查一下土豪流失"))
    print(run_query("选出MA多头的票"))
    print(run_query("画一张最近流水趋势图"))
