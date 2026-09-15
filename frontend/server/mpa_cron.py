"""Read-only MPA tasks with TOP-issued credentials kept inside Studio."""

import asyncio
import json
import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Query, Request

from veadk.a2a.registry_client import _volc_sign_v4


def user_uid(request: Request, app: FastAPI, gateway: bool, claims: Callable) -> str:
    handler = getattr(app.state, "oauth2_handler", None)
    if gateway:
        identity = claims(request.headers.get("authorization")) or {}
    elif handler is not None:
        session = handler.get_session_from_request(request)
        identity = session.user_info if session and session.user_info else {}
    else:
        # Local Studio uses an operator-configured identity, never a browser header.
        identity = {"user_pool_user_uid": os.getenv("VEADK_STUDIO_MPA_USER_UID", "")}
    uid = identity.get("user_pool_user_uid")
    if not isinstance(uid, str) or not uid.strip():
        raise HTTPException(409, "mpa_identity_required")
    return uid.strip()


def endpoint_origin(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(502, "mpa_invalid_credentials")
    value = value.strip().strip("`")
    parsed = urlsplit(value if "://" in value else "https://" + value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.netloc != parsed.hostname
        or parsed.path.rstrip("/") not in ("", "/api/v1")
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(502, "mpa_invalid_credentials")
    return "https://" + parsed.hostname


async def list_tasks(
    runtime: Any,
    endpoint: str,
    uid: str,
    region: str,
    credentials: tuple[str, str, str | None],
    offset: int,
    query: str,
) -> dict[str, Any]:
    env = {item.key: item.value for item in (runtime.envs or [])}
    instance = env.get("MPA_AGENT_ID", "")
    space = env.get("MPA_SPACE_ID") or env.get("CLAW_SPACE_ID")
    service = env.get("ARKCLAW_TOP_SERVICE", "arkclaw")
    if (
        not instance
        or not space
        or service not in ("arkclaw", "arkclaw_stg", "arkclaw_ppe")
    ):
        raise HTTPException(409, "mpa_runtime_config_required")
    payload = {"id": instance, "SpaceId": space, "UserPoolUserUid": uid}
    if str(env.get("MPA_IS_DEBUG_RUNTIME", "")).lower() == "true":
        payload["type"] = "Debug"
    body = json.dumps(payload)
    params = {"Action": "GetMpaInstanceToken", "Version": "2026-03-01"}
    ak, sk, token = credentials
    headers = {"Host": "open.volcengineapi.com", "Content-Type": "application/json"}
    if token:
        headers["X-Security-Token"] = token
    headers.update(
        _volc_sign_v4(ak, sk, service, region, "POST", "/", params, headers, body)
    )
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            result = await client.post(
                "https://open.volcengineapi.com/",
                params=params,
                headers=headers,
                content=body,
            )
            data = result.json()
            if result.is_error or data.get("ResponseMetadata", {}).get("Error"):
                raise HTTPException(502, "mpa_top_failed")
            data = data.get("Result", {})
            target = endpoint_origin(
                data.get("PublicEndpoint") or data.get("public_endpoint")
            )
            if target != endpoint_origin(endpoint):
                raise HTTPException(409, "mpa_runtime_mismatch")
            jwt = data.get("JwtToken") or data.get("jwt_token") or data.get("Token")
            api_key = data.get("ApiKey") or data.get("api_key") or data.get("apikey")
            if not all(
                isinstance(value, str) and value.strip() for value in (jwt, api_key)
            ):
                raise HTTPException(502, "mpa_invalid_credentials")
            response = await client.get(
                target + "/api/v1/esa-cron-tasks",
                headers={"Authorization": f"Bearer {api_key}", "X-Jwt-Token": jwt},
                params={
                    "includeDisabled": "true",
                    "limit": 20,
                    "offset": offset,
                    "query": query,
                },
            )
            if response.is_error:
                raise HTTPException(response.status_code, "mpa_tasks_failed")
            tasks = response.json()
            if not isinstance(tasks, dict):
                raise TypeError("Invalid task page")
            return tasks
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as error:
        # Never include response bodies or transport exception messages in errors.
        raise HTTPException(502, "mpa_upstream_failed") from error


def mount_routes(
    app: FastAPI,
    *,
    authorize: Callable,
    connection: Callable,
    identity: Callable,
    credentials: Callable,
    region_for: Callable,
) -> None:
    @app.get("/web/mpa-cron/{runtime_id}")
    async def get_tasks(
        request: Request,
        runtime_id: str,
        region: str,
        offset: int = Query(0, ge=0),
        query: str = Query("", max_length=200),
    ):
        region = region_for(region)
        runtime = await asyncio.to_thread(authorize, request, runtime_id, region)
        uid = identity(request)
        endpoint, *_ = await asyncio.to_thread(connection, runtime_id, region, runtime)
        return await list_tasks(
            runtime, endpoint, uid, region, credentials(), offset, query
        )
