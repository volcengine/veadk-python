from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "scripts" / "mpa_p0_vc21_driver.py"


def _driver_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mpa_p0_vc21_driver", DRIVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_isolated_runtime_env_replaces_all_shared_identities() -> None:
    module = _driver_module()

    result = module.isolated_runtime_env(
        {
            "MPA_AGENT_ID": "mi-source",
            "CLAW_SPACE_ID": "csi-source",
            "PGDATABASE": "shared",
            "A2A_PUBLIC_URL": "https://source.example",
            "CODEX_MCP_RUNTIME_API_KEY": "source-key",
            "OTEL_SERVICE_NAME": "source-service",
            "OTEL_RESOURCE_ATTRIBUTES": "service.name=source,tenant=source",
            "MODEL_AGENT_API_KEY": "must-be-preserved-in-memory",
        },
        mpa_instance_id="mi-e2e-run-1",
        database_name="mpa_p0_e2e_run_1",
        runtime_name="mpa-p0-e2e-run-1",
        tool_id="t-isolated",
    )

    assert result["MPA_AGENT_ID"] == "mi-e2e-run-1"
    assert result["CLAW_SPACE_ID"] == "mi-e2e-run-1"
    assert result["PGDATABASE"] == "mpa_p0_e2e_run_1"
    assert result["A2A_PUBLIC_URL"] == "https://pending.invalid"
    assert result["CODEX_MCP_RUNTIME_API_KEY"] == "pending"
    assert result["OTEL_SERVICE_NAME"] == "mpa-p0-e2e-run-1"
    assert result["MPA_CODEX_WORKER_TOOL_AUTH_MODE"] == "openapi"
    assert result["OTEL_RESOURCE_ATTRIBUTES"] == (
        "service.name=mpa-p0-e2e-run-1,mpa.instance.id=mi-e2e-run-1"
    )
    assert result["AGENTKIT_TOOL_ID"] == "t-isolated"
    assert result["MPA_CODEX_WORKER_TOOL_ID"] == "t-isolated"
    assert result["MODEL_AGENT_API_KEY"] == "must-be-preserved-in-memory"


def test_resources_track_isolated_tool_between_database_and_runtime() -> None:
    module = _driver_module()

    result = module._resources(
        {
            "databaseName": "mpa_p0_e2e_run_1",
            "toolId": "t-isolated",
            "toolName": "mpa-p0-e2e-run-1-worker",
            "runtimeId": "r-isolated",
            "region": "cn-beijing",
        }
    )

    assert [item["type"] for item in result] == [
        "postgres_database",
        "tool",
        "runtime",
    ]
    assert result[1] == {
        "type": "tool",
        "id": "t-isolated",
        "name": "mpa-p0-e2e-run-1-worker",
        "region": "cn-beijing",
    }


def test_tool_runtime_association_requires_the_expected_runtime_id() -> None:
    module = _driver_module()
    tool = SimpleNamespace(
        associated_runtimes=[
            SimpleNamespace(id="r-source"),
            SimpleNamespace(id="r-isolated"),
        ]
    )

    assert module._tool_has_runtime(tool, "r-isolated") is True
    assert module._tool_has_runtime(tool, "r-other") is False


def test_tool_runtime_association_waits_for_permission_propagation() -> None:
    module = _driver_module()

    assert module._tool_association_stable(
        {"toolRuntimeAssociationObservedAt": 100},
        now=129,
    ) is False
    assert module._tool_association_stable(
        {"toolRuntimeAssociationObservedAt": 100},
        now=130,
    ) is True


def test_safe_evidence_keeps_ids_and_status_but_removes_credentials() -> None:
    module = _driver_module()

    result = module.safe_evidence(
        {
            "runtimeId": "r-test",
            "operationId": "op-test",
            "requestId": "req-test",
            "status": "Ready",
            "version": 3,
            "authorization": "Bearer secret",
            "envs": [{"key": "PGPASSWORD", "value": "secret"}],
            "nested": {"apiKey": "secret", "status": "passed"},
        }
    )

    assert result == {
        "runtimeId": "r-test",
        "operationId": "op-test",
        "requestId": "req-test",
        "status": "Ready",
        "version": 3,
        "nested": {"status": "passed"},
    }


