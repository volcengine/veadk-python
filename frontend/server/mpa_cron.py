"""Read-only task access for MPA Runtimes with JWT verification disabled."""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request


async def list_tasks(
    endpoint: str,
    authorization: str,
    offset: int,
    query: str,
) -> dict[str, Any]:
    headers = {"Authorization": authorization}
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.get(
                endpoint.rstrip("/") + "/api/v1/esa-cron-tasks",
                headers=headers,
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
    except (httpx.HTTPError, ValueError, TypeError) as error:
        raise HTTPException(502, "mpa_upstream_failed") from error


def mount_routes(
    app: FastAPI,
    *,
    authorize: Callable,
    connection: Callable,
    authorization: Callable,
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
        endpoint, apikey, auth_type, _ = await asyncio.to_thread(
            connection, runtime_id, region, runtime
        )
        return await list_tasks(
            endpoint,
            authorization(request, apikey, auth_type),
            offset,
            query,
        )
