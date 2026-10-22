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

"""Independent image management for exclusively owned MPA resources."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Callable
from types import SimpleNamespace
from typing import NoReturn

import httpx
from fastapi import FastAPI, HTTPException, Query, Request

from veadk.integrations.mpa.managed.database import agent_suffix
from veadk.integrations.mpa.managed.diagnostics import classify_error
from veadk.integrations.mpa.managed.runtime import env_map

REPOSITORIES = {
    "volcengine": "agentkit-platform-2112682748-cn-beijing.cr.volces.com/mpa",
    "byteplus": "agentkit-platform-3001037806-ap-southeast-1.cr.bytepluses.com/mpa",
}
COMPONENTS = {"runtime": "mpa_agent", "worker": "mpa_codex_worker"}
READY = {"ready", "running", "available"}
ACTIVE = {"submitting", "submitted", "uncertain"}
MAX_RESPONSE = 1024 * 1024


def fail(status: int, reason: str) -> NoReturn:
    raise HTTPException(status, {"reason": reason})


def repository(provider: str, component: str) -> str:
    if provider not in REPOSITORIES or component not in COMPONENTS:
        fail(422, "invalid_request")
    return REPOSITORIES[provider] + "/" + COMPONENTS[component]


def valid_tag(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[\w][\w.-]{0,127}", value, re.ASCII) is not None
    )


_IMAGE_HOST = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_IMAGE_PART = r"[a-z0-9]+(?:(?:[._]|__|[-]+)[a-z0-9]+)*"
_IMAGE_REFERENCE = re.compile(
    rf"(?P<host>{_IMAGE_HOST}(?:\.{_IMAGE_HOST})*)(?::(?P<port>[0-9]{{1,5}}))?/"
    rf"{_IMAGE_PART}(?:/{_IMAGE_PART})*:[\w][\w.-]{{0,127}}",
    re.ASCII,
)


def valid_image(value: object) -> bool:
    """Validate a tagged image reference without contacting its registry."""
    if not isinstance(value, str) or len(value) > 2048:
        return False
    match = _IMAGE_REFERENCE.fullmatch(value)
    if match is None:
        return False
    port = match.group("port")
    host = match.group("host")
    return (port is None or 1 <= int(port) <= 65535) and (
        "." in host or port is not None or host == "localhost"
    )


def valid_selection(provider: str, component: str, value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {"image", "digest"}:
        return False
    image, digest = value["image"], value["digest"]
    return (
        valid_image(image)
        and image.startswith(repository(provider, component) + ":")
        and image.rsplit(":", 1)[1] != "latest"
        and isinstance(digest, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is not None
    )


async def resolve_latest(provider: str, component: str, *, selection=None):
    """Reuse creation's anonymous resolver without its persisted creation state."""
    from veadk.integrations.mpa.managed.image_snapshot import snapshot_image

    try:
        result = await asyncio.to_thread(
            snapshot_image,
            repository(provider, component) + ":latest",
            SimpleNamespace(provider=provider),
            selection=selection,
        )
    except Exception:
        fail(502, "latest_resolution_failed")
    if not valid_selection(provider, component, result) or (
        selection is not None and result != selection
    ):
        fail(502, "latest_resolution_failed")
    return result


def check_revision(detail, revision):
    if detail["revision"] != revision:
        fail(409, "stale")
    if not detail["canUpdate"]:
        fail(409, detail["reason"])