def test_compatibility_fence_covers_valid_incompatible_and_malformed() -> None:
    module = _driver_module()

    result = module.compatibility_fence(
        veadk_revision="a" * 40,
        runtime_revision="b" * 40,
        runtime_image_digest="sha256:" + "c" * 64,
    )

    assert result["valid"]["status"] == "compatible"
    assert result["incompatible"] == {
        "errorCode": "worker_protocol_incompatible",
        "status": "incompatible",
    }
    assert result["malformed"] == {
        "errorCode": "invalid_runtime_image_digest",
        "status": "invalid_manifest",
    }


def test_runtime_artifact_url_comes_from_live_manifest_not_source_runtime() -> None:
    module = _driver_module()

    assert (
        module.runtime_artifact_url(
            {
                "runtimeImageUrl": (
                    "registry.example.com/agentkit/mpa_agent:vc21-build"
                )
            }
        )
        == "registry.example.com/agentkit/mpa_agent:vc21-build"
    )


def test_same_runtime_artifact_matches_tag_and_digest_forms() -> None:
    module = _driver_module()

    assert module._same_runtime_artifact(
        "registry.example.com/agentkit/mpa_agent:vc21-build@sha256:" + "a" * 64,
        "registry.example.com/agentkit/mpa_agent:vc21-build",
    )
    assert not module._same_runtime_artifact(
        "registry.example.com/agentkit/mpa_agent:other",
        "registry.example.com/agentkit/mpa_agent:vc21-build",
    )


def test_rollback_skips_release_when_current_runtime_already_uses_target_artifact(
    monkeypatch,
) -> None:
    module = _driver_module()

    class _GetRuntimeRequest:
        def __init__(self, **kwargs: object) -> None:
            self.__dict__.update(kwargs)
            self.RuntimeId = kwargs.get("RuntimeId") or kwargs.get("runtime_id")

    class _ReleaseRuntimeRequest:
        def __init__(self, **kwargs: object) -> None:
            self.__dict__.update(kwargs)

    class _RuntimeClient:
        def __init__(self) -> None:
            self.release_calls = 0

        def get_runtime(self, request: object) -> SimpleNamespace:
            assert request.runtime_id == "r-isolated"
            return SimpleNamespace(
                runtime_id="r-isolated",
                status="Ready",
                current_version_number=3,
                artifact_url=(
                    "registry.example.com/agentkit/mpa_agent:vc21-build@"
                    + "sha256:"
                    + "a" * 64
                ),
            )

        def release_runtime(self, request: object) -> None:
            self.release_calls += 1

    client = _RuntimeClient()
    records: list[dict[str, object]] = []
    monkeypatch.setitem(
        sys.modules,
        "agentkit.sdk.runtime.types",
        SimpleNamespace(
            GetRuntimeRequest=_GetRuntimeRequest,
            ReleaseRuntimeRequest=_ReleaseRuntimeRequest,
        ),
    )
    monkeypatch.setattr(module, "_runtime_client", lambda region: client)
    monkeypatch.setattr(
        module,
        "_smoke",
        lambda state, suffix: {"status": "passed", "operationId": suffix},
    )
    monkeypatch.setattr(module, "_save_state", lambda state: None)
    monkeypatch.setattr(
        module,
        "_record",
        lambda state, stage, **payload: records.append(
            {"stage": stage, **payload}
        ),
    )

    state = {
        "region": "cn-beijing",
        "runtimeId": "r-isolated",
        "baselineVersion": 2,
    }
    result = module._stage_rollback(
        state,
        {
            "runtimeImageUrl": "registry.example.com/agentkit/mpa_agent:vc21-build"
        },
    )

    assert result == {
        "status": "passed",
        "resources": [
            {
                "id": "r-isolated",
                "region": "cn-beijing",
                "type": "runtime",
            }
        ],
    }
    assert client.release_calls == 0
    assert state["rollbackRequested"] is True
    assert records == [
        {
            "stage": "VC21-COMPATIBLE-ROLLBACK",
            "event": "rollback_ready",
            "version": 3,
            "targetVersion": 2,
            "noRollbackNeeded": True,
            "reason": "already_on_target_artifact",
            "smoke": {"status": "passed", "operationId": "rollback-smoke"},
        }
    ]


