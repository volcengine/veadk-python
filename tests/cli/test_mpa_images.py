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

"""MPA image mutations must be independent, owned and safely reconciled."""

from copy import deepcopy
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from frontend.server.mpa_images import ImageManager, PublicCatalog, repository
from veadk.integrations.mpa.managed.database import agent_suffix

REGION = "cn-beijing"
AGENT = "mi-example"
ACCOUNT = "test-account"
RUNTIME_IMAGE = repository("volcengine", "runtime") + ":old"
WORKER_IMAGE = repository("volcengine", "worker") + ":old"


def manager(provider="volcengine", region=REGION):
    record = {
        "runtime_id": "r-one",
        "worker_id": "t-one",
        "worker_managed": True,
        "state": "ready",
    }
    entry = AsyncMock()
    entry.read.side_effect = lambda: deepcopy(record)

    async def save(data):
        record.clear()
        record.update(deepcopy(data))

    entry.save.side_effect = save
    entry.other_records.return_value = []
    runtime = {
        "RuntimeId": "r-one",
        "ArtifactUrl": repository(provider, "runtime") + ":old",
        "Status": "Ready",
        "ProjectName": "default",
        "ToolId": "t-one",
        "Envs": [
            {"Key": "MPA_AGENT_ID", "Value": AGENT},
            {"Key": "AGENTKIT_TOOL_ID", "Value": "t-one"},
        ],
    }
    tool = {
        "ToolId": "t-one",
        "ImageUrl": repository(provider, "worker") + ":old",
        "Status": "Ready",
        "ProjectName": "default",
        "Tags": [
            {"Key": "managed_by", "Value": "mpa-deployment"},
            {"Key": "mpa_agent_key", "Value": agent_suffix(ACCOUNT, region, AGENT)},
        ],
    }
    cloud, worker, catalog = AsyncMock(), AsyncMock(), AsyncMock()
    cloud.get.side_effect = lambda _: deepcopy(runtime)
    cloud.list_runtimes.return_value = [runtime]
    worker.get.side_effect = lambda _: deepcopy(tool)
    m = ImageManager(
        entry=entry,
        cloud=cloud,
        worker=worker,
        runtime=runtime,
        account=ACCOUNT,
        region=region,
        agent_id=AGENT,
        provider=provider,
        catalog=catalog,
    )
    return m, record, runtime, tool


@pytest.mark.asyncio
@pytest.mark.parametrize("component", ["runtime", "worker"])
async def test_updates_only_selected_component(component):
    m, record, runtime, tool = manager()
    detail = await m.detail(component)
    result = await m.update(component, "new", detail["revision"])
    assert result["operation"]["phase"] == "submitted"
    assert record["image_updates"][component]["target"].endswith(":new")
    if component == "runtime":
        m.cloud.update.assert_awaited_once_with(
            {
                "RuntimeId": "r-one",
                "ArtifactType": "public_image",
                "ArtifactUrl": repository("volcengine", component) + ":new",
                "ReleaseEnable": True,
            }
        )
        m.worker.call.assert_not_awaited()
        assert tool["ImageUrl"] == WORKER_IMAGE
    else:
        m.worker.call.assert_awaited_once_with(
            "update_tool",
            "UpdateToolRequest",
            ToolId="t-one",
            ImageUrl=repository("volcengine", component) + ":new",
        )
        m.cloud.update.assert_not_awaited()
        assert runtime["ArtifactUrl"] == RUNTIME_IMAGE


@pytest.mark.asyncio
async def test_stale_revision_and_unchanged_targets_do_not_write():
    m, *_ = manager()
    detail = await m.detail("runtime")
    for tag, revision in [("new", "stale"), ("old", detail["revision"])]:
        with pytest.raises(HTTPException) as error:
            await m.update("runtime", tag, revision)
        assert error.value.status_code == 409
    m.cloud.update.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", ["pending", "record", "binding", "shared", "tags", "project", "missing"]
)
async def test_worker_ownership_faults_fail_closed(fault):
    m, record, runtime, tool = manager()
    if fault == "pending":
        record["pending"] = True
    if fault == "record":
        record["worker_id"] = "t-other"
    if fault == "binding":
        runtime["ToolId"] = "t-other"
    if fault == "shared":
        m.cloud.list_runtimes.return_value.append(
            {"RuntimeId": "r-other", "ToolId": "t-one"}
        )
    if fault == "tags":
        tool["Tags"] = []
    if fault == "project":
        tool["ProjectName"] = "other"
    if fault == "missing":
        runtime["ToolId"] = ""
        runtime["Envs"].pop()
        record.pop("worker_id")
    detail = await m.detail("worker")
    assert not detail["canUpdate"]
    with pytest.raises(HTTPException):
        await m.update("worker", "new", detail["revision"])
    m.worker.call.assert_not_awaited()


