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

from __future__ import annotations

import io
from datetime import datetime, timezone
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, Literal

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from frontend.server.runtime_artifacts import (
    RuntimeArtifactAccess,
    RuntimeArtifactService,
    mount_routes,
)

from frontend.server.storage import StudioStorageConfig


class FakeObject(io.BytesIO):
    def __init__(self, content: bytes, content_length: object) -> None:
        super().__init__(content)
        self.content_length = content_length
        self.read_calls = 0

    def read(self, size: int | None = -1, /) -> bytes:
        self.read_calls += 1
        return super().read(size)


class FakeTos:
    def __init__(self) -> None:
        self.files = {
            "artifacts/alice/session-1/report.html": b'<img src="chart.svg">',
            "artifacts/alice/session-1/chart.svg": b"<svg/>",
            "artifacts/bob/session-1/private.txt": b"private",
        }
        self.calls: list[dict[str, Any]] = []
        self.error: Exception | None = None
        self.page_token = ""
        self.truncated = False
        self.size: int | None = None
        self.streams: list[FakeObject] = []

    def list_objects_type2(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        keys = [key for key in self.files if key.startswith(kwargs["prefix"])]
        return SimpleNamespace(
            contents=[
                SimpleNamespace(
                    key=key,
                    size=len(self.files[key]),
                    last_modified=datetime(2026, 9, 17, tzinfo=timezone.utc),
                )
                for key in keys[: kwargs["max_keys"]]
            ],
            is_truncated=self.truncated,
            next_continuation_token=self.page_token,
        )

    def head_object(self, **kwargs: Any) -> Any:
        self.calls.append({"method": "HEAD", **kwargs})
        if kwargs["key"] not in self.files:
            error = RuntimeError("sensitive provider error")
            error.status_code = 404  # type: ignore[attr-defined]
            raise error
        return SimpleNamespace(
            content_length=self.size
            if self.size is not None
            else len(self.files[kwargs["key"]]),
            etag="etag-1",
        )

    def get_object(self, **kwargs: Any) -> Any:
        self.calls.append({"method": "GET", **kwargs})
        if kwargs["key"] not in self.files:
            error = RuntimeError("sensitive provider error")
            error.status_code = 404  # type: ignore[attr-defined]
            raise error
        content = self.files[kwargs["key"]]
        if "range_start" in kwargs:
            content = content[kwargs["range_start"] : kwargs["range_end"] + 1]
        stream = FakeObject(
            content, self.size if self.size is not None else len(content)
        )
        self.streams.append(stream)
        return stream


def access(user_id: str = "alice", bucket_path: str = "/") -> RuntimeArtifactAccess:
    return RuntimeArtifactAccess(
        user_id=user_id,
        provider="volcengine",
        region="cn-beijing",
        runtime_detail={
            "TosMountConfig": {
                "EnableTos": True,
                "MountPoints": [
                    {
                        "BucketName": "private-bucket",
                        "BucketPath": bucket_path,
                        "LocalMountPath": "/mnt/artifacts",
                        "Endpoint": "http://tos-cn-beijing.ivolces.com",
                    }
                ],
            }
        },
    )


def client_for(
    tos: FakeTos,
    *,
    denied: bool = False,
    runtime_access: RuntimeArtifactAccess | None = None,
    studio_storage: StudioStorageConfig | None = None,
    studio_client_factory: Callable[[], Any] | None = None,
) -> TestClient:
    app = FastAPI()

    async def resolve(request, runtime_id, region, app_name, session_id):
        assert (runtime_id, region, app_name, session_id) == (
            "r-one",
            "cn-beijing",
            "agent",
            "session-1",
        )
        if denied:
            raise HTTPException(status_code=403, detail="no access")
        return runtime_access or access(request.headers.get("x-user", "alice"))

    mount_routes(
        app,
        RuntimeArtifactService(
            lambda provider, region: tos,
            studio_storage=studio_storage,
            studio_client_factory=studio_client_factory,
        ),
        resolve,
    )
    return TestClient(app)


BASE = "/web/runtime-artifacts/r-one/sessions/session-1"
PARAMS = {"region": "cn-beijing", "appName": "agent"}


def test_list_uses_authenticated_user_and_mount_root_without_exposing_storage() -> None:
    tos = FakeTos()
    response = client_for(tos).get(
        BASE, params={**PARAMS, "userId": "bob", "bucket": "other"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert {item["path"] for item in data["items"]} == {"report.html", "chart.svg"}
    assert tos.calls[0]["prefix"] == "artifacts/alice/session-1/"
    assert tos.calls[0]["bucket"] == "private-bucket"
    assert "private-bucket" not in response.text
    assert "artifacts/alice" not in response.text
    assert (
        next(item for item in data["items"] if item["path"] == "report.html")[
            "mimeType"
        ]
        == "text/html"
    )


def test_subdirectory_mount_preserves_fixed_artifacts_namespace() -> None:
    tos = FakeTos()
    response = client_for(tos, runtime_access=access(bucket_path="/dedicated")).get(
        BASE, params=PARAMS
    )
    assert response.status_code == 200
    assert tos.calls[0]["prefix"] == "dedicated/artifacts/alice/session-1/"


def test_auth_denial_happens_before_storage_access() -> None:
    tos = FakeTos()
    client = client_for(tos, denied=True)
    assert client.get(BASE, params=PARAMS).status_code == 403
    assert client.get(BASE + "/content/report.html", params=PARAMS).status_code == 403
    assert tos.calls == []


def test_no_dedicated_mount_is_unavailable_instead_of_reading_another_mount() -> None:
    tos = FakeTos()
    current = RuntimeArtifactAccess(
        user_id="alice",
        provider="volcengine",
        region="cn-beijing",
        runtime_detail={
            "TosMountConfig": {
                "EnableTos": True,
                "MountPoints": [
                    {
                        "BucketName": "private-bucket",
                        "BucketPath": "/",
                        "LocalMountPath": "/mnt/other",
                    }
                ],
            }
        },
    )
    client = client_for(tos, runtime_access=current)
    listing = client.get(BASE, params=PARAMS).json()
    assert listing["available"] is False
    assert listing["reason"] == "Studio 尚未配置会话产物存储"
    content = client.get(BASE + "/content/report.html", params=PARAMS)
    assert content.status_code == 409
    assert content.json()["detail"] == "Studio 尚未配置会话产物存储"
    assert tos.calls == []


@pytest.mark.parametrize(
    "path",
    [
        "%2e%2e%2fprivate.txt",
        "%252e%252e/private.txt",
        "nested%5c..%5cprivate.txt",
        "%2fprivate.txt",
        "x%00.html",
    ],
)
def test_content_rejects_unsafe_paths(path: str) -> None:
    tos = FakeTos()
    response = client_for(tos).get(BASE + "/content/" + path, params=PARAMS)
    assert response.status_code in {400, 404}
    assert tos.calls == []


def test_content_remains_in_the_current_user_session() -> None:
    tos = FakeTos()
    response = client_for(tos).get(BASE + "/content/private.txt", params=PARAMS)
    assert response.status_code == 404
    assert "sensitive" not in response.text
    assert tos.calls[0]["key"] == "artifacts/alice/session-1/private.txt"


def test_html_stream_is_sandboxed_and_closed() -> None:
    tos = FakeTos()
    response = client_for(tos).get(BASE + "/content/report.html", params=PARAMS)
    assert response.status_code == 200
    assert response.content == tos.files["artifacts/alice/session-1/report.html"]
    assert response.headers["content-type"].startswith("text/html")
    assert "sandbox" in response.headers["content-security-policy"]
    assert "script-src 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    assert tos.streams[0].closed
    assert [call["method"] for call in tos.calls] == ["GET"]
    assert "storage_open;dur=" in response.headers["server-timing"]


def test_range_download_and_unsatisfiable_range() -> None:
    tos = FakeTos()
    client = client_for(tos)
    response = client.get(
        BASE + "/content/chart.svg",
        params={**PARAMS, "download": "true"},
        headers={"Range": "bytes=1-3"},
    )
    assert response.status_code == 206
    assert response.content == b"svg"
    assert response.headers["content-range"] == "bytes 1-3/6"
    assert response.headers["content-disposition"].startswith("attachment")
    assert [call["method"] for call in tos.calls] == ["HEAD", "GET"]
    assert tos.calls[1]["if_match"] == "etag-1"
    assert (
        client.get(
            BASE + "/content/chart.svg", params=PARAMS, headers={"Range": "bytes=9-"}
        ).status_code
        == 416
    )


def test_size_limit_closes_get_response_before_reading_the_body() -> None:
    tos = FakeTos()
    tos.size = 20 * 1024 * 1024
    response = client_for(tos).get(BASE + "/content/report.html", params=PARAMS)
    assert response.status_code == 413
    assert [call["method"] for call in tos.calls] == ["GET"]
    assert tos.streams[0].read_calls == 0
    assert tos.streams[0].closed


def test_listing_has_bounded_pagination_and_rejects_broken_provider_page() -> None:
    tos = FakeTos()
    tos.truncated = True
    tos.page_token = "next-page"
    client = client_for(tos)
    response = client.get(BASE, params={**PARAMS, "limit": 1, "cursor": "previous"})
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["nextCursor"] == "next-page"
    assert tos.calls[0]["max_keys"] == 1
    assert tos.calls[0]["continuation_token"] == "previous"
    assert client.get(BASE, params={**PARAMS, "limit": 501}).status_code == 422
    tos.page_token = ""
    assert client.get(BASE, params=PARAMS).status_code == 502


def test_provider_failure_is_not_an_empty_list_or_secret_leak() -> None:
    tos = FakeTos()
    tos.error = RuntimeError("SecretAccessKey=do-not-expose")
    response = client_for(tos).get(BASE, params=PARAMS)
    assert response.status_code == 502
    assert "do-not-expose" not in response.text


@pytest.mark.parametrize(
    "message",
    [
        "The continuation token provided is incorrect",
        "the key-marker[artifacts/alice/session-2/] does not start with "
        "prefix[artifacts/alice/session-1/].",
    ],
)
def test_invalid_or_cross_session_cursor_is_a_safe_client_error(message: str) -> None:
    from tos.exceptions import TosServerError

    tos = FakeTos()
    tos.error = TosServerError(
        SimpleNamespace(status=400, request_id="test-request", headers={}),
        message,
        "InvalidArgument",
        "storage-host",
        "private-bucket",
    )
    response = client_for(tos).get(BASE, params={**PARAMS, "cursor": "other-session"})
    assert response.status_code == 400
    assert response.json() == {
        "detail": "产物分页游标无效或不属于当前会话，请重新加载产物列表"
    }
    assert "artifacts/alice" not in response.text
    assert "private-bucket" not in response.text
    assert tos.calls[0]["continuation_token"] == "other-session"


@pytest.mark.parametrize(
    ("status", "code", "message", "cursor"),
    [
        (400, "InvalidArgument", "An unrelated storage argument is invalid", "cursor"),
        (403, "AccessDenied", "The continuation token provided is incorrect", "cursor"),
        (
            503,
            "InvalidArgument",
            "The continuation token provided is incorrect",
            "cursor",
        ),
        (400, "InvalidArgument", "The continuation token provided is incorrect", ""),
    ],
)
def test_cursor_mapping_preserves_unrelated_storage_errors(
    status: int, code: str, message: str, cursor: str
) -> None:
    from tos.exceptions import TosServerError

    tos = FakeTos()
    tos.error = TosServerError(
        SimpleNamespace(status=status, request_id="test-request", headers={}),
        message,
        code,
        "storage-host",
        "private-bucket",
    )
    response = client_for(tos).get(BASE, params={**PARAMS, "cursor": cursor})
    assert response.status_code == 502
    assert message not in response.text


def test_tos_sdk_response_wrapper_is_closed_exactly_once() -> None:
    from frontend.server.runtime_artifacts.service import ArtifactContent

    closed: list[bool] = []
    stream = SimpleNamespace(
        read=io.BytesIO(b"abc").read,
        content=SimpleNamespace(
            data=SimpleNamespace(
                resp=SimpleNamespace(close=lambda: closed.append(True))
            )
        ),
    )
    content = ArtifactContent(stream, "a.txt", "text/plain", 3, 3, None)
    assert b"".join(content.chunks()) == b"abc"
    content.close()
    assert closed == [True]


@pytest.mark.asyncio
async def test_byteplus_access_uses_its_own_provider_and_region() -> None:
    calls: list[tuple[str, str]] = []
    tos = FakeTos()

    def factory(provider: str, region: str) -> FakeTos:
        calls.append((provider, region))
        return tos

    current = access()
    current = RuntimeArtifactAccess(
        current.user_id, "byteplus", "ap-southeast-1", current.runtime_detail
    )
    await RuntimeArtifactService(factory).list(current, "session-1")
    assert calls == [("byteplus", "ap-southeast-1")]


@pytest.mark.parametrize("user_id", ["", "../bob", "alice/session-1"])
def test_unsafe_authenticated_identity_fails_before_storage(user_id: str) -> None:
    tos = FakeTos()
    response = client_for(tos, runtime_access=access(user_id)).get(BASE, params=PARAMS)
    assert response.status_code == 400
    assert tos.calls == []


@pytest.mark.parametrize("invalid_length", [None, -1, "6", True])
def test_invalid_get_length_closes_response_without_reading(
    invalid_length: object,
) -> None:
    class InvalidLengthTos(FakeTos):
        def get_object(self, **kwargs: Any) -> Any:
            stream = super().get_object(**kwargs)
            stream.content_length = invalid_length
            return stream

    tos = InvalidLengthTos()
    response = client_for(tos).get(BASE + "/content/chart.svg", params=PARAMS)
    assert response.status_code == 502
    assert tos.streams[0].closed
    assert tos.streams[0].read_calls == 0


def test_range_keeps_full_file_size_limit_before_get() -> None:
    tos = FakeTos()
    tos.size = 20 * 1024 * 1024
    response = client_for(tos).get(
        BASE + "/content/report.html", params=PARAMS, headers={"Range": "bytes=0-5"}
    )
    assert response.status_code == 413
    assert [call["method"] for call in tos.calls] == ["HEAD"]
    assert tos.streams == []


def test_mismatched_range_response_closes_before_reading() -> None:
    class IgnoredRangeTos(FakeTos):
        def get_object(self, **kwargs: Any) -> Any:
            stream = super().get_object(**kwargs)
            stream.content_length = len(self.files[kwargs["key"]])
            return stream

    tos = IgnoredRangeTos()
    response = client_for(tos).get(
        BASE + "/content/chart.svg", params=PARAMS, headers={"Range": "bytes=1-3"}
    )
    assert response.status_code == 502
    assert tos.streams[0].closed
    assert tos.streams[0].read_calls == 0


def test_tos_get_object_exposes_header_length_without_reading_body() -> None:
    from requests.structures import CaseInsensitiveDict
    from tos.models2 import GetObjectOutput

    class HeaderResponse:
        status = 200
        headers = CaseInsensitiveDict({"content-length": "3", "etag": '"etag-1"'})
        request_id = "request-1"

        def read(self, amt: int | None = None) -> bytes:
            raise AssertionError("Constructing GetObjectOutput must not read the body")

    output = GetObjectOutput(HeaderResponse(), enable_crc=True)
    assert output.content_length == 3
    assert output.etag == "etag-1"


def test_owner_directory_mount_reads_session_without_duplicate_artifacts_prefix() -> (
    None
):
    tos = FakeTos()
    client = client_for(tos, runtime_access=access(bucket_path="/artifacts/alice/"))
    listing = client.get(BASE, params=PARAMS)
    assert listing.status_code == 200
    assert {item["path"] for item in listing.json()["items"]} == {
        "report.html",
        "chart.svg",
    }
    assert tos.calls[0]["prefix"] == "artifacts/alice/session-1/"
    content = client.get(BASE + "/content/report.html", params=PARAMS)
    assert content.status_code == 200
    assert content.content == tos.files["artifacts/alice/session-1/report.html"]


def test_shared_runtime_owner_mount_cannot_be_read_by_a_different_user() -> None:
    tos = FakeTos()
    client = client_for(
        tos, runtime_access=access("bob", bucket_path="/artifacts/alice/")
    )
    assert client.get(BASE, params=PARAMS).status_code == 403
    assert client.get(BASE + "/content/report.html", params=PARAMS).status_code == 403
    assert tos.calls == []


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_unmounted_runtime_reads_studio_bucket_with_trusted_user_session(
    provider: Literal["volcengine", "byteplus"],
) -> None:
    storage = StudioStorageConfig.from_env(
        provider,
        {
            "VEADK_STUDIO_TOS_BUCKET": "studio-artifacts",
            "VEADK_STUDIO_TOS_REGION": (
                "cn-shanghai" if provider == "volcengine" else "ap-southeast-1"
            ),
        },
    )
    mounted_tos = FakeTos()
    studio_tos = FakeTos()
    studio_tos.files["artifacts/alice/session-2/other-session.txt"] = b"private"
    current = RuntimeArtifactAccess(
        "alice",
        provider,
        "cn-beijing",
        {"Tags": [{"Key": "veadk:owner", "Value": "bob"}]},
    )
    client = client_for(
        mounted_tos,
        runtime_access=current,
        studio_storage=storage,
        studio_client_factory=lambda: studio_tos,
    )
    response = client.get(BASE, params={**PARAMS, "userId": "bob", "bucket": "other"})
    assert response.status_code == 200
    assert response.json()["available"] is True
    assert {item["path"] for item in response.json()["items"]} == {
        "report.html",
        "chart.svg",
    }
    content = client.get(BASE + "/content/report.html", params=PARAMS)
    assert content.status_code == 200
    assert content.content == studio_tos.files["artifacts/alice/session-1/report.html"]
    assert "sandbox" in content.headers["content-security-policy"]
    assert content.headers["x-content-type-options"] == "nosniff"
    assert client.get(BASE + "/content/private.txt", params=PARAMS).status_code == 404
    assert (
        client.get(BASE + "/content/other-session.txt", params=PARAMS).status_code
        == 404
    )
    assert (
        client.get(BASE + "/content/%252e%252e/private.txt", params=PARAMS).status_code
        == 400
    )
    assert studio_tos.calls[0]["prefix"] == "artifacts/alice/session-1/"
    assert all(call["bucket"] == "studio-artifacts" for call in studio_tos.calls)
    assert mounted_tos.calls == []
    assert "studio-artifacts" not in response.text


def _studio_storage() -> StudioStorageConfig:
    return StudioStorageConfig.from_env(
        "volcengine",
        {
            "VEADK_STUDIO_TOS_BUCKET": "studio-artifacts",
            "VEADK_STUDIO_TOS_REGION": "cn-shanghai",
        },
    )


@pytest.mark.parametrize("bucket_path", ["/", "/artifacts/bob/"])
def test_studio_storage_takes_precedence_over_existing_runtime_mount(
    bucket_path: str,
) -> None:
    mounted_tos = FakeTos()
    studio_tos = FakeTos()
    client = client_for(
        mounted_tos,
        runtime_access=access(bucket_path=bucket_path),
        studio_storage=_studio_storage(),
        studio_client_factory=lambda: studio_tos,
    )
    assert client.get(BASE, params=PARAMS).status_code == 200
    assert client.get(BASE + "/content/chart.svg", params=PARAMS).status_code == 200
    assert all(call["bucket"] == "studio-artifacts" for call in studio_tos.calls)
    assert studio_tos.calls[0]["prefix"] == "artifacts/alice/session-1/"
    assert mounted_tos.calls == []


def test_studio_storage_does_not_bypass_runtime_authorization() -> None:
    tos = FakeTos()
    client = client_for(
        tos,
        denied=True,
        runtime_access=RuntimeArtifactAccess("alice", "volcengine", "cn-beijing", {}),
        studio_storage=_studio_storage(),
        studio_client_factory=lambda: pytest.fail(
            "Unauthorized access must not read Studio storage"
        ),
    )
    assert client.get(BASE, params=PARAMS).status_code == 403
    assert client.get(BASE + "/content/report.html", params=PARAMS).status_code == 403
    assert tos.calls == []


@pytest.mark.parametrize("mounted", [False, True])
def test_studio_storage_errors_do_not_fall_back_and_preview_limits_remain(
    mounted: bool,
) -> None:
    tos = FakeTos()
    mounted_tos = FakeTos()
    current = (
        access()
        if mounted
        else RuntimeArtifactAccess("alice", "volcengine", "cn-beijing", {})
    )
    client = client_for(
        mounted_tos,
        runtime_access=current,
        studio_storage=_studio_storage(),
        studio_client_factory=lambda: tos,
    )
    from tos.exceptions import TosServerError

    tos.error = TosServerError(
        SimpleNamespace(status=403, request_id="test-request", headers={}),
        "private credentials",
        "AccessDenied",
        "private-host",
        "studio-artifacts",
    )
    denied = client.get(BASE, params=PARAMS)
    assert denied.status_code == 502
    assert "private credentials" not in denied.text
    tos.error = None
    tos.size = 20 * 1024 * 1024
    assert client.get(BASE + "/content/report.html", params=PARAMS).status_code == 413
    assert tos.streams[0].closed
    assert tos.streams[0].read_calls == 0
    assert mounted_tos.calls == []


def test_unmounted_runtime_rejects_a_different_studio_provider() -> None:
    tos = FakeTos()
    client = client_for(
        tos,
        runtime_access=RuntimeArtifactAccess("alice", "byteplus", "ap-southeast-1", {}),
        studio_storage=_studio_storage(),
        studio_client_factory=lambda: pytest.fail(
            "Wrong provider must not read storage"
        ),
    )
    assert client.get(BASE, params=PARAMS).status_code == 409
    assert tos.calls == []


@pytest.mark.parametrize("user_id", ["", "../bob", "alice/session-1"])
def test_studio_storage_rejects_unsafe_authenticated_identity(user_id: str) -> None:
    tos = FakeTos()
    client = client_for(
        tos,
        runtime_access=RuntimeArtifactAccess(user_id, "volcengine", "cn-beijing", {}),
        studio_storage=_studio_storage(),
        studio_client_factory=lambda: pytest.fail(
            "Invalid identity must not reach storage"
        ),
    )
    assert client.get(BASE, params=PARAMS).status_code == 400
    assert tos.calls == []


def test_unconfigured_studio_storage_keeps_native_mount_compatibility() -> None:
    tos = FakeTos()
    client = client_for(
        tos,
        studio_storage=StudioStorageConfig.from_env("volcengine", {}),
        studio_client_factory=lambda: pytest.fail(
            "Unconfigured Studio storage must not be used"
        ),
    )
    assert client.get(BASE, params=PARAMS).status_code == 200
    assert tos.calls[0]["bucket"] == "private-bucket"


def test_partial_studio_storage_config_does_not_fall_back_to_runtime_mount() -> None:
    tos = FakeTos()
    client = client_for(
        tos,
        studio_storage=StudioStorageConfig.from_env(
            "volcengine", {"VEADK_STUDIO_TOS_BUCKET": "studio-artifacts"}
        ),
    )
    assert client.get(BASE, params=PARAMS).status_code == 409
    assert tos.calls == []