def test_runtime_log_diagnostics_keep_only_safe_classifications() -> None:
    module = _driver_module()

    result = module.classify_runtime_logs(
        """
execution smoke Worker stage failed stage=sandbox_prepare safe_code=unclassified
operation finished code=smoke_worker_sandbox_prepare_failed
AgentKit Sandbox API failed action=create_session tool_auth_mode=openapi provider_code=resource_not_found error_type=ApiError
	execution smoke Worker detail sandbox_stage=ready_probe http_status=404 worker_phase=init
Traceback (most recent call last):
agentkit.toolkit.errors.ApiError: Failed: {"Error":{"Code":"AccessDenied","Message":"https://signed.example/?token=secret"}}
app.integrations.agentkit_sandbox.CodexSandboxUnavailable: private sandbox endpoint is unavailable
"""
    )

    assert result == {
        "providerCodes": ["AccessDenied"],
        "exceptionTypes": ["ApiError", "CodexSandboxUnavailable"],
	        "httpStatuses": ["404"],
        "knownReasons": ["endpoint_unavailable", "permission_denied"],
	        "sandboxStages": ["ready_probe"],
        "toolApiActions": ["create_session"],
        "toolAuthModes": ["openapi"],
        "toolProviderCodes": ["resource_not_found"],
	        "workerPhases": ["init"],
        "workerStages": ["sandbox_prepare"],
    }
    assert "secret" not in str(result)
    assert "smoke_worker_sandbox_prepare_failed" not in result["providerCodes"]


def test_runtime_log_diagnostics_read_at_most_1000_lines_per_instance(
    monkeypatch,
) -> None:
    module = _driver_module()
    requests: list[object] = []

    class _ListRequest:
        def __init__(self, **kwargs: object) -> None:
            self.__dict__.update(kwargs)

    class _LogsRequest:
        def __init__(self, **kwargs: object) -> None:
            self.__dict__.update(kwargs)

    class _Client:
        def list_runtime_instances(self, request: object) -> SimpleNamespace:
            requests.append(request)
            return SimpleNamespace(
                instance_items=[SimpleNamespace(instance_name="instance-1")]
            )

        def get_runtime_instance_logs(self, request: object) -> SimpleNamespace:
            requests.append(request)
            return SimpleNamespace(
                logs=(
                    "stage=ready ApiError: \"Code\":\"AccessDenied\" "
                    "token=must-not-persist"
                )
            )

    monkeypatch.setitem(
        sys.modules,
        "agentkit.sdk.runtime.types",
        SimpleNamespace(
            ListRuntimeInstancesRequest=_ListRequest,
            GetRuntimeInstanceLogsRequest=_LogsRequest,
        ),
    )

    result = module._collect_runtime_log_diagnostics(_Client(), "runtime-1")

    assert result == {
        "providerCodes": ["AccessDenied"],
        "exceptionTypes": ["ApiError"],
	        "httpStatuses": [],
        "knownReasons": ["permission_denied"],
	        "sandboxStages": [],
        "toolApiActions": [],
        "toolAuthModes": [],
        "toolProviderCodes": [],
	        "workerPhases": [],
        "workerStages": ["ready"],
    }
    assert requests[0].runtime_id == "runtime-1"
    assert requests[1].runtime_id == "runtime-1"
    assert requests[1].instance_name == "instance-1"
    assert requests[1].limit == 1000
    assert "must-not-persist" not in str(result)