@pytest.mark.asyncio
async def test_lost_response_persists_intent_until_observed_and_blocks_retries():
    m, record, runtime, _ = manager()
    detail = await m.detail("runtime")
    m.cloud.update.side_effect = TimeoutError("sensitive-provider-error")
    with pytest.raises(HTTPException) as error:
        await m.update("runtime", "new", detail["revision"])
    assert error.value.detail == {"reason": "outcome_unknown"}
    assert record["image_updates"]["runtime"]["phase"] == "uncertain"
    detail = await m.detail("runtime")
    assert not detail["canUpdate"]
    with pytest.raises(HTTPException):
        await m.update("runtime", "new", detail["revision"])
    assert m.cloud.update.await_count == 1
    # The other component is still independently available.
    assert (await m.detail("worker"))["canUpdate"]
    runtime["ArtifactUrl"] = repository("volcengine", "runtime") + ":new"
    detail = await m.detail("runtime")
    assert detail["operation"]["phase"] == "configured"
    assert detail["canUpdate"]


@pytest.mark.asyncio
async def test_catalog_failure_before_dispatch_does_not_create_intent():
    m, record, *_ = manager()
    m.catalog.verify.side_effect = HTTPException(502, {"reason": "catalog_failed"})
    detail = await m.detail("worker")
    with pytest.raises(HTTPException):
        await m.update("worker", "new", detail["revision"])
    assert not record.get("image_updates")
    m.worker.call.assert_not_awaited()


@pytest.mark.asyncio
async def test_registry_uses_only_fixed_token_host_and_cursor():
    calls = []

    async def respond(request):
        calls.append(request)
        if request.url.path == "/service/token":
            return httpx.Response(200, json={"token": "test-not-a-real-credential"})
        if not request.headers.get("authorization"):
            return httpx.Response(
                401,
                headers={
                    "WWW-Authenticate": 'Bearer realm="https://untrusted.test/token"'
                },
            )
        return httpx.Response(
            200,
            json={"name": "mpa/mpa_agent", "tags": ["v1", "v2"]},
            headers={"Link": '<https://untrusted.test/>; rel="next"'},
        )

    catalog = PublicCatalog(transport=httpx.MockTransport(respond))
    page = await catalog.page("volcengine", "runtime", "")
    assert page == {
        "tags": ["v1", "v2"],
        "nextCursor": "v2",
        "repository": repository("volcengine", "runtime"),
    }
    assert all(
        r.url.host == repository("volcengine", "runtime").split("/")[0] for r in calls
    )
    assert calls[1].url.params["scope"] == "repository:mpa/mpa_agent:pull"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data", [{"tags": ["../bad"]}, {"tags": "bad"}, {"tags": ["v1", "v1"]}]
)
async def test_bad_catalog_is_not_empty_success(data):
    catalog = PublicCatalog(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    )
    with pytest.raises(HTTPException) as error:
        await catalog.page("byteplus", "worker", "")
    assert error.value.detail == {"reason": "catalog_failed"}


def test_repository_and_tag_cannot_be_arbitrary():
    with pytest.raises(HTTPException):
        repository("other", "worker")
    with pytest.raises(HTTPException):
        repository("volcengine", "other")


@pytest.mark.asyncio
async def test_record_is_durable_before_the_cloud_write_and_other_component_is_preserved():
    m, record, *_ = manager()
    record["image_updates"] = {
        "worker": {"phase": "configured", "target": WORKER_IMAGE}
    }

    async def dispatch(_):
        assert record["image_updates"]["runtime"]["phase"] == "submitting"

    m.cloud.update.side_effect = dispatch
    await m.update("runtime", "new", (await m.detail("runtime"))["revision"])
    assert record["image_updates"]["worker"] == {
        "phase": "configured",
        "target": WORKER_IMAGE,
    }