class PublicCatalog:
    def __init__(self, *, transport=None):
        self.transport = transport

    async def _read(self, repo: str, suffix: str, *, params=None, head=False):
        host, path = repo.split("/", 1)
        url = f"https://{host}/v2/{path}/{suffix}"
        async with httpx.AsyncClient(
            timeout=12, follow_redirects=False, transport=self.transport
        ) as client:

            async def send(target, *, headers=None, query=None, method="GET"):
                async with client.stream(
                    method, target, params=query, headers=headers
                ) as response:
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_RESPONSE:
                            fail(502, "catalog_failed")
                    return response.status_code, response.headers, bytes(content)

            headers = {
                "Accept": "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"
            }
            method = "HEAD" if head else "GET"
            status, response_headers, body = await send(
                url, headers=headers, query=params, method=method
            )
            if status == 401:
                # Never follow the remote challenge realm or a pagination Link URL.
                token_status, _, token_body = await send(
                    f"https://{host}/service/token",
                    query={
                        "service": "harbor-registry",
                        "scope": f"repository:{path}:pull",
                    },
                )
                if token_status != 200:
                    fail(502, "catalog_failed")
                token_data = json.loads(token_body)
                token = token_data.get("token") or token_data.get("access_token")
                if (
                    not isinstance(token, str)
                    or not token
                    or len(token) > 16384
                    or any(c.isspace() for c in token)
                ):
                    fail(502, "catalog_failed")
                headers["Authorization"] = "Bearer " + token
                status, response_headers, body = await send(
                    url, headers=headers, query=params, method=method
                )
            if status != 200:
                fail(502, "catalog_failed")
            return response_headers, body

    async def page(self, provider: str, component: str, cursor: str):
        repo = repository(provider, component)
        if cursor and not valid_tag(cursor):
            fail(422, "invalid_request")
        try:
            headers, body = await asyncio.wait_for(
                self._read(
                    repo,
                    "tags/list",
                    params={"n": 100, **({"last": cursor} if cursor else {})},
                ),
                25,
            )
            data = json.loads(body)
            tags = data.get("tags") if isinstance(data, dict) else None
            if tags is None and isinstance(data, dict) and "tags" in data:
                tags = []
            if (
                not isinstance(tags, list)
                or len(tags) > 100
                or any(not valid_tag(tag) for tag in tags)
                or len(set(tags)) != len(tags)
                or cursor in tags
            ):
                fail(502, "catalog_failed")
            return {
                "repository": repo,
                "tags": tags,
                "nextCursor": tags[-1]
                if tags and (headers.get("link") or len(tags) == 100)
                else "",
            }
        except HTTPException:
            raise
        except (
            httpx.HTTPError,
            ValueError,
            TypeError,
            AttributeError,
            TimeoutError,
            asyncio.TimeoutError,
        ):
            fail(502, "catalog_failed")

    async def verify(self, provider: str, component: str, tag: str):
        repo = repository(provider, component)
        if not valid_tag(tag):
            fail(422, "invalid_request")
        try:
            await asyncio.wait_for(self._read(repo, "manifests/" + tag, head=True), 25)
        except HTTPException:
            raise
        except (
            httpx.HTTPError,
            ValueError,
            TypeError,
            AttributeError,
            TimeoutError,
            asyncio.TimeoutError,
        ):
            fail(502, "catalog_failed")


