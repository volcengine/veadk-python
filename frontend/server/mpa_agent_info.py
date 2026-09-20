"""Read-only, allowlisted metadata for the Studio MPA information rail."""

from typing import Any

import httpx


def _bound_spaces(card: dict[str, Any] | None, region: str) -> dict[str, Any]:
    unavailable = {"skillSpaces": [], "skillSpacesStatus": "unsupported"}
    capabilities = (card or {}).get("capabilities")
    if not isinstance(capabilities, dict):
        return unavailable
    extensions = capabilities.get("extensions")
    if not isinstance(extensions, list):
        return unavailable
    topology = next(
        (
            item.get("params")
            for item in extensions
            if isinstance(item, dict)
            and item.get("uri") == "urn:veadk:mpa:resource-topology:v1"
        ),
        None,
    )
    if not isinstance(topology, dict):
        return unavailable
    nodes, edges = topology.get("nodes"), topology.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return unavailable
    agents = {
        node.get("id")
        for node in nodes
        if isinstance(node, dict)
        and node.get("kind") == "agent"
        and isinstance(node.get("id"), str)
    }
    targets = {
        edge.get("target")
        for edge in edges
        if isinstance(edge, dict)
        and isinstance(edge.get("source"), str)
        and edge.get("source") in agents
        and edge.get("relation") == "mounts"
        and isinstance(edge.get("target"), str)
    }
    ids = dict.fromkeys(
        node["resourceId"].strip()
        for node in nodes
        if isinstance(node, dict)
        and isinstance(node.get("id"), str)
        and node.get("id") in targets
        and node.get("kind") == "skill-space"
        and node.get("status") == "configured"
        and isinstance(node.get("resourceId"), str)
        and node["resourceId"].strip()
    )
    return {
        "skillSpacesStatus": "ready",
        "skillSpaces": [{"id": space_id, "region": region} for space_id in ids],
    }


async def load_mpa_agent_info(
    endpoint: str,
    headers: dict[str, str],
    card: dict[str, Any] | None,
    region: str,
    *,
    runtime_api_key: str = "",
) -> dict[str, Any]:
    """Keep document failures independent from bound-space discovery."""
    result: dict[str, Any] = {
        "agentsMd": None,
        "agentsMdStatus": "error",
        **_bound_spaces(card, region),
    }
    legacy_fallback = False
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=4)) as client:
            safe_headers = {
                key: value
                for key, value in headers.items()
                if key.lower() != "x-mpa-studio-key"
            }
            key = runtime_api_key.strip()
            if key.lower().startswith("bearer "):
                key = key[7:].strip()
            if key:
                response = await client.get(
                    f"{endpoint.rstrip('/')}/api/v1/studio/agent-info",
                    headers={**safe_headers, "X-MPA-Studio-Key": key},
                )
                if response.status_code in (404, 405):
                    legacy_fallback = True
                    response = await client.get(
                        f"{endpoint.rstrip('/')}/api/v1/agents", headers=safe_headers
                    )
            else:
                response = await client.get(
                    f"{endpoint.rstrip('/')}/api/v1/agents", headers=safe_headers
                )
        if response.status_code in (401, 403):
            result["agentsMdStatus"] = "unsupported" if legacy_fallback else "forbidden"
        elif response.status_code in (404, 405, 501):
            result["agentsMdStatus"] = "unsupported"
        elif response.is_success:
            payload = response.json()
            if not isinstance(payload, dict) or "agentsMd" not in payload:
                return result
            document = payload["agentsMd"]
            if document is not None and not isinstance(document, str):
                return result
            result.update(agentsMd=document, agentsMdStatus="ready")
            for key in ("name", "description", "model"):
                if isinstance(payload.get(key), str):
                    result[key] = payload[key]
    except (httpx.HTTPError, ValueError):
        # Never forward arbitrary upstream bodies or transport credentials.
        pass
    return result