@pytest.mark.asyncio
async def test_console_change_during_catalog_validation_is_rejected():
    m, record, runtime, _ = manager()

    async def moved(*_):
        runtime["ArtifactUrl"] = RUNTIME_IMAGE + "-changed"

    m.catalog.verify.side_effect = moved
    with pytest.raises(HTTPException) as error:
        await m.update("runtime", "new", (await m.detail("runtime"))["revision"])
    assert error.value.detail == {"reason": "stale"}
    assert not record.get("image_updates")
    m.cloud.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejection_is_safe_and_can_be_retried_after_reading():
    import requests

    m, record, *_ = manager()
    response = requests.Response()
    response.status_code = 403
    m.cloud.update.side_effect = requests.HTTPError("sensitive", response=response)
    with pytest.raises(HTTPException) as error:
        await m.update("runtime", "new", (await m.detail("runtime"))["revision"])
    assert error.value.status_code == 403
    assert error.value.detail == {"reason": "forbidden"}
    assert record["image_updates"]["runtime"]["phase"] == "rejected"
    assert (await m.detail("runtime"))["canUpdate"]


def route_client(*, denied=False, provider="volcengine", region=REGION):
    from contextlib import asynccontextmanager
    from unittest.mock import Mock
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from frontend.server.mpa_images import mount_routes

    m, *_ = manager(provider, region)
    m.entry.in_scope = False
    authorize = Mock(return_value={"RuntimeId": "r-one"})
    admin = Mock(side_effect=HTTPException(403, "denied") if denied else None)

    @asynccontextmanager
    async def scope(_runtime, _region, _catalog):
        m.entry.in_scope = True
        try:
            yield m
        finally:
            m.entry.in_scope = False

    app = FastAPI()
    mount_routes(
        app,
        admin=admin,
        authorize=authorize,
        region_for=lambda r: r or region,
        provider=provider,
        scope=scope,
        catalog=m.catalog,
    )
    return TestClient(app), m, admin, authorize


@pytest.mark.parametrize(
    "suffix,method,body",
    [
        ("runtime", "get", None),
        ("worker/versions", "get", None),
        ("runtime/latest-preview?revision=x", "get", None),
        ("runtime", "post", {"tag": "new", "revision": "x"}),
    ],
)
def test_all_routes_require_management_before_cloud_access(suffix, method, body):
    client, m, _, authorize = route_client(denied=True)
    response = getattr(client, method)(
        "/web/mpa-images/r-one/" + suffix, **({"json": body} if body else {})
    )
    assert response.status_code == 403
    authorize.assert_not_called()
    m.cloud.update.assert_not_awaited()


@pytest.mark.parametrize(
    "body",
    [
        {"tag": "new", "revision": "x", "imageUrl": "https://evil.test"},
        {"tag": "../bad", "revision": "x"},
        {"tag": "x"},
        [],
    ],
)
def test_invalid_write_payload_never_dispatches(body):
    client, m, *_ = route_client()
    assert client.post("/web/mpa-images/r-one/runtime", json=body).status_code == 422
    m.cloud.update.assert_not_awaited()


def test_route_round_trip_and_safe_response_projection():
    client, m, _, authorize = route_client()
    detail = client.get("/web/mpa-images/r-one/worker?region=cn-beijing")
    assert detail.status_code == 200
    assert "Envs" not in detail.text and "Tags" not in detail.text
    result = client.post(
        "/web/mpa-images/r-one/worker?region=cn-beijing",
        json={"tag": "new", "revision": detail.json()["revision"]},
    )
    assert result.status_code == 200
    assert result.json()["operation"]["phase"] == "submitted"
    m.cloud.update.assert_not_awaited()
    assert authorize.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["redirect", "big", "repeat", "timeout"])
async def test_registry_boundaries(mode):
    def respond(request):
        if mode == "redirect":
            return httpx.Response(302, headers={"Location": "http://untrusted.test"})
        if mode == "big":
            return httpx.Response(200, content=b"x" * (1024 * 1024 + 1))
        if mode == "repeat":
            return httpx.Response(
                200, json={"tags": ["last"]}, headers={"Link": "next"}
            )
        raise httpx.ReadTimeout("sensitive", request=request)

    catalog = PublicCatalog(transport=httpx.MockTransport(respond))
    with pytest.raises(HTTPException) as error:
        await catalog.page("volcengine", "worker", "last" if mode == "repeat" else "")
    assert error.value.detail == {"reason": "catalog_failed"}


