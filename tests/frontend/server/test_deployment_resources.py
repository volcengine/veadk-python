from __future__ import annotations

import itertools
from types import SimpleNamespace
from typing import Any, cast

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
                "page_number": 1,
                "page_size": 100,
            },
        )
    ]


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
