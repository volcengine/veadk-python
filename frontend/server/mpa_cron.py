"""User-scoped task management through authorized MPA Runtime connections."""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Path, Query, Request


async def task_request(
    endpoint: str,
    authorization: str,
    user_id: str,
    method: str,
    suffix: str = "",
    params: dict | None = None,
    payload: dict | None = None,
) -> dict[str, Any]:
    if not user_id:
        raise HTTPException(401, "mpa_identity_required")
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.request(
                method,
                endpoint.rstrip("/") + "/api/v1/esa-cron-tasks" + suffix,
                headers={"Authorization": authorization, "x-user-id": user_id},
                params=params,
                json=payload,
            )
            if not response.is_success:
                raise HTTPException(
                    response.status_code if response.is_error else 502,
                    "mpa_tasks_failed",
                )
            data = response.json()
            if not isinstance(data, dict):
                raise TypeError("Invalid task response")
            return data
    except (httpx.HTTPError, ValueError, TypeError) as error:
        raise HTTPException(502, "mpa_upstream_failed") from error


def mount_routes(
    app: FastAPI,
    *,
    authorize: Callable,
    connection: Callable,
    authorization: Callable,
    region_for: Callable,
    user_for: Callable,
) -> None:
    async def send(
        request, runtime_id, region, method, suffix="", params=None, payload=None
    ):
        region = region_for(region)
        runtime = await asyncio.to_thread(authorize, request, runtime_id, region)
        user_id = user_for(request)
        endpoint, apikey, auth_type, _ = await asyncio.to_thread(
            connection, runtime_id, region, runtime
        )
        return await task_request(
            endpoint,
            authorization(request, apikey, auth_type),
            user_id,
            method,
            suffix,
            params,
            payload,
        )

    async def body(request: Request, allowed: set[str]):
        raw = await request.body()
        if len(raw) > 32768:
            raise HTTPException(413, "mpa_payload_too_large")
        try:
            payload = await request.json()
        except ValueError as error:
            raise HTTPException(422, "mpa_invalid_payload") from error
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise HTTPException(422, "mpa_invalid_payload")
        return payload

    fields = {
        "name",
        "agentId",
        "prompt",
        "enabled",
        "schedule",
        "delivery",
        "jitterSeconds",
        "timeoutSeconds",
    }

    @app.get("/web/mpa-cron/{runtime_id}")
    async def get_tasks(
        request: Request,
        runtime_id: str,
        region: str,
        offset: int = Query(0, ge=0),
        query: str = Query("", max_length=200),
    ):
        return await send(
            request,
            runtime_id,
            region,
            "GET",
            params={
                "includeDisabled": "true",
                "limit": 20,
                "offset": offset,
                "query": query,
            },
        )

    @app.post("/web/mpa-cron/{runtime_id}")
    async def create_task(request: Request, runtime_id: str, region: str):
        return await send(
            request,
            runtime_id,
            region,
            "POST",
            payload=await body(request, fields | {"clientToken"}),
        )

    @app.post("/web/mpa-cron/{runtime_id}/{task_id}")
    async def update_task(
        request: Request,
        runtime_id: str,
        region: str,
        task_id: str = Path(pattern=r"^[A-Za-z0-9_-]+$"),
    ):
        return await send(
            request,
            runtime_id,
            region,
            "POST",
            "/" + task_id,
            payload=await body(request, fields | {"expectedVersion"}),
        )

    @app.delete("/web/mpa-cron/{runtime_id}/{task_id}")
    async def delete_task(
        request: Request,
        runtime_id: str,
        region: str,
        task_id: str = Path(pattern=r"^[A-Za-z0-9_-]+$"),
    ):
        return await send(request, runtime_id, region, "DELETE", "/" + task_id)

    @app.post("/web/mpa-cron/{runtime_id}/{task_id}/run")
    async def run_task(
        request: Request,
        runtime_id: str,
        region: str,
        task_id: str = Path(pattern=r"^[A-Za-z0-9_-]+$"),
    ):
        return await send(
            request,
            runtime_id,
            region,
            "POST",
            "/" + task_id + "/run",
            payload=await body(request, {"clientToken", "mode"}),
        )

    @app.get("/web/mpa-cron/{runtime_id}/{task_id}/runs")
    async def get_runs(
        request: Request,
        runtime_id: str,
        region: str,
        task_id: str = Path(pattern=r"^[A-Za-z0-9_-]+$"),
        offset: int = Query(0, ge=0),
    ):
        return await send(
            request,
            runtime_id,
            region,
            "GET",
            "/" + task_id + "/runs",
            params={"offset": offset, "limit": 20},
        )