class ImageManager:
    """Caller holds the existing account/region registry lock for this lifetime."""

    def __init__(
        self,
        *,
        entry,
        cloud,
        worker,
        runtime,
        account,
        region,
        agent_id,
        provider,
        catalog,
    ):
        self.entry, self.cloud, self.worker, self.runtime = (
            entry,
            cloud,
            worker,
            runtime,
        )
        self.account, self.region, self.agent_id = account, region, agent_id
        self.provider, self.catalog = provider, catalog
        self.write_started = False

    async def _snapshot(self, component):
        repo = repository(self.provider, component)
        record = await self.entry.read() if self.entry is not None else {}
        runtime = await self.cloud.get(self.runtime["RuntimeId"])
        values = env_map(runtime)
        binding = runtime.get("ToolId") or values.get("AGENTKIT_TOOL_ID", "")
        reason = ""
        if (
            runtime.get("RuntimeId") != self.runtime["RuntimeId"]
            or values.get("MPA_AGENT_ID") != self.agent_id
            or not record
            or record.get("runtime_id") != runtime.get("RuntimeId")
        ):
            reason = "ownership"
        elif record.get("pending") or record.get("state") in {"deleting", "deleted"}:
            reason = "busy"
        if values.get("SHARED_APIG_DATABASE_URL") != env_map(self.runtime).get(
            "SHARED_APIG_DATABASE_URL"
        ):
            reason = "ownership"
        if values.get("AGENTKIT_TOOL_REGION") not in (None, "", self.region):
            reason = "ownership"
        resource = runtime
        if component == "worker":
            if not binding:
                reason = "missing_worker"
                resource = {}
            elif not reason:
                if (
                    record.get("worker_id") != binding
                    or record.get("worker_managed") is not True
                    or (
                        runtime.get("ToolId")
                        and values.get("AGENTKIT_TOOL_ID")
                        and runtime["ToolId"] != values["AGENTKIT_TOOL_ID"]
                    )
                ):
                    reason = "ownership"
                resource = await self.worker.get(binding) if not reason else {}
                tags = {
                    t.get("Key"): t.get("Value") for t in resource.get("Tags") or []
                }
                if (
                    resource.get("ToolId") != binding
                    or tags.get("managed_by") != "mpa-deployment"
                    or tags.get("mpa_agent_key")
                    != agent_suffix(self.account, self.region, self.agent_id)
                    or resource.get("ProjectName")
                    != (runtime.get("ProjectName") or "default")
                    or env_map(resource).get("MPA_AGENT_ID")
                    not in (None, "", self.agent_id)
                ):
                    reason = "ownership"
                if not reason:
                    assert self.entry is not None
                    others = await self.entry.other_records()
                    runtimes = await self.cloud.list_runtimes()
                    if any(
                        r.get("worker_id") == binding and r.get("state") != "deleted"
                        for r in others
                    ) or any(
                        r.get("RuntimeId") != runtime["RuntimeId"]
                        and binding
                        in {r.get("ToolId"), env_map(r).get("AGENTKIT_TOOL_ID")}
                        for r in runtimes
                    ):
                        reason = "ownership"
            else:
                resource = {}
        image_key = "ArtifactUrl" if component == "runtime" else "ImageUrl"
        current = str(resource.get(image_key) or "")
        if current and (
            len(current) > 2048
            or "//" in current
            or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9./:_-]*(?:@sha256:[0-9a-f]{64})?", current
            )
        ):
            # Cloud metadata must not turn signed URLs or credentials into UI text.
            current, reason = "", "ownership"
        status = str(resource.get("Status") or "")
        resource_id = runtime["RuntimeId"] if component == "runtime" else binding
        operation = (record.get("image_updates") or {}).get(component)
        if operation and operation.get("phase") in ACTIVE:
            if (
                not reason
                and current == operation.get("target")
                and status.lower() in READY
            ):
                operation = {**operation, "phase": "configured"}
                record["image_updates"][component] = operation
                assert self.entry is not None
                await self.entry.save(record)
            else:
                reason = reason or "busy"
        if not reason and (not current or status.lower() not in READY):
            reason = "busy"
        revision = hashlib.sha256(
            json.dumps(
                [
                    runtime.get("RuntimeId"),
                    binding,
                    self.agent_id,
                    resource_id,
                    runtime.get("ProjectName"),
                    runtime.get("Tags"),
                    resource.get("Tags"),
                    current,
                    status,
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return record, {
            "component": component,
            "resourceId": resource_id,
            "repository": repo,
            "currentImage": current,
            "status": status,
            "revision": revision,
            "canUpdate": not reason,
            "reason": reason,
            "operation": operation,
        }

    async def detail(self, component):
        return (await self._snapshot(component))[1]

    async def update(self, component, tag, revision, *, image=None, selection=None):
        if (
            (tag is None) == (image is None)
            or not isinstance(revision, str)
            or len(revision) > 128
        ):
            fail(422, "invalid_request")
        if image is not None and not valid_image(image):
            fail(422, "invalid_image")
        if tag is not None and not valid_tag(tag):
            fail(422, "invalid_request")
        public_repo = repository(self.provider, component)
        latest = image is None and tag == "latest"
        if selection is not None and (
            not latest or not valid_selection(self.provider, component, selection)
        ):
            fail(422, "invalid_request")
        if image is not None:
            target = image
        else:
            assert isinstance(tag, str)
            target = public_repo + ":" + tag
        artifact_type = (
            "public_image" if target.startswith(public_repo + ":") else "image"
        )
        record, detail = await self._snapshot(component)
        check_revision(detail, revision)
        if latest:
            selection = await resolve_latest(
                self.provider, component, selection=selection
            )
            target = selection["image"]
        if target == detail["currentImage"]:
            fail(409, "unchanged")
        if image is None and not latest:
            await self.catalog.verify(self.provider, component, tag)
        # Recheck the resource after target validation and any catalog I/O.
        record, fresh = await self._snapshot(component)
        if fresh["revision"] != revision or not fresh["canUpdate"]:
            fail(409, "stale")
        operation = {"target": target, "phase": "submitting"}
        if latest:
            assert selection is not None
            operation.update(
                requestedImage=public_repo + ":latest", digest=selection["digest"]
            )
        record.setdefault("image_updates", {})[component] = operation
        await self.entry.save(record)
        try:
            self.write_started = True
            if component == "runtime":
                await self.cloud.update(
                    {
                        "RuntimeId": detail["resourceId"],
                        "ArtifactType": artifact_type,
                        "ArtifactUrl": target,
                        "ReleaseEnable": True,
                    }
                )
            else:
                await self.worker.call(
                    "update_tool",
                    "UpdateToolRequest",
                    ToolId=detail["resourceId"],
                    ImageUrl=target,
                )
        except Exception as error:
            category = classify_error(error)
            rejected = category in {
                "permission",
                "invalid_request",
                "not_found",
                "throttled",
            }
            operation["phase"] = "rejected" if rejected else "uncertain"
            await self.entry.save(record)
            fail(
                403 if category == "permission" else 409 if rejected else 502,
                "forbidden"
                if category == "permission"
                else "rejected"
                if rejected
                else "outcome_unknown",
            )
        operation["phase"] = "submitted"
        await self.entry.save(record)
        return {**detail, "canUpdate": False, "reason": "busy", "operation": operation}


def mount_routes(
    app: FastAPI,
    *,
    admin: Callable,
    authorize: Callable,
    region_for: Callable,
    provider: str,
    scope: Callable,
    catalog=None,
):
    catalog = catalog or PublicCatalog()
    running: set[asyncio.Task] = set()

    async def access(request, runtime_id, component, region):
        admin(request)
        repository(provider, component)
        if not re.fullmatch(r"r-[A-Za-z0-9_-]{1,100}", runtime_id):
            fail(422, "invalid_request")
        region = region_for(region)
        if not re.fullmatch(r"(?:cn-[a-z]+|ap-[a-z]+-[0-9]+)", region) or (
            provider == "volcengine"
        ) != region.startswith("cn-"):
            fail(422, "invalid_request")
        runtime = await asyncio.to_thread(authorize, request, runtime_id, region)
        return runtime, region

    async def managed(request, runtime_id, component, region, body=None):
        runtime, region = await access(request, runtime_id, component, region)
        manager = None
        try:
            async with scope(runtime, region, catalog) as manager:
                if body is None:
                    return await manager.detail(component)
                return await manager.update(
                    component,
                    body.get("tag"),
                    body["revision"],
                    image=body.get("image"),
                    selection=body.get("selection"),
                )
        except HTTPException:
            raise
        except Exception as error:
            if classify_error(error) == "permission":
                fail(403, "forbidden")
            fail(
                502,
                "outcome_unknown"
                if manager is not None and manager.write_started
                else "read_failed",
            )

    @app.get("/web/mpa-images/{runtime_id}/{component}/versions")
    async def versions(
        request: Request,
        runtime_id: str,
        component: str,
        region: str = "",
        cursor: str = Query(default="", max_length=128),
    ):
        await access(request, runtime_id, component, region)
        return await catalog.page(provider, component, cursor)

    @app.get("/web/mpa-images/{runtime_id}/{component}/latest-preview")
    async def latest_preview(
        request: Request,
        runtime_id: str,
        component: str,
        revision: str = Query(min_length=1, max_length=128),
        region: str = "",
    ):
        async def preview():
            # Discovery can be slow. Do not hold a provisioning lock while reading tags.
            check_revision(
                await managed(request, runtime_id, component, region), revision
            )
            selection = await resolve_latest(provider, component)
            check_revision(
                await managed(request, runtime_id, component, region), revision
            )
            return {
                "component": component,
                "revision": revision,
                "requestedImage": repository(provider, component) + ":latest",
                **selection,
            }

        try:
            return await asyncio.wait_for(preview(), 180)
        except asyncio.TimeoutError:
            fail(504, "latest_resolution_failed")

    @app.get("/web/mpa-images/{runtime_id}/{component}")
    async def detail(
        request: Request, runtime_id: str, component: str, region: str = ""
    ):
        try:
            return await asyncio.wait_for(
                managed(request, runtime_id, component, region), 30
            )
        except asyncio.TimeoutError:
            fail(504, "read_failed")

    @app.post("/web/mpa-images/{runtime_id}/{component}")
    async def update(
        request: Request, runtime_id: str, component: str, region: str = ""
    ):
        admin(request)
        raw = await request.body()
        if len(raw) > 4096:
            fail(413, "invalid_request")
        try:
            body = json.loads(raw)
        except ValueError:
            fail(422, "invalid_request")
        if (
            not isinstance(body, dict)
            or set(body)
            not in (
                {"tag", "revision"},
                {"image", "revision"},
                {"tag", "revision", "selection"},
            )
            or not isinstance(body["revision"], str)
            or len(body["revision"]) > 128
        ):
            fail(422, "invalid_request")
        if "image" in body and not valid_image(body["image"]):
            fail(422, "invalid_image")
        if "tag" in body and not valid_tag(body["tag"]):
            fail(422, "invalid_request")
        if "selection" in body and (
            body.get("tag") != "latest"
            or not valid_selection(provider, component, body["selection"])
        ):
            fail(422, "invalid_request")
        # Keep the lock until the synchronous SDK call finishes, even on disconnect.
        task = asyncio.create_task(
            managed(request, runtime_id, component, region, body)
        )
        running.add(task)

        def done(completed):
            running.discard(completed)
            if not completed.cancelled():
                completed.exception()

        task.add_done_callback(done)
        return await asyncio.shield(task)