@pytest.mark.asyncio
async def test_manifest_is_checked_in_the_matching_component_repository():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200)

    await PublicCatalog(transport=httpx.MockTransport(respond)).verify(
        "byteplus", "worker", "v1"
    )
    assert calls[0].method == "HEAD"
    assert (
        str(calls[0].url)
        == "https://"
        + repository("byteplus", "worker").split("/")[0]
        + "/v2/mpa/mpa_codex_worker/manifests/v1"
    )


@pytest.mark.asyncio
async def test_signed_metadata_is_not_returned_to_the_browser():
    m, _, runtime, _ = manager()
    runtime["ArtifactUrl"] = "https://private.example/image?token=sensitive"
    detail = await m.detail("runtime")
    assert not detail["canUpdate"]
    assert detail["currentImage"] == ""
    assert "sensitive" not in str(detail)


@pytest.mark.asyncio
async def test_python310_overall_catalog_deadline_returns_a_safe_error(monkeypatch):
    import asyncio

    async def timeout(coroutine, _seconds):
        coroutine.close()
        raise asyncio.TimeoutError()

    monkeypatch.setattr("frontend.server.mpa_images.asyncio.wait_for", timeout)
    catalog = PublicCatalog()
    with pytest.raises(HTTPException) as error:
        await catalog.page("volcengine", "runtime", "")
    assert error.value.detail == {"reason": "catalog_failed"}


@pytest.mark.asyncio
@pytest.mark.parametrize("component", ["runtime", "worker"])
async def test_manual_image_updates_only_selected_component_without_registry_requests(
    component,
):
    m, record, runtime, tool = manager()
    image = "registry.example.com/team/custom-agent:release-1"
    detail = await m.detail(component)
    result = await m.update(component, None, detail["revision"], image=image)
    assert result["operation"]["target"] == image
    assert record["image_updates"][component]["target"] == image
    m.catalog.verify.assert_not_awaited()
    m.catalog.page.assert_not_awaited()
    if component == "runtime":
        m.cloud.update.assert_awaited_once_with(
            {
                "RuntimeId": "r-one",
                "ArtifactType": "image",
                "ArtifactUrl": image,
                "ReleaseEnable": True,
            }
        )
        m.worker.call.assert_not_awaited()
        assert tool["ImageUrl"] == WORKER_IMAGE
    else:
        m.worker.call.assert_awaited_once_with(
            "update_tool", "UpdateToolRequest", ToolId="t-one", ImageUrl=image
        )
        m.cloud.update.assert_not_awaited()
        assert runtime["ArtifactUrl"] == RUNTIME_IMAGE


@pytest.mark.asyncio
async def test_manual_corresponding_public_runtime_image_keeps_public_artifact_type():
    m, *_ = manager()
    image = repository("volcengine", "runtime") + ":new"
    await m.update(
        "runtime", None, (await m.detail("runtime"))["revision"], image=image
    )
    assert m.cloud.update.await_args.args[0]["ArtifactType"] == "public_image"
    m.catalog.verify.assert_not_awaited()


@pytest.mark.parametrize(
    "image",
    [
        "https://registry.example/team/image:v1",
        "registry.example/team/image",
        "user:password@registry.example/team/image:v1",
        "registry.example/team/image:v1?token=secret",
        "registry.example/team/image:v1#fragment",
        "registry.example/team/image:v1\n",
        "registry.example:65536/team/image:v1",
        "registry.example:0/team/image:v1",
        "registry.example/Team/image:v1",
        "registry.example/team/image@sha256:" + "a" * 64,
        "registry.example/team/../image:v1",
        "x" * 2049,
    ],
)
def test_invalid_manual_images_are_rejected_before_cloud_or_registry_access(image):
    client, m, _, authorize = route_client()
    result = client.post(
        "/web/mpa-images/r-one/runtime", json={"image": image, "revision": "revision"}
    )
    assert result.status_code == 422
    authorize.assert_not_called()
    m.cloud.update.assert_not_awaited()
    m.worker.call.assert_not_awaited()
    m.catalog.verify.assert_not_awaited()


