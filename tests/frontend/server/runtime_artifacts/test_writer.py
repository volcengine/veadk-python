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

import hashlib
import json
import sys
import traceback
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from veadk.utils.cloud_provider import CloudProvider

from frontend.server.runtime_artifacts import writer as writer_module
from frontend.server.runtime_artifacts.writer import (
    ARTIFACT_WRITE_MAX_BYTES,
    StudioArtifactWriter,
)
from frontend.server.storage import StudioStorageConfig
from frontend.server.studio_tools.extensions.artifacts import register_tools
from frontend.server.studio_tools.registry import (
    StudioToolExecutionContext,
    StudioToolExecutionError,
    StudioToolRegistry,
    StudioToolRuntimeError,
)


def context(**changes: Any) -> StudioToolExecutionContext:
    return replace(
        StudioToolExecutionContext(
            runtime_id="runtime-1",
            app_name="agent",
            user_id="alice",
            owner_id="alice",
            session_id="session-1",
            run_id="run-1",
            scope_id="scope-1",
            catalog_revision="catalog-1",
        ),
        **changes,
    )


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for prefix in ("VOLCENGINE", "BYTEPLUS"):
        for suffix in ("ACCESS_KEY", "SECRET_KEY", "SESSION_TOKEN"):
            monkeypatch.delenv(f"{prefix}_{suffix}", raising=False)
    monkeypatch.delenv("VOLC_SESSIONTOKEN", raising=False)
    credential_path = tmp_path / "iam-credential"
    monkeypatch.setattr(writer_module, "_IAM_CREDENTIAL_PATH", credential_path)
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("VEADK_STUDIO_TOS_BUCKET", "studio-test-bucket")
    monkeypatch.setenv("VEADK_STUDIO_TOS_REGION", "cn-beijing")
    return credential_path


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(clients=[], puts=[], error=None, init_error=None)

    class Client:
        def __init__(self, **options: Any) -> None:
            if state.init_error:
                raise state.init_error
            self.options = options
            state.clients.append(self)

        def put_object(self, **options: Any) -> None:
            if state.error:
                raise state.error
            state.puts.append(options)

    monkeypatch.setitem(sys.modules, "tos", SimpleNamespace(TosClientV2=Client))
    return state


@pytest.fixture
def writer(storage: SimpleNamespace) -> StudioArtifactWriter:
    return StudioArtifactWriter(
        StudioStorageConfig(
            "volcengine", "studio-test-bucket", "cn-beijing", "storage.example.test"
        ),
        lambda: ("test-ak", "test-sk", "test-token"),
    )


@pytest.mark.asyncio
async def test_registered_tool_has_only_content_arguments_and_requires_context(
    monkeypatch: pytest.MonkeyPatch, storage: SimpleNamespace
) -> None:
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "test-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "test-sk")
    monkeypatch.setenv("VOLCENGINE_SESSION_TOKEN", "test-token")
    registry = StudioToolRegistry()
    register_tools(registry)
    snapshot = registry.snapshot(["studio_write_artifact"])
    manifest = snapshot.manifests()[0]
    schema = manifest["input_schema"]
    assert set(schema["properties"]) == {"path", "content"}
    assert set(schema["required"]) == {"path", "content"}
    assert schema["additionalProperties"] is False
    assert snapshot.public_items()[0]["name"] == "保存会话产物"
    arguments = {"path": "report/summary.md", "content": "会话报告\n"}
    with pytest.raises(StudioToolExecutionError, match="requires an execution context"):
        await snapshot.execute(
            name="studio_write_artifact",
            executor_revision=manifest["executor_revision"],
            arguments=arguments,
        )
    assert storage.clients == []
    result = await snapshot.execute(
        name="studio_write_artifact",
        executor_revision=manifest["executor_revision"],
        arguments=arguments,
        context=context(),
    )
    assert result["status"] == "saved"
    assert storage.puts[0]["key"] == "artifacts/alice/session-1/report/summary.md"
    assert storage.clients[-1].options["security_token"] == "test-token"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field", ["user_id", "owner_id", "session_id", "bucket", "key", "runtime_id"]
)
async def test_schema_and_writer_reject_identity_or_storage_overrides(
    field: str, writer: StudioArtifactWriter, storage: SimpleNamespace
) -> None:
    registry = StudioToolRegistry()
    register_tools(registry)
    arguments = {"path": "report.md", "content": "safe", field: "attacker"}
    with pytest.raises(StudioToolExecutionError, match="Invalid arguments"):
        await registry.execute(
            name="studio_write_artifact",
            executor_revision="studio-artifacts-v1",
            arguments=arguments,
            context=context(),
        )
    with pytest.raises(StudioToolExecutionError):
        writer.write(arguments, context())
    assert storage.clients == []


