# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

import itertools
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server import deployment_resources


class _FakeResourceService:
    def __init__(
        self,
        provider: str,
        region: str,
        credentials: deployment_resources.CloudCredentials | None = None,
    ) -> None:
        self.provider = provider
        self.region = region
        self.credentials = credentials
        self.calls: list[tuple[str, dict[str, str]]] = []

    def list_resources(self, kind: str, **parents: str) -> dict[str, Any]:
        self.calls.append((kind, parents))
        return {
            "serviceRegion": "cn-beijing",
            "items": [{"id": "resource-id", "name": "resource-name"}],
        }


def test_deployment_resource_route_passes_provider_region_and_parents(
    monkeypatch,
) -> None:
    services: list[_FakeResourceService] = []

    def service(
        provider: str,
        region: str,
        credentials: deployment_resources.CloudCredentials | None = None,
    ) -> _FakeResourceService:
        instance = _FakeResourceService(provider, region, credentials)
        services.append(instance)
        return instance

    monkeypatch.setattr(deployment_resources, "DeploymentResourceService", service)
    app = FastAPI()
    deployment_resources.mount_deployment_resource_routes(
        app,
        authorize=lambda _request: None,
        provider="byteplus",
        resolve_credentials=lambda: ("ak", "sk", "token"),
    )

    response = TestClient(app).get(
        "/web/deployment-resources",
        params={
            "kind": "cp-pipeline",
            "region": "ap-southeast-1",
            "workspaceId": "workspace-id",
        },
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "resource-name"
    assert services[0].provider == "byteplus"
    assert services[0].region == "ap-southeast-1"
    assert services[0].credentials == ("ak", "sk", "token")
    assert services[0].calls == [
        (
            "cp-pipeline",
            {
                "registry": "",
                "namespace": "",
                "workspace_id": "workspace-id",
                "search": "",
                "page_number": 1,
                "page_size": 100,
            },
        )
    ]


@pytest.mark.parametrize(
    "provider,region,expected_host",
    [
        ("volcengine", "cn-beijing", "open.volcengineapi.com"),
        (
            "byteplus",
            "ap-southeast-1",
            "cp.ap-southeast-1.byteplusapi.com",
        ),
    ],
)
def test_code_pipeline_client_uses_provider_specific_product_endpoint(
    provider: str,
    region: str,
    expected_host: str,
) -> None:
    service = deployment_resources.DeploymentResourceService(
        provider,
        region,
        ("access-key", "secret-key", "session-token"),
    )

    client = service._cp_client()

    assert client.host == expected_host
    assert client.region == region


def test_deployment_resource_route_preserves_exception_chain_and_redacts_credentials(
    monkeypatch,
) -> None:
    class _FailingResourceService:
        def __init__(
            self,
            _provider: str,
            _region: str,
            _credentials: deployment_resources.CloudCredentials | None = None,
        ) -> None:
            pass

        def list_resources(self, _kind: str, **_parents: str) -> dict[str, Any]:
            try:
                raise ValueError(
                    "SDK original error: RequestId=request-123, credential=secret-ak-123"
                )
            except ValueError as error:
                raise RuntimeError("resource wrapper failed") from error

    monkeypatch.setattr(
        deployment_resources,
        "DeploymentResourceService",
        _FailingResourceService,
    )
    app = FastAPI()
    deployment_resources.mount_deployment_resource_routes(
        app,
        authorize=lambda _request: None,
        provider="byteplus",
        resolve_credentials=lambda: ("secret-ak-123", "secret-sk-456", None),
    )

    response = TestClient(app).get(
        "/web/deployment-resources",
        params={"kind": "tos-bucket", "region": "ap-southeast-1"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "resource wrapper failed\nCaused by:\n"
        "SDK original error: RequestId=request-123, credential=***"
    )


def test_cr_error_keeps_complete_original_response() -> None:
    response = {
        "ResponseMetadata": {
            "RequestId": "request-123",
            "Action": "ListRegistries",
            "Error": {
                "Code": "AccessDenied",
                "Message": "permission denied",
            },
        },
        "OriginalBody": {"trace": "cloud-trace-456"},
    }
    client = SimpleNamespace(
        _ve_request=lambda **_kwargs: response,
    )

    with pytest.raises(ValueError) as exc_info:
        deployment_resources._cr_page(client, "ListRegistries", 1, 10)

    detail = str(exc_info.value)
    assert "ListRegistries failed" in detail
    assert "AccessDenied" in detail
    assert "permission denied" in detail
    assert "request-123" in detail
    assert "cloud-trace-456" in detail


def test_resolve_deployment_resources_maps_custom_names() -> None:
    service = object.__new__(deployment_resources.DeploymentResourceService)

    assert service.resolve_deployment_config(
        {
            "tos": {"mode": "create", "bucket": "source-bucket"},
            "cr": {
                "mode": "create",
                "instance": "registry-a",
                "namespace": "namespace-a",
                "repository": "repository-a",
            },
            "codePipeline": {
                "mode": "create",
                "workspaceName": "workspace-a",
                "pipelineName": "pipeline-a",
            },
        },
        validate_existing=False,
    ) == {
        "tos_bucket": "source-bucket",
        "cr_instance_name": "registry-a",
        "cr_namespace_name": "namespace-a",
        "cr_repo_name": "repository-a",
        "cp_workspace_name": "workspace-a",
        "cp_pipeline_name": "pipeline-a",
    }


def _managed_sidecar_resource_service() -> (
    deployment_resources.DeploymentResourceService
):
    service = object.__new__(deployment_resources.DeploymentResourceService)
    service.provider = "volcengine"
    service.region = "cn-shanghai"
    service.credentials = None
    service._tos = None
    service._cr = cast(
        Any,
        SimpleNamespace(
            region="cn-shanghai",
            list_registries=lambda _page, _size: {
                "Items": [
                    {"Name": "unrelated", "Status": {"Phase": "Running"}},
                    {"Name": "managed", "Status": {"Phase": "Running"}},
                ],
                "TotalCount": 2,
            },
            _list_domains=lambda registry: [
                {
                    "Domain": (
                        "managed.example.internal"
                        if registry == "managed"
                        else "unrelated.example.internal"
                    ),
                    "Default": True,
                }
            ],
            list_namespaces=lambda registry, _page, _size: {
                "Items": ([{"Name": "sidecar"}] if registry == "managed" else []),
                "TotalCount": 1 if registry == "managed" else 0,
            },
        ),
    )
    service._cp = None
    return service


def test_managed_sidecar_auto_cr_anchors_to_base_image_registry() -> None:
    service = _managed_sidecar_resource_service()

    assert service.anchor_managed_sidecar_registry(
        "managed.example.internal/sidecar/runtime@sha256:test-only",
        {},
    ) == {
        "cr_instance_name": "managed",
        "cr_namespace_name": "sidecar",
    }


@pytest.mark.parametrize(
    "config",
    [
        {},
        {
            "cr_instance_name": "customer-registry",
            "cr_namespace_name": "agentkit",
            "cr_repo_name": "customer-agent",
        },
    ],
)
def test_managed_sidecar_public_base_keeps_customer_application_cr(
    config: dict[str, str],
) -> None:
    service = _managed_sidecar_resource_service()

    assert (
        service.anchor_managed_sidecar_registry(
            "platform-public.example.invalid/sidecar/runtime@sha256:test-only",
            config,
        )
        == config
    )


@pytest.mark.parametrize(
    "config",
    [
        {"cr_instance_name": "unrelated"},
        {
            "cr_instance_name": "managed",
            "cr_namespace_name": "application",
        },
    ],
)
def test_managed_sidecar_rejects_explicit_cr_conflict(
    config: dict[str, str],
) -> None:
    service = _managed_sidecar_resource_service()

    with pytest.raises(
        deployment_resources.ManagedSidecarRegistryError,
        match="所选 CR 与受控 Harness Sidecar 基础镜像不在同一实例和命名空间",
    ):
        service.anchor_managed_sidecar_registry(
            "managed.example.internal/sidecar/runtime:test-only",
            config,
        )


def test_managed_sidecar_registry_errors_do_not_echo_private_image() -> None:
    service = _managed_sidecar_resource_service()
    private_reference = "not-a-registry-reference"

    with pytest.raises(deployment_resources.ManagedSidecarRegistryError) as exc_info:
        service.anchor_managed_sidecar_registry(private_reference, {})

    assert private_reference not in str(exc_info.value)


def test_tos_list_only_returns_buckets_in_the_service_region() -> None:
    service = object.__new__(deployment_resources.DeploymentResourceService)
    service.provider = "volcengine"
    service.region = "cn-shanghai"
    service.credentials = None
    service._tos = cast(
        Any,
        SimpleNamespace(
            actual_region="cn-shanghai",
            list_buckets=lambda: [
                {"Name": "shanghai-bucket", "Location": "cn-shanghai"},
                {"Name": "beijing-bucket", "Location": "cn-beijing"},
            ],
        ),
    )
    service._cr = None
    service._cp = None

    assert service.list_resources("tos-bucket") == {
        "serviceRegion": "cn-shanghai",
        "pageNumber": 1,
        "pageSize": 100,
        "totalCount": 1,
        "hasMore": False,
        "items": [
            {
                "id": "shanghai-bucket",
                "name": "shanghai-bucket",
                "region": "cn-shanghai",
                "status": "",
            }
        ],
    }


def test_tos_list_supports_current_agentkit_service_shape() -> None:
    service = object.__new__(deployment_resources.DeploymentResourceService)
    service.provider = "volcengine"
    service.region = "cn-beijing"
    service.credentials = ("ak", "sk", None)
    service._tos = cast(
        Any,
        SimpleNamespace(
            actual_region="cn-beijing",
            client=SimpleNamespace(
                list_buckets=lambda: SimpleNamespace(
                    buckets=[SimpleNamespace(name="bucket-a", location="cn-beijing")]
                )
            ),
        ),
    )
    service._cr = None
    service._cp = None

    result = service.list_resources("tos-bucket")

    assert result["items"][0]["name"] == "bucket-a"
    assert result["items"][0]["region"] == "cn-beijing"


def test_tos_search_filters_before_pagination() -> None:
    service = object.__new__(deployment_resources.DeploymentResourceService)
    service.provider = "volcengine"
    service.region = "cn-beijing"
    service.credentials = None
    service._tos = cast(
        Any,
        SimpleNamespace(
            actual_region="cn-beijing",
            list_buckets=lambda: [
                {"Name": "alpha", "Location": "cn-beijing"},
                {"Name": "beta", "Location": "cn-beijing"},
                {"Name": "theta", "Location": "cn-beijing"},
            ],
        ),
    )
    service._cr = None
    service._cp = None

    result = service.list_resources(
        "tos-bucket", search="TA", page_number=2, page_size=1
    )

    assert result["totalCount"] == 2
    assert result["hasMore"] is False
    assert [item["name"] for item in result["items"]] == ["theta"]


def test_cr_search_scans_all_pages_before_paginating_matches() -> None:
    calls: list[tuple[int, int]] = []
    pages = {
        1: {
            "Items": [
                {"Name": "alpha"},
                *[{"Name": f"unrelated-{index}"} for index in range(99)],
            ],
            "TotalCount": 102,
        },
        2: {
            "Items": [{"Name": "alphabet"}, {"Name": "omega"}],
            "TotalCount": 102,
        },
    }
    service = object.__new__(deployment_resources.DeploymentResourceService)
    service.provider = "byteplus"
    service.region = "ap-southeast-1"
    service.credentials = None
    service._tos = None
    service._cr = cast(
        Any,
        SimpleNamespace(
            region="ap-southeast-1",
            list_registries=lambda page, size: (
                calls.append((page, size)) or pages[page]
            ),
        ),
    )
    service._cp = None

    result = service.list_resources(
        "cr-registry", search="alpha", page_number=2, page_size=1
    )

    assert calls == [(1, 100), (2, 100)]
    assert result["serviceRegion"] == "ap-southeast-1"
    assert result["totalCount"] == 2
    assert result["hasMore"] is False
    assert [item["name"] for item in result["items"]] == ["alphabet"]


def test_cr_list_supports_current_agentkit_private_request_api() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def ve_request(*, request_body: dict[str, Any], action: str) -> dict[str, Any]:
        calls.append((action, request_body))
        return {
            "ResponseMetadata": {},
            "Result": {"Items": [{"Name": action}], "TotalCount": 1},
        }

    service = object.__new__(deployment_resources.DeploymentResourceService)
    service.provider = "volcengine"
    service.region = "cn-beijing"
    service.credentials = ("ak", "sk", None)
    service._tos = None
    service._cr = cast(
        Any,
        SimpleNamespace(region="cn-beijing", _ve_request=ve_request),
    )
    service._cp = None

    service.list_resources("cr-registry", page_number=2, page_size=20)
    service.list_resources(
        "cr-namespace", registry="registry-a", page_number=3, page_size=10
    )
    service.list_resources(
        "cr-repository",
        registry="registry-a",
        namespace="namespace-a",
        page_number=4,
        page_size=5,
    )

    assert calls == [
        ("ListRegistries", {"PageNumber": 2, "PageSize": 20}),
        (
            "ListNamespaces",
            {"PageNumber": 3, "PageSize": 10, "Registry": "registry-a"},
        ),
        (
            "ListRepositories",
            {
                "PageNumber": 4,
                "PageSize": 5,
                "Registry": "registry-a",
                "Namespace": "namespace-a",
            },
        ),
    ]


def test_code_pipeline_search_uses_service_name_filter() -> None:
    calls: list[tuple[int, int, str]] = []
    service = object.__new__(deployment_resources.DeploymentResourceService)
    service.provider = "volcengine"
    service.region = "cn-beijing"
    service.credentials = None
    service._tos = None
    service._cr = None
    service._cp = cast(
        Any,
        SimpleNamespace(
            region="cn-beijing",
            list_workspaces=lambda page, size, name_filter="": (
                calls.append((page, size, name_filter))
                or {
                    "Items": [{"Id": "workspace-id", "Name": "workspace-alpha"}],
                    "TotalCount": 1,
                }
            ),
        ),
    )

    result = service.list_resources("cp-workspace", search="alpha")

    assert calls == [(1, 100, "alpha")]
    assert result["items"][0]["name"] == "workspace-alpha"


def test_code_pipeline_list_filters_incompatible_pipelines() -> None:
    service = object.__new__(deployment_resources.DeploymentResourceService)
    service.provider = "byteplus"
    service.region = "ap-southeast-1"
    service.credentials = None
    service._tos = None
    service._cr = None
    service._cp = cast(
        Any,
        SimpleNamespace(
            region="ap-southeast-1",
            list_pipelines=lambda _workspace_id, _page, _size: {
                "Items": [
                    {"Id": "compatible-id", "Name": "compatible"},
                    {"Id": "other-id", "Name": "other"},
                ],
                "TotalCount": 2,
            },
            is_agentkit_build_pipeline=lambda pipeline: (
                pipeline["Id"] == "compatible-id"
            ),
        ),
    )

    result = service.list_resources("cp-pipeline", workspace_id="workspace-id")

    assert result["serviceRegion"] == "ap-southeast-1"
    assert result["pageNumber"] == 1
    assert result["pageSize"] == 100
    assert result["totalCount"] == 2
    assert result["hasMore"] is False
    assert result["items"] == [
        {
            "id": "compatible-id",
            "name": "compatible",
            "region": "ap-southeast-1",
            "status": "",
            "compatible": True,
        }
    ]


def test_code_pipeline_compatibility_uses_current_agentkit_pipeline_shape() -> None:
    required_parameters = [
        {"Key": key}
        for key in sorted(deployment_resources._AGENTKIT_PIPELINE_PARAMETERS)
    ]
    service = object.__new__(deployment_resources.DeploymentResourceService)
    service.provider = "volcengine"
    service.region = "cn-beijing"
    service.credentials = None
    service._tos = None
    service._cr = None
    service._cp = cast(
        Any,
        SimpleNamespace(
            region="cn-beijing",
            list_pipelines=lambda _workspace_id, _page, _size: {
                "Items": [
                    {
                        "Id": "agentkit-id",
                        "Name": "agentkit-build",
                        "Parameters": required_parameters,
                        "Spec": "component: artifact/tos-download\ncomponent: buildkit-cr",
                    },
                    {
                        "Id": "other-id",
                        "Name": "other",
                        "Parameters": [],
                        "Spec": "component: shell",
                    },
                ],
                "TotalCount": 2,
            },
        ),
    )

    result = service.list_resources("cp-pipeline", workspace_id="workspace-id")

    assert [item["id"] for item in result["items"]] == ["agentkit-id"]


def test_existing_resource_validation_supports_current_agentkit_sdk_shapes() -> None:
    required_parameters = [
        {"Key": key}
        for key in sorted(deployment_resources._AGENTKIT_PIPELINE_PARAMETERS)
    ]

    def ve_request(*, request_body: dict[str, Any], action: str) -> dict[str, Any]:
        names = {
            "ListRegistries": "registry-a",
            "ListNamespaces": "namespace-a",
            "ListRepositories": "repository-a",
        }
        return {
            "ResponseMetadata": {},
            "Result": {"Items": [{"Name": names[action]}], "TotalCount": 1},
        }

    service = object.__new__(deployment_resources.DeploymentResourceService)
    service.provider = "volcengine"
    service.region = "cn-beijing"
    service.credentials = None
    service._tos = cast(
        Any,
        SimpleNamespace(
            actual_region="cn-beijing",
            client=SimpleNamespace(
                list_buckets=lambda: SimpleNamespace(
                    buckets=[SimpleNamespace(name="bucket-a", location="cn-beijing")]
                )
            ),
        ),
    )
    service._cr = cast(
        Any,
        SimpleNamespace(region="cn-beijing", _ve_request=ve_request),
    )
    service._cp = cast(
        Any,
        SimpleNamespace(
            region="cn-beijing",
            list_pipelines=lambda *_args, **_kwargs: {
                "Items": [
                    {
                        "Id": "pipeline-id",
                        "Name": "pipeline-a",
                        "Parameters": required_parameters,
                        "Spec": "component: artifact/tos-download\ncomponent: buildkit-cr",
                    }
                ],
                "TotalCount": 1,
            },
        ),
    )

    assert (
        service._require_existing_resource("tos-bucket", resource_id="bucket-a")["name"]
        == "bucket-a"
    )
    assert (
        service._require_existing_resource("cr-registry", resource_id="registry-a")[
            "name"
        ]
        == "registry-a"
    )
    assert (
        service._require_existing_resource(
            "cr-namespace", resource_id="namespace-a", registry="registry-a"
        )["name"]
        == "namespace-a"
    )
    assert (
        service._require_existing_resource(
            "cr-repository",
            resource_id="repository-a",
            registry="registry-a",
            namespace="namespace-a",
        )["name"]
        == "repository-a"
    )
    assert (
        service._require_existing_resource(
            "cp-pipeline",
            resource_id="pipeline-id",
            workspace_id="workspace-id",
        )["compatible"]
        is True
    )


def test_agentkit_code_pipeline_override_redirects_sdk_hardcoded_names(
    monkeypatch,
) -> None:
    from agentkit.toolkit.volcengine.code_pipeline import VeCodePipeline

    calls: list[tuple[str, Any]] = []

    monkeypatch.setattr(
        VeCodePipeline,
        "workspace_exists_by_name",
        lambda _self, name: calls.append(("workspace-exists", name)) or True,
    )
    monkeypatch.setattr(
        VeCodePipeline,
        "get_workspaces_by_name",
        lambda _self, name, page_number=1, page_size=10: (
            calls.append(("get-workspace", (name, page_number, page_size)))
            or {"Items": []}
        ),
    )
    monkeypatch.setattr(
        VeCodePipeline,
        "create_workspace",
        lambda _self, name, visibility, description="", visible_users=None: (
            calls.append(
                (
                    "create-workspace",
                    (name, visibility, description, visible_users),
                )
            )
            or "workspace-id"
        ),
    )
    monkeypatch.setattr(
        VeCodePipeline,
        "list_pipelines",
        lambda _self,
        workspace_id,
        page_number=1,
        page_size=10,
        name_filter="",
        pipeline_ids=None: (
            calls.append(
                (
                    "list-pipelines",
                    (
                        workspace_id,
                        page_number,
                        page_size,
                        name_filter,
                        pipeline_ids,
                    ),
                )
            )
            or {"Items": []}
        ),
    )
    monkeypatch.setattr(
        VeCodePipeline,
        "_create_pipeline",
        lambda _self, workspace_id, pipeline_name, spec, parameters=None: (
            calls.append(
                (
                    "create-pipeline",
                    (workspace_id, pipeline_name, spec, parameters),
                )
            )
            or "pipeline-id"
        ),
    )
    client = object.__new__(VeCodePipeline)

    with deployment_resources.agentkit_code_pipeline_resources(
        {
            "cp_workspace_name": "selected-workspace",
            "cp_pipeline_name": "selected-pipeline",
            "cp_pipeline_id": "selected-pipeline-id",
        }
    ):
        client.workspace_exists_by_name(name="agentkit-cli-workspace")
        client.get_workspaces_by_name(name="agentkit-cli-workspace", page_size=100)
        client.create_workspace(name="agentkit-cli-workspace", visibility="Account")
        client.list_pipelines(
            workspace_id="selected-workspace-id", name_filter="runtime-name"
        )
        client._create_pipeline(
            workspace_id="selected-workspace-id",
            pipeline_name="runtime-name",
            spec="spec",
        )

    assert calls == [
        ("workspace-exists", "selected-workspace"),
        ("get-workspace", ("selected-workspace", 1, 100)),
        ("create-workspace", ("selected-workspace", "Account", "", None)),
        (
            "list-pipelines",
            (
                "selected-workspace-id",
                1,
                10,
                "",
                ["selected-pipeline-id"],
            ),
        ),
        (
            "create-pipeline",
            ("selected-workspace-id", "selected-pipeline", "spec", None),
        ),
    ]

    calls.clear()
    client.workspace_exists_by_name("native-workspace")
    assert calls == [("workspace-exists", "native-workspace")]


def test_large_pipeline_list_fetches_one_page_at_a_time() -> None:
    calls: list[tuple[str, int, int]] = []
    service = object.__new__(deployment_resources.DeploymentResourceService)
    service.provider = "volcengine"
    service.region = "cn-beijing"
    service.credentials = None
    service._tos = None
    service._cr = None
    service._cp = cast(
        Any,
        SimpleNamespace(
            region="cn-beijing",
            list_pipelines=lambda workspace_id, page, size: (
                calls.append((workspace_id, page, size))
                or {
                    "Items": [
                        {
                            "Id": f"pipeline-{page}",
                            "Name": f"pipeline-{page}",
                        }
                    ],
                    "TotalCount": 15305,
                }
            ),
            is_agentkit_build_pipeline=lambda _pipeline: True,
        ),
    )

    result = service.list_resources(
        "cp-pipeline",
        workspace_id="workspace-id",
        page_number=3,
        page_size=100,
    )

    assert calls == [("workspace-id", 3, 100)]
    assert result["items"][0]["id"] == "pipeline-3"
    assert result["pageNumber"] == 3
    assert result["totalCount"] == 15305
    assert result["hasMore"] is True


def test_existing_pipeline_must_be_agentkit_compatible(monkeypatch) -> None:
    service = object.__new__(deployment_resources.DeploymentResourceService)
    monkeypatch.setattr(
        service,
        "_require_existing_resource",
        lambda kind, **_parents: (
            {"id": "pipeline-id", "name": "pipeline-a"}
            if kind == "cp-pipeline"
            else {"id": "workspace-id", "name": "workspace-a"}
        ),
    )

    resolved = service.resolve_deployment_config(
        {
            "codePipeline": {
                "mode": "existing",
                "workspaceId": "workspace-id",
                "workspaceName": "workspace-a",
                "pipelineId": "pipeline-id",
                "pipelineName": "pipeline-a",
            }
        }
    )

    assert resolved == {
        "cp_workspace_name": "workspace-a",
        "cp_pipeline_name": "pipeline-a",
        "cp_pipeline_id": "pipeline-id",
    }


def test_deployment_resource_tags_round_trip_all_resource_modes() -> None:
    resources = {
        "tos": {"mode": "existing", "bucket": "bucket-a"},
        "cr": {
            "mode": "create",
            "instance": "registry-a",
            "namespace": "namespace-a",
            "repository": "repository-a",
        },
        "codePipeline": {
            "mode": "existing",
            "workspaceId": "workspace-id",
            "workspaceName": "workspace-a",
            "pipelineId": "pipeline-id",
            "pipelineName": "pipeline-a",
        },
    }

    tags = deployment_resources.deployment_resource_tags(resources)

    assert tags == {
        "veadk:build-resource:tos-mode": "existing",
        "veadk:build-resource:tos-bucket": "bucket-a",
        "veadk:build-resource:cr-mode": "create",
        "veadk:build-resource:cr-instance": "registry-a",
        "veadk:build-resource:cr-namespace": "namespace-a",
        "veadk:build-resource:cr-repository": "repository-a",
        "veadk:build-resource:cp-mode": "existing",
        "veadk:build-resource:cp-workspace-id": "workspace-id",
        "veadk:build-resource:cp-workspace-name": "workspace-a",
        "veadk:build-resource:cp-pipeline-id": "pipeline-id",
        "veadk:build-resource:cp-pipeline-name": "pipeline-a",
    }
    assert deployment_resources.deployment_resources_from_tags(tags) == resources


def test_deployment_resource_tags_distinguish_new_defaults_from_legacy_runtime() -> (
    None
):
    tags = deployment_resources.deployment_resource_tags(None)

    assert tags == {
        "veadk:build-resource:tos-mode": "auto",
        "veadk:build-resource:cr-mode": "auto",
        "veadk:build-resource:cp-mode": "auto",
    }
    assert deployment_resources.deployment_resources_from_tags(tags) == {
        "tos": {"mode": "auto"},
        "cr": {"mode": "auto"},
        "codePipeline": {"mode": "auto"},
    }
    assert deployment_resources.deployment_resources_from_tags({}) is None


def test_all_resource_mode_combinations_map_to_agentkit_config(monkeypatch) -> None:
    service = object.__new__(deployment_resources.DeploymentResourceService)
    monkeypatch.setattr(
        service,
        "_require_existing_resource",
        lambda kind, **_parents: {
            "id": _parents["resource_id"],
            "name": (
                "pipeline-existing"
                if kind == "cp-pipeline"
                else _parents["resource_id"]
            ),
        },
    )

    for tos_mode, cr_mode, cp_mode in itertools.product(
        deployment_resources.RESOURCE_MODES, repeat=3
    ):
        resources = {
            "tos": {
                "mode": tos_mode,
                **({"bucket": f"tos-{tos_mode}"} if tos_mode != "auto" else {}),
            },
            "cr": {
                "mode": cr_mode,
                **(
                    {
                        "instance": f"cr-{cr_mode}",
                        "namespace": f"namespace-{cr_mode}",
                        "repository": f"repository-{cr_mode}",
                    }
                    if cr_mode != "auto"
                    else {}
                ),
            },
            "codePipeline": {
                "mode": cp_mode,
                **(
                    {
                        "workspaceName": f"workspace-{cp_mode}",
                        "pipelineName": (
                            "pipeline-existing"
                            if cp_mode == "existing"
                            else "pipeline-create"
                        ),
                    }
                    if cp_mode != "auto"
                    else {}
                ),
                **(
                    {
                        "workspaceId": "workspace-existing",
                        "pipelineId": "pipeline-existing-id",
                    }
                    if cp_mode == "existing"
                    else {}
                ),
            },
        }

        resolved = service.resolve_deployment_config(resources)

        assert ("tos_bucket" in resolved) is (tos_mode != "auto")
        assert ("cr_instance_name" in resolved) is (cr_mode != "auto")
        assert ("cr_namespace_name" in resolved) is (cr_mode != "auto")
        assert ("cr_repo_name" in resolved) is (cr_mode != "auto")
        assert ("cp_workspace_name" in resolved) is (cp_mode != "auto")
        assert ("cp_pipeline_name" in resolved) is (cp_mode != "auto")
        assert ("cp_pipeline_id" in resolved) is (cp_mode == "existing")