@pytest.mark.parametrize(
    "image",
    [
        "registry.example/team/image:v1",
        "registry.example:5000/team/image:Release_1",
        "ghcr.io/org/team/image:1.2.3",
        "localhost:5000/team/image:latest",
    ],
)
def test_manual_address_validation_accepts_complete_tagged_references(image):
    from frontend.server.mpa_images import valid_image

    assert valid_image(image)


@pytest.mark.parametrize(
    "extra",
    [
        {"tag": "new", "image": "registry.example/team/image:v1"},
        {},
        {"image": ""},
        {"image": None},
    ],
)
def test_manual_payload_requires_exactly_one_source(extra):
    client, m, *_ = route_client()
    assert (
        client.post(
            "/web/mpa-images/r-one/runtime", json={"revision": "x", **extra}
        ).status_code
        == 422
    )
    m.cloud.update.assert_not_awaited()
    m.worker.call.assert_not_awaited()


def test_manual_route_uses_the_image_union_and_does_not_contact_its_host():
    client, m, *_ = route_client()
    detail = client.get("/web/mpa-images/r-one/worker").json()
    image = "private-registry.example:5000/team/worker:release-1"
    result = client.post(
        "/web/mpa-images/r-one/worker",
        json={"image": image, "revision": detail["revision"]},
    )
    assert result.status_code == 200
    assert result.json()["operation"]["target"] == image
    m.worker.call.assert_awaited_once_with(
        "update_tool", "UpdateToolRequest", ToolId="t-one", ImageUrl=image
    )
    m.catalog.verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_images_keep_stale_and_unknown_outcome_guards():
    m, record, *_ = manager()
    image = "registry.example/team/image:new"
    with pytest.raises(HTTPException) as error:
        await m.update("runtime", None, "stale", image=image)
    assert error.value.detail == {"reason": "stale"}
    m.cloud.update.assert_not_awaited()
    m.cloud.update.side_effect = TimeoutError()
    with pytest.raises(HTTPException):
        await m.update(
            "runtime", None, (await m.detail("runtime"))["revision"], image=image
        )
    assert record["image_updates"]["runtime"]["phase"] == "uncertain"
    with pytest.raises(HTTPException):
        await m.update(
            "runtime", None, (await m.detail("runtime"))["revision"], image=image
        )
    assert m.cloud.update.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,region", [("volcengine", "cn-beijing"), ("byteplus", "ap-southeast-1")]
)
@pytest.mark.parametrize("component", ["runtime", "worker"])
async def test_public_latest_uses_upstream_resolver_for_only_selected_component(
    monkeypatch, provider, region, component
):
    from unittest.mock import Mock

    m, record, runtime, tool = manager(provider, region)
    creation = {
        "requested": {"runtimeImage": "original"},
        "selected": {"runtimeImage": {"image": "original:version"}},
    }
    record["image_snapshots"] = deepcopy(creation)
    repo = repository(provider, component)
    choice = {"image": repo + ":release-20261022", "digest": "sha256:" + "a" * 64}
    resolver = Mock(return_value=choice)
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.image_snapshot.snapshot_image", resolver
    )
    result = await m.update(
        component, "latest", (await m.detail(component))["revision"]
    )
    assert resolver.call_args.args[0] == repo + ":latest"
    assert vars(resolver.call_args.args[1]) == {"provider": provider}
    assert result["operation"] == {
        "phase": "submitted",
        "target": choice["image"],
        "requestedImage": repo + ":latest",
        "digest": choice["digest"],
    }
    assert record["image_snapshots"] == creation
    assert set(record["image_updates"]) == {component}
    m.catalog.verify.assert_not_awaited()
    if component == "runtime":
        assert m.cloud.update.await_args.args[0]["ArtifactUrl"] == choice["image"]
        m.worker.call.assert_not_awaited()
        assert tool["ImageUrl"] == repository(provider, "worker") + ":old"
    else:
        assert m.worker.call.await_args.kwargs["ImageUrl"] == choice["image"]
        m.cloud.update.assert_not_awaited()
        assert runtime["ArtifactUrl"] == repository(provider, "runtime") + ":old"


@pytest.mark.asyncio
async def test_latest_submission_verifies_saved_selection_without_reselecting_latest(
    monkeypatch,
):
    from unittest.mock import Mock

    m, record, *_ = manager()
    choice = {
        "image": repository("volcengine", "runtime") + ":chosen-before-latest-moved",
        "digest": "sha256:" + "b" * 64,
    }
    resolver = Mock(return_value=choice)
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.image_snapshot.snapshot_image", resolver
    )
    await m.update(
        "runtime", "latest", (await m.detail("runtime"))["revision"], selection=choice
    )
    assert resolver.call_args.kwargs["selection"] == choice
    assert record["image_updates"]["runtime"]["target"] == choice["image"]