@pytest.mark.parametrize(
    "changes",
    [
        {"owner_id": ""},
        {"owner_id": "bob"},
        {"user_id": "bob"},
        {"owner_id": "../alice", "user_id": "../alice"},
        {"owner_id": "alice/other", "user_id": "alice/other"},
        {"session_id": "../other"},
        {"session_id": ""},
        {"session_id": "one/two"},
    ],
)
def test_invalid_server_identity_cannot_reach_storage(
    changes: dict[str, str], writer: StudioArtifactWriter, storage: SimpleNamespace
) -> None:
    with pytest.raises(StudioToolExecutionError):
        writer.write({"path": "report.md", "content": "safe"}, context(**changes))
    assert storage.clients == []


@pytest.mark.parametrize(
    "path",
    [
        "",
        ".",
        "../secret",
        "/private.txt",
        "a/../b",
        "a//b",
        "a\\b",
        "a/",
        "%2e%2e/x",
        "a%252fb",
        "a\x00b",
        "a\x7fb",
        "文" * 342,
    ],
)
def test_unsafe_paths_are_rejected_before_storage(
    path: str, writer: StudioArtifactWriter, storage: SimpleNamespace
) -> None:
    with pytest.raises(StudioToolExecutionError):
        writer.write({"path": path, "content": "safe"}, context())
    assert storage.clients == []


def test_success_uses_trusted_scope_and_hashes_utf8_bytes(
    writer: StudioArtifactWriter, storage: SimpleNamespace
) -> None:
    content = "# 报告\n完成 ✓\n"
    encoded = content.encode("utf-8")
    result = writer.write({"path": "reports/summary.md", "content": content}, context())
    assert storage.puts == [
        {
            "bucket": "studio-test-bucket",
            "key": "artifacts/alice/session-1/reports/summary.md",
            "content": encoded,
            "content_type": "text/markdown",
        }
    ]
    assert result == {
        "status": "saved",
        "artifact": {
            "path": "reports/summary.md",
            "name": "summary.md",
            "mimeType": "text/markdown",
            "size": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        },
    }
    assert "test-token" not in json.dumps(result)
    assert "studio-test-bucket" not in json.dumps(result)
    writer.write(
        {"path": "reports/summary.md", "content": "next"},
        context(session_id="session-2"),
    )
    assert storage.puts[-1]["key"] == "artifacts/alice/session-2/reports/summary.md"


