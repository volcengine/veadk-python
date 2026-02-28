from sdk.registry import ToolRegistry


@ToolRegistry.register(intent="screening", tool_name="execute_api")
def execute_api(envelope: dict) -> dict:
    payload = envelope.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {"value": payload}
    normalized = {
        "universe": payload.get("universe"),
        "factors": payload.get("factors") or payload.get("rules") or [],
        "sort_by": payload.get("sort_by") or payload.get("sortBy"),
        "limit": payload.get("limit"),
        "raw_payload": payload,
    }
    return {
        "status": "mock",
        "message": "Screening request normalized",
        "request": normalized,
    }
