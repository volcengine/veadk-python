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

"""Register existing services in AgentKit A2A Center using Studio cloud identity."""

import asyncio
import json
import logging
import re
from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException, Request

logger = logging.getLogger(__name__)

MAX_BODY = 128 * 1024


def _identifier(value: object, prefix: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        prefix + r"-[A-Za-z0-9_-]{1,100}", value
    ):
        raise ValueError("Invalid identifier")
    return value


def _card_url(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 4096
        or any(c.isspace() for c in value)
    ):
        raise ValueError("Invalid URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("Invalid URL")
    # Accessing port also validates malformed or out-of-range ports.
    _ = parsed.port
    return value


def registration_payload(body: object) -> tuple[str, dict]:
    """Parse the public source union, rejecting irrelevant or unrecognized fields."""
    if not isinstance(body, dict):
        raise ValueError("Invalid body")
    target = _identifier(body.get("targetRuntimeId"), "r")
    project = body.get("projectName", "default")
    if (
        not isinstance(project, str)
        or not project.strip()
        or len(project) > 128
        or any(ord(c) < 32 for c in project)
    ):
        raise ValueError("Invalid project")
    payload = {
        "A2aSpaceId": _identifier(body.get("spaceId"), "as"),
        "Source": body.get("source"),
        "SetDefaultVersion": True,
        "ProjectName": project,
    }
    common = {"targetRuntimeId", "spaceId", "source", "projectName"}
    if body.get("source") == "Runtime":
        allowed = common | {"runtimeId", "networkType"}
        if body.get("networkType") not in {"public", "private"}:
            raise ValueError("Invalid network type")
        payload["RuntimeConfig"] = {
            "RuntimeId": _identifier(body.get("runtimeId"), "r"),
            "NetworkType": body["networkType"],
        }
    elif body.get("source") == "Standard":
        method = body.get("importType")
        if method == "url":
            allowed = common | {"importType", "cardUrl"}
            payload["StandardConfig"] = {
                "ImportType": "url",
                "AgentCardUrl": _card_url(body.get("cardUrl")),
            }
        elif method == "json":
            allowed = common | {"importType", "agentCard"}
            card = body.get("agentCard")
            if not isinstance(card, dict) or any(
                not isinstance(card.get(key), str) or not card[key].strip()
                for key in ("name", "url", "version")
            ):
                raise ValueError("Invalid Card")
            _card_url(card["url"])
            payload["AgentCard"] = json.dumps(card, ensure_ascii=False, allow_nan=False)
            payload["StandardConfig"] = {"ImportType": "json"}
        else:
            raise ValueError("Invalid import type")
    else:
        raise ValueError("Invalid source")
    if set(body) - allowed:
        raise ValueError("Unexpected fields")
    return target, payload


class A2ACenterCloudError(RuntimeError):
    """A safe provider error with no raw response or credential-bearing message."""

    def __init__(self, status: int, reason: str):
        self.status = status
        self.reason = reason
        super().__init__(reason)


def cloud_error(status: int, code: str = "", message: str = "") -> A2ACenterCloudError:
    if message.strip().lower().startswith("runtimeid already exists"):
        return A2ACenterCloudError(409, "runtime_already_registered")
    if status >= 500:
        return A2ACenterCloudError(502, "outcome_unknown")
    if status in {401, 403} or code.startswith("AccessDenied"):
        return A2ACenterCloudError(403, "forbidden")
    if status == 404 or code.startswith("ResourceNotFound"):
        return A2ACenterCloudError(404, "not_found")
    if status in {400, 422} or code.startswith("InvalidParameter"):
        return A2ACenterCloudError(422, "invalid_parameter")
    if status == 409 or code.startswith(
        ("AlreadyExists", "ResourceAlreadyExists", "ResourceInUse")
    ):
        return A2ACenterCloudError(409, "conflict")
    if status == 429:
        return A2ACenterCloudError(429, "rate_limited")
    return A2ACenterCloudError(502, "outcome_unknown")


def _result(data: object) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("Result"), dict):
        raise HTTPException(502, {"reason": "invalid_response"})
    return data["Result"]