def test_utf8_byte_limit_accepts_exact_boundary(
    writer: StudioArtifactWriter, storage: SimpleNamespace
) -> None:
    content = "你" * (ARTIFACT_WRITE_MAX_BYTES // 3) + "a"
    result = writer.write({"path": "report.txt", "content": content}, context())
    assert result["artifact"]["size"] == ARTIFACT_WRITE_MAX_BYTES
    assert len(storage.puts[0]["content"]) == ARTIFACT_WRITE_MAX_BYTES


@pytest.mark.parametrize(
    "content",
    [
        "x" * (ARTIFACT_WRITE_MAX_BYTES + 1),
        "你" * (ARTIFACT_WRITE_MAX_BYTES // 3 + 1),
        "bad\ud800text",
    ],
)
def test_oversized_or_invalid_utf8_content_never_reaches_storage(
    content: str, writer: StudioArtifactWriter, storage: SimpleNamespace
) -> None:
    with pytest.raises(StudioToolExecutionError):
        writer.write({"path": "report.txt", "content": content}, context())
    assert storage.clients == []


@pytest.mark.parametrize("failure", ["error", "init_error"])
def test_storage_errors_do_not_expose_provider_secrets(
    failure: str,
    writer: StudioArtifactWriter,
    storage: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "authorization=private-signature&security_token=private-token"
    setattr(storage, failure, RuntimeError(secret))
    with pytest.raises(StudioToolRuntimeError, match="产物保存失败") as caught:
        writer.write({"path": "report.txt", "content": "safe"}, context())
    assert secret not in "".join(traceback.format_exception(caught.value))
    assert secret not in caplog.text
    assert storage.puts == []


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
@pytest.mark.parametrize("style", ["snake", "pascal"])
def test_role_token_is_preserved_rotated_and_never_reused_after_missing_credentials(
    provider: str,
    style: str,
    isolated_environment: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage: SimpleNamespace,
) -> None:
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", provider)
    monkeypatch.setenv(
        "VEADK_STUDIO_TOS_REGION",
        "ap-southeast-1" if provider == "byteplus" else "cn-beijing",
    )
    keys = (
        ("access_key_id", "secret_access_key", "session_token")
        if style == "snake"
        else ("AccessKeyId", "SecretAccessKey", "SessionToken")
    )

    def credentials(token: str) -> None:
        isolated_environment.write_text(
            json.dumps(dict(zip(keys, ("role-ak", "role-sk", token))))
        )

    credentials("role-token-1")
    writer = StudioArtifactWriter.from_env()
    arguments = {"path": "report.txt", "content": "safe"}
    writer.write(arguments, context())
    first_client = storage.clients[-1]
    first_count = len(storage.clients)
    assert first_client.options["security_token"] == "role-token-1"
    assert first_client.options["ak"] == "role-ak"
    assert first_client.options["sk"] == "role-sk"
    assert first_client.options["endpoint"].endswith(
        "bytepluses.com" if provider == "byteplus" else "volces.com"
    )
    writer.write(arguments, context())
    assert len(storage.clients) == first_count
    credentials("role-token-2")
    writer.write(arguments, context())
    assert storage.clients[-1] is not first_client
    assert storage.clients[-1].options["security_token"] == "role-token-2"
    isolated_environment.unlink()
    with pytest.raises(StudioToolRuntimeError, match="角色凭据不可用"):
        writer.write(arguments, context())
    assert len(storage.puts) == 3


@pytest.mark.parametrize(
    "provider,prefix,token_key",
    [
        ("volcengine", "VOLCENGINE", "VOLCENGINE_SESSION_TOKEN"),
        ("volcengine", "VOLCENGINE", "VOLC_SESSIONTOKEN"),
        ("byteplus", "BYTEPLUS", "BYTEPLUS_SESSION_TOKEN"),
    ],
)
def test_environment_sts_credentials_retain_the_token(
    provider: CloudProvider,
    prefix: str,
    token_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(f"{prefix}_ACCESS_KEY", "env-ak")
    monkeypatch.setenv(f"{prefix}_SECRET_KEY", "env-sk")
    monkeypatch.setenv(token_key, "env-token")
    assert writer_module._resolve_credentials(provider) == (
        "env-ak",
        "env-sk",
        "env-token",
    )


@pytest.mark.parametrize(
    "document",
    [
        None,
        "not-json private-token",
        "[]",
        '{"AccessKeyId":"private-ak"}',
        '{"AccessKeyId":"private-ak","SecretAccessKey":"private-sk"}',
    ],
)
def test_missing_or_malformed_role_credentials_fail_safely(
    document: str | None, isolated_environment: Path
) -> None:
    if document is not None:
        isolated_environment.write_text(document)
    with pytest.raises(StudioToolRuntimeError, match="角色凭据不可用") as caught:
        writer_module._resolve_credentials("volcengine")
    assert "private-" not in "".join(traceback.format_exception(caught.value))


def test_partial_environment_credentials_fail_without_role_fallback(
    monkeypatch: pytest.MonkeyPatch, isolated_environment: Path
) -> None:
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "private-ak")
    isolated_environment.write_text(
        json.dumps(
            {
                "AccessKeyId": "role-ak",
                "SecretAccessKey": "role-sk",
                "SessionToken": "role-token",
            }
        )
    )
    with pytest.raises(StudioToolRuntimeError, match="凭据不完整") as caught:
        writer_module._resolve_credentials("volcengine")
    assert "private-ak" not in str(caught.value)


def test_unconfigured_storage_fails_before_resolving_credentials(
    storage: SimpleNamespace,
) -> None:
    def unexpected_credentials() -> tuple[str, str, str | None]:
        pytest.fail("Unconfigured storage must not request credentials")

    writer = StudioArtifactWriter(
        StudioStorageConfig("volcengine", "", "", ""), unexpected_credentials
    )
    with pytest.raises(StudioToolRuntimeError, match="尚未配置产物存储"):
        writer.write({"path": "report.md", "content": "safe"}, context())
    assert storage.clients == []
