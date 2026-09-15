"""Studio administrator boundary for MPA channel management."""

from urllib.parse import unquote

from fastapi import HTTPException


def channel_management_headers(
    path: str, *, is_admin: bool, api_key: str | None
) -> dict[str, str]:
    # Reject path aliases before forwarding: authorization and the upstream
    # must interpret the same route, including encoded and dot segments.
    if (
        unquote(path) != path
        or "//" in path
        or any(part in {".", ".."} for part in path.split("/"))
    ):
        raise HTTPException(400, "Noncanonical proxy path")
    route = path.strip("/")
    if route != "api/v1/channels" and not route.startswith("api/v1/channels/"):
        return {}
    if not is_admin:
        raise HTTPException(403, "Channel management requires a Studio administrator")
    if route == "api/v1/channels/events" or route.startswith("api/v1/channels/events/"):
        raise HTTPException(403, "Gateway ingress cannot be proxied through Studio")
    key = (api_key or "").strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    if not key:
        raise HTTPException(503, "Channel management requires a Runtime API key")
    return {"X-MPA-Channel-Key": key}
