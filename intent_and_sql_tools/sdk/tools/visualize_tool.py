from sdk.registry import ToolRegistry


@ToolRegistry.register(intent="plot_chart", tool_name="visualize_data")
def visualize_data(envelope: dict) -> dict:
    payload = envelope.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {"value": payload}
    summary = {
        "metric": payload.get("metric") or payload.get("metrics"),
        "time_range": payload.get("time_range") or payload.get("timeRange"),
        "dimension": payload.get("dimension") or payload.get("dimensions"),
        "chart_type": payload.get("chart_type") or payload.get("chartType"),
        "raw_payload": payload,
    }
    return {
        "status": "mock",
        "message": "Will generate chart",
        "summary": summary,
        "code": None,
    }