@pytest.mark.asyncio
async def test_latest_resolution_failure_prevents_intent_and_cloud_mutation(
    monkeypatch,
):
    from unittest.mock import Mock
    from veadk.integrations.mpa.managed.database import DeploymentError

    m, record, *_ = manager()
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.image_snapshot.snapshot_image",
        Mock(side_effect=DeploymentError("Registered image selection content changed")),
    )
    choice = {
        "image": repository("volcengine", "runtime") + ":overwritten",
        "digest": "sha256:" + "a" * 64,
    }
    with pytest.raises(HTTPException) as error:
        await m.update(
            "runtime",
            "latest",
            (await m.detail("runtime"))["revision"],
            selection=choice,
        )
    assert error.value.detail == {"reason": "latest_resolution_failed"}
    assert not record.get("image_updates")
    m.cloud.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_latest_alias_current_image_still_resolves_to_a_version(monkeypatch):
    from unittest.mock import Mock

    m, _, runtime, _ = manager()
    runtime["ArtifactUrl"] = repository("volcengine", "runtime") + ":latest"
    choice = {
        "image": repository("volcengine", "runtime") + ":new-content",
        "digest": "sha256:" + "c" * 64,
    }
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.image_snapshot.snapshot_image",
        Mock(return_value=choice),
    )
    await m.update("runtime", "latest", (await m.detail("runtime"))["revision"])
    assert m.cloud.update.await_args.args[0]["ArtifactUrl"] == choice["image"]


@pytest.mark.asyncio
async def test_manual_latest_does_not_use_public_discovery(monkeypatch):
    from unittest.mock import Mock

    m, *_ = manager()
    resolver = Mock(side_effect=AssertionError("Manual image must not be discovered"))
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.image_snapshot.snapshot_image", resolver
    )
    await m.update(
        "runtime",
        None,
        (await m.detail("runtime"))["revision"],
        image="registry.example/team/image:latest",
    )
    resolver.assert_not_called()


@pytest.mark.parametrize(
    "provider,region", [("volcengine", "cn-beijing"), ("byteplus", "ap-southeast-1")]
)
@pytest.mark.parametrize("component", ["runtime", "worker"])
def test_latest_preview_is_read_only_and_releases_provisioning_lock_during_resolution(
    monkeypatch, provider, region, component
):
    from unittest.mock import Mock

    client, m, _, authorize = route_client(provider=provider, region=region)
    choice = {
        "image": repository(provider, component) + ":release",
        "digest": "sha256:" + "a" * 64,
    }

    def resolve(*args, **kwargs):
        assert not m.entry.in_scope
        return choice

    resolver = Mock(side_effect=resolve)
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.image_snapshot.snapshot_image", resolver
    )
    path = f"/web/mpa-images/r-one/{component}"
    revision = client.get(path).json()["revision"]
    result = client.get(path + "/latest-preview", params={"revision": revision})
    assert result.status_code == 200
    assert result.json() == {
        "component": component,
        "revision": revision,
        "requestedImage": repository(provider, component) + ":latest",
        **choice,
    }
    assert authorize.call_count == 3
    m.cloud.update.assert_not_awaited()
    m.worker.call.assert_not_awaited()
    m.entry.save.assert_not_awaited()


def test_latest_snapshot_payload_stays_compatible_with_legacy_source_union(monkeypatch):
    from unittest.mock import Mock

    client, m, *_ = route_client()
    choice = {
        "image": repository("volcengine", "worker") + ":release",
        "digest": "sha256:" + "a" * 64,
    }
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.image_snapshot.snapshot_image",
        Mock(return_value=choice),
    )
    revision = client.get("/web/mpa-images/r-one/worker").json()["revision"]
    result = client.post(
        "/web/mpa-images/r-one/worker",
        json={"tag": "latest", "revision": revision, "selection": choice},
    )
    assert result.status_code == 200
    assert m.worker.call.await_args.kwargs["ImageUrl"] == choice["image"]