def _member(result: dict, agent_id: str, space_id: str) -> dict:
    if result.get("Id") != agent_id or result.get("A2aSpaceId") != space_id:
        raise HTTPException(502, {"reason": "invalid_response"})
    if result.get("Source") not in {"Runtime", "Standard"}:
        raise HTTPException(502, {"reason": "invalid_response"})
    detail = {"id": agent_id}
    for source, dest in [
        ("Name", "name"),
        ("Status", "status"),
        ("Source", "source"),
        ("DefaultVersion", "defaultVersion"),
        ("ProjectName", "projectName"),
    ]:
        value = result.get(source, "")
        if not isinstance(value, str) or len(value) > 512:
            raise HTTPException(502, {"reason": "invalid_response"})
        detail[dest] = value
    for key, fields in [
        ("RuntimeConfig", {"RuntimeId": "runtimeId", "NetworkType": "networkType"}),
        ("StandardConfig", {"ImportType": "importType"}),
    ]:
        config = result.get(key) or {}
        if not isinstance(config, dict):
            raise HTTPException(502, {"reason": "invalid_response"})
        for source, dest in fields.items():
            value = config.get(source, "")
            if not isinstance(value, str) or len(value) > 512:
                raise HTTPException(502, {"reason": "invalid_response"})
            detail[dest] = value
    return detail


def _display_url(value: object) -> str | None:
    """Project an address for display without URL credentials or query secrets."""
    if not isinstance(value, str) or not value or len(value) > 4096:
        return None
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or "\\" in parsed.netloc
        ):
            return None
        _ = parsed.port
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except ValueError:
        return None


def _runtime_endpoints(runtime: object) -> list[dict[str, str]]:
    endpoints: dict[str, dict[str, str]] = {}
    for config in getattr(runtime, "network_configurations", None) or []:
        kind = getattr(config, "network_type", "")
        address = _display_url(getattr(config, "endpoint", None))
        if kind in {"public", "private"} and address and kind not in endpoints:
            endpoints[kind] = {"networkType": kind, "url": address}
    return list(endpoints.values())


def _card_metadata(raw: object) -> dict:
    """Keep optional registry metadata bounded and separate from write checks."""
    detail: dict = {"serviceAddress": None, "skills": None, "skillsTruncated": False}
    try:
        if isinstance(raw, str):
            if len(raw.encode()) > MAX_BODY:
                return detail
            card = json.loads(raw)
        elif isinstance(raw, dict):
            if len(json.dumps(raw, allow_nan=False).encode()) > MAX_BODY:
                return detail
            card = raw
        else:
            return detail
        if not isinstance(card, dict):
            return detail
        detail["serviceAddress"] = _display_url(card.get("url"))
        skills = card.get("skills")
        if not isinstance(skills, list):
            return detail
        projected = []
        for skill in skills[:100]:
            if not isinstance(skill, dict):
                return detail
            item = {}
            for key, limit in [("id", 256), ("name", 512), ("description", 4096)]:
                value = skill.get(key, "")
                if not isinstance(value, str) or len(value) > limit:
                    return detail
                item[key] = value
            for key, limit in [("tags", 128), ("examples", 1024)]:
                values = skill.get(key, [])
                if (
                    not isinstance(values, list)
                    or len(values) > 20
                    or any(not isinstance(v, str) or len(v) > limit for v in values)
                ):
                    return detail
                item[key] = values
            projected.append(item)
        detail["skills"] = projected
        detail["skillsTruncated"] = len(skills) > 100
    except (ValueError, TypeError, RecursionError):
        pass  # Optional metadata is explicitly unavailable, never a fabricated empty list.
    return detail