@pytest.mark.parametrize(
    "source",
    [
        {"tag": "new"},
        {"image": "registry.example/team/image:latest"},
        {"tag": "latest", "extra": "bad"},
    ],
)
def test_selection_is_only_accepted_for_public_latest(source):
    client, m, *_ = route_client()
    choice = {
        "image": repository("volcengine", "runtime") + ":release",
        "digest": "sha256:" + "a" * 64,
    }
    assert (
        client.post(
            "/web/mpa-images/r-one/runtime",
            json={"revision": "x", "selection": choice, **source},
        ).status_code
        == 422
    )
    m.cloud.update.assert_not_awaited()


@pytest.mark.parametrize("mutation", ["stale", "permission"])
def test_preview_reauthorizes_and_rechecks_after_discovery(monkeypatch, mutation):
    from unittest.mock import Mock

    client, m, _, authorize = route_client()
    revision = client.get("/web/mpa-images/r-one/runtime").json()["revision"]
    choice = {
        "image": repository("volcengine", "runtime") + ":release",
        "digest": "sha256:" + "a" * 64,
    }

    def resolve(*args, **kwargs):
        if mutation == "stale":
            m.runtime["ArtifactUrl"] = (
                repository("volcengine", "runtime") + ":concurrent"
            )
        else:
            authorize.side_effect = HTTPException(403, {"reason": "forbidden"})
        return choice

    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.image_snapshot.snapshot_image",
        Mock(side_effect=resolve),
    )
    result = client.get(
        "/web/mpa-images/r-one/runtime/latest-preview", params={"revision": revision}
    )
    assert result.status_code == (409 if mutation == "stale" else 403)
    m.cloud.update.assert_not_awaited()
    m.entry.save.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    ["stale_before", "stale_after", "unchanged", "invalid_result", "unknown_write"],
)
async def test_latest_guards_before_intent_and_unknown_write_reconciliation(
    monkeypatch, mode
):
    from unittest.mock import Mock

    m, record, runtime, _ = manager()
    revision = (await m.detail("runtime"))["revision"]
    choice = {
        "image": repository("volcengine", "runtime")
        + (":old" if mode == "unchanged" else ":release"),
        "digest": "sha256:" + "a" * 64,
    }
    if mode == "invalid_result":
        choice["image"] = "untrusted.example/team/image:new"

    def resolve(*args, **kwargs):
        if mode == "stale_after":
            runtime["Status"] = "Updating"
        return choice

    resolver = Mock(side_effect=resolve)
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.image_snapshot.snapshot_image", resolver
    )
    if mode == "unknown_write":
        m.cloud.update.side_effect = TimeoutError()
    with pytest.raises(HTTPException) as error:
        await m.update(
            "runtime", "latest", "stale" if mode == "stale_before" else revision
        )
    expected = {
        "stale_before": "stale",
        "stale_after": "stale",
        "unchanged": "unchanged",
        "invalid_result": "latest_resolution_failed",
        "unknown_write": "outcome_unknown",
    }[mode]
    assert error.value.detail == {"reason": expected}
    if mode == "unknown_write":
        assert record["image_updates"]["runtime"]["phase"] == "uncertain"
        with pytest.raises(HTTPException):
            await m.update("runtime", "latest", revision)
        assert m.cloud.update.await_count == 1
    else:
        assert not record.get("image_updates")
        m.cloud.update.assert_not_awaited()
    if mode == "stale_before":
        resolver.assert_not_called()


@pytest.mark.parametrize(
    "selection",
    [
        None,
        {},
        {"image": "untrusted.example/team/image:v1", "digest": "sha256:" + "a" * 64},
        {
            "image": repository("volcengine", "runtime") + ":latest",
            "digest": "sha256:" + "a" * 64,
        },
        {
            "image": repository("volcengine", "runtime") + ":release",
            "digest": "invalid",
        },
    ],
)
def test_malformed_latest_selection_is_rejected_before_registry_io(
    monkeypatch, selection
):
    from unittest.mock import Mock

    client, m, *_ = route_client()
    resolver = Mock()
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.image_snapshot.snapshot_image", resolver
    )
    result = client.post(
        "/web/mpa-images/r-one/runtime",
        json={"tag": "latest", "revision": "x", "selection": selection},
    )
    assert result.status_code == 422
    resolver.assert_not_called()
    m.cloud.update.assert_not_awaited()