def mount_routes(
    app: FastAPI,
    *,
    admin: Callable,
    authorize: Callable,
    region_for: Callable,
    cloud: Callable,
    runtime_request: Callable | None = None,
) -> None:
    async def invoke(**kwargs):
        try:
            return await cloud(**kwargs)
        except A2ACenterCloudError as error:
            logger.info(
                "A2A action refused action=%s status=%s reason=%s",
                kwargs.get("action"),
                error.status,
                error.reason,
            )
            raise HTTPException(
                error.status, {"code": "a2a_request_failed", "reason": error.reason}
            ) from None

    async def target(request: Request, runtime_id: str, region: str):
        admin(request)
        try:
            _identifier(runtime_id, "r")
        except ValueError:
            raise HTTPException(422, "invalid_a2a_target") from None
        return await asyncio.to_thread(authorize, request, runtime_id, region)

    async def agent_result(
        request: Request, agent_id: str, runtime_id: str, space_id: str, region: str
    ):
        await target(request, runtime_id, region)
        try:
            _identifier(agent_id, "a")
            _identifier(space_id, "as")
        except ValueError:
            raise HTTPException(422, "invalid_a2a_target") from None
        try:
            result = _result(
                await invoke(
                    region=region,
                    action="GetA2aAgent",
                    payload={"Id": agent_id, "SpaceId": space_id},
                )
            )
            _member(result, agent_id, space_id)
            return result
        except HTTPException as error:
            if error.status_code >= 500:
                raise HTTPException(502, {"reason": "read_failed"}) from None
            raise
        except Exception:
            raise HTTPException(502, {"reason": "read_failed"}) from None

    @app.get("/web/a2a-runtime-endpoints/{source_runtime_id}")
    async def runtime_endpoints(
        request: Request, source_runtime_id: str, targetRuntimeId: str, region: str = ""
    ):
        region = region_for(region)
        await target(request, targetRuntimeId, region)
        try:
            _identifier(source_runtime_id, "r")
        except ValueError:
            raise HTTPException(422, "invalid_a2a_target") from None
        runtime = await asyncio.to_thread(authorize, request, source_runtime_id, region)
        return {
            "runtimeId": source_runtime_id,
            "endpoints": _runtime_endpoints(runtime),
        }

    @app.get("/web/a2a-agents/{agent_id}")
    async def detail(
        request: Request,
        agent_id: str,
        targetRuntimeId: str,
        spaceId: str,
        region: str = "",
    ):
        region = region_for(region)
        result = await agent_result(request, agent_id, targetRuntimeId, spaceId, region)
        return {
            **_member(result, agent_id, spaceId),
            **_card_metadata(result.get("AgentCard")),
        }

    @app.delete("/web/a2a-agents/{agent_id}")
    async def deregister(
        request: Request,
        agent_id: str,
        targetRuntimeId: str,
        spaceId: str,
        region: str = "",
    ):
        region = region_for(region)
        await agent_result(request, agent_id, targetRuntimeId, spaceId, region)
        try:
            _result(
                await invoke(
                    region=region, action="DeleteA2aAgent", payload={"Id": agent_id}
                )
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(502, {"reason": "outcome_unknown"}) from None
        return {"deleted": True}

    @app.delete("/web/a2a-spaces/{space_id}")
    async def delete_space(
        request: Request, space_id: str, targetRuntimeId: str, region: str = ""
    ):
        region = region_for(region)
        runtime = await target(request, targetRuntimeId, region)
        try:
            _identifier(space_id, "as")
        except ValueError:
            raise HTTPException(422, "invalid_a2a_target") from None
        if runtime_request is None:
            raise HTTPException(503, {"reason": "read_failed"})
        try:
            try:
                binding = await runtime_request(
                    request=request,
                    runtime=runtime,
                    runtime_id=targetRuntimeId,
                    region=region,
                    method="GET",
                    path="/api/v1/studio/collaborators/registry/binding",
                )
            except HTTPException as error:
                if error.status_code in {401, 403}:
                    raise HTTPException(
                        error.status_code, {"reason": "runtime_auth_failed"}
                    ) from None
                raise
            if (
                not isinstance(binding, dict)
                or "space_id" not in binding
                or not (
                    binding["space_id"] is None or isinstance(binding["space_id"], str)
                )
            ):
                raise HTTPException(502, {"reason": "invalid_response"})
            if binding["space_id"] == space_id:
                raise HTTPException(409, {"reason": "space_bound"})
            space = _result(
                await invoke(
                    region=region, action="GetA2aSpace", payload={"Id": space_id}
                )
            )
            if space.get("Id") != space_id:
                raise HTTPException(502, {"reason": "invalid_response"})
            members = _result(
                await invoke(
                    region=region,
                    action="ListA2aAgents",
                    payload={"SpaceId": space_id, "PageNumber": 1, "PageSize": 1},
                )
            )
            if (
                not isinstance(members.get("Items"), list)
                or type(members.get("TotalCount")) is not int
                or members["TotalCount"] < 0
            ):
                raise HTTPException(502, {"reason": "invalid_response"})
            if members["Items"] or members["TotalCount"]:
                raise HTTPException(409, {"reason": "space_not_empty"})
        except HTTPException as error:
            if error.status_code >= 500:
                raise HTTPException(502, {"reason": "read_failed"}) from None
            raise
        except Exception:
            raise HTTPException(502, {"reason": "read_failed"}) from None
        try:
            _result(
                await invoke(
                    region=region, action="DeleteA2aSpace", payload={"Id": space_id}
                )
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(502, {"reason": "outcome_unknown"}) from None
        return {"deleted": True}

    @app.post("/web/a2a-agents", status_code=201)
    async def create(request: Request, region: str = ""):
        admin(request)
        region = region_for(region)
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_BODY:
                raise HTTPException(413, "a2a_registration_too_large")
            raw.extend(chunk)
        try:
            target, payload = registration_payload(json.loads(raw))
        except (ValueError, TypeError, RecursionError):
            # No Pydantic/input or provider errors containing Card credentials.
            raise HTTPException(422, "invalid_a2a_registration") from None
        await asyncio.to_thread(authorize, request, target, region)
        if payload["Source"] == "Runtime":
            await asyncio.to_thread(
                authorize, request, payload["RuntimeConfig"]["RuntimeId"], region
            )
        try:
            result = await invoke(
                region=region, action="CreateA2aAgent", payload=payload
            )
            identifier = _identifier(result["Result"]["Id"], "a")
        except HTTPException:
            raise
        except Exception as error:
            logger.warning(
                "A2A registration outcome unknown region=%s space_id=%s error_type=%s",
                region,
                payload["A2aSpaceId"],
                type(error).__name__,
            )
            # An HTTP/network failure may have occurred after acceptance. Never retry here.
            raise HTTPException(
                502, "a2a_registration_outcome_unknown_refresh_center"
            ) from None
        return {"id": identifier}

    @app.post("/web/a2a-spaces", status_code=201)
    async def create_space(request: Request, region: str = ""):
        admin(request)
        region = region_for(region)
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 4096:
                raise HTTPException(413, "a2a_space_creation_too_large")
            raw.extend(chunk)
        try:
            body = json.loads(raw)
            if not isinstance(body, dict) or set(body) - {
                "targetRuntimeId",
                "name",
                "projectName",
                "intentEnabled",
            }:
                raise ValueError("Invalid body")
            target = _identifier(body.get("targetRuntimeId"), "r")
            name = _space_text(body.get("name"))
            project = _space_text(body.get("projectName", "default"))
            intent = body.get("intentEnabled", False)
            if not isinstance(intent, bool):
                raise ValueError("Invalid intent flag")
        except (ValueError, TypeError, RecursionError):
            raise HTTPException(422, "invalid_a2a_space_creation") from None
        await asyncio.to_thread(authorize, request, target, region)
        try:
            result = await invoke(
                region=region,
                action="CreateA2aSpace",
                payload={
                    "Name": name,
                    "ProjectName": project,
                    "IntentEnabled": intent,
                },
            )
            identifier = _identifier(result["Result"]["Id"], "as")
        except HTTPException:
            raise
        except Exception as error:
            logger.warning(
                "A2A space creation outcome unknown region=%s error_type=%s",
                region,
                type(error).__name__,
            )
            raise HTTPException(
                502, "a2a_space_creation_outcome_unknown_refresh_center"
            ) from None
        return {"id": identifier}


def _space_text(value: object) -> str:
    """Apply Studio's bounded text policy without exposing input in errors."""
    if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Invalid space text")
    value = value.strip()
    if not value or len(value) > 128:
        raise ValueError("Invalid space text")
    return value
