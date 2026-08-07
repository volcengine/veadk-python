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

"""List and validate cloud build resources used by Studio deployments."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request

CloudCredentials = tuple[str, str, str | None]

RESOURCE_KINDS = {
    "tos-bucket",
    "cr-registry",
    "cr-namespace",
    "cr-repository",
    "cp-workspace",
    "cp-pipeline",
}
RESOURCE_MODES = {"auto", "create", "existing"}


def _required_text(data: dict[str, Any], key: str, label: str) -> str:
    value = str(data.get(key) or "").strip()
    if not value:
        raise ValueError(f"{label} is required")
    return value


def _item_name(item: dict[str, Any]) -> str:
    return str(item.get("Name") or item.get("name") or "").strip()


def _item_id(item: dict[str, Any]) -> str:
    return str(item.get("Id") or item.get("ID") or _item_name(item)).strip()


def _item_status(item: dict[str, Any]) -> str:
    status = item.get("Status") or item.get("status") or ""
    if isinstance(status, dict):
        status = status.get("Phase") or status.get("phase") or ""
    return str(status).strip()


def _resource_item(
    item: dict[str, Any], *, region: str = "", compatible: bool | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": _item_id(item),
        "name": _item_name(item),
        "region": region,
        "status": _item_status(item),
    }
    if compatible is not None:
        result["compatible"] = compatible
    return result


def _page_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in result.get("Items", []) if isinstance(item, dict)]


def _find_in_pages(
    fetch_page: Callable[[int, int], dict[str, Any]],
    resource_id: str,
) -> dict[str, Any] | None:
    page_number = 1
    page_size = 100
    while True:
        result = fetch_page(page_number, page_size)
        items = _page_items(result)
        for item in items:
            normalized = _resource_item(item)
            if normalized["id"] == resource_id or normalized["name"] == resource_id:
                return item
        total = int(result.get("TotalCount", len(items)) or 0)
        if not items or page_number * page_size >= total:
            return None
        page_number += 1


class DeploymentResourceService:
    """Adapter around AgentKit's TOS, CR, and CodePipeline clients."""

    def __init__(
        self,
        provider: str,
        region: str,
        credentials: CloudCredentials | None = None,
    ) -> None:
        self.provider = provider
        self.region = region
        self.credentials = credentials
        self._tos = None
        self._cr = None
        self._cp = None

    def _tos_client(self):
        if self._tos is None:
            from agentkit.platform import Credentials
            from agentkit.toolkit.volcengine.services.tos_service import (
                TOSService,
                TOSServiceConfig,
            )

            credentials = (
                Credentials(
                    access_key=self.credentials[0],
                    secret_key=self.credentials[1],
                    session_token=self.credentials[2],
                )
                if self.credentials
                else None
            )

            self._tos = TOSService(
                TOSServiceConfig(bucket="", region=self.region),
                provider=self.provider,
                credentials=credentials,
            )
        return self._tos

    def _cr_client(self):
        if self._cr is None:
            from agentkit.platform import VolcConfiguration
            from agentkit.toolkit.volcengine.cr import VeCR

            access_key, secret_key, session_token = self.credentials or ("", "", None)
            config = VolcConfiguration(
                access_key=access_key or None,
                secret_key=secret_key or None,
                session_token=session_token,
                region=self.region,
                provider=self.provider,
            )
            credentials = config.get_service_credentials("cr")
            endpoint = config.get_service_endpoint("cr")
            self._cr = VeCR(
                access_key=credentials.access_key,
                secret_key=credentials.secret_key,
                session_token=credentials.session_token,
                region=endpoint.region,
                provider=self.provider,
            )
        return self._cr

    def _cp_client(self):
        if self._cp is None:
            from agentkit.toolkit.volcengine.code_pipeline import VeCodePipeline

            access_key, secret_key, session_token = self.credentials or ("", "", None)
            self._cp = VeCodePipeline(
                access_key=access_key,
                secret_key=secret_key,
                session_token=session_token or "",
                region=self.region,
                provider=self.provider,
            )
        return self._cp

    def list_resources(
        self,
        kind: str,
        *,
        registry: str = "",
        namespace: str = "",
        workspace_id: str = "",
        page_number: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        if kind not in RESOURCE_KINDS:
            raise ValueError(f"Unsupported deployment resource kind: {kind}")
        if page_number < 1:
            raise ValueError("pageNumber must be at least 1")
        if page_size < 1 or page_size > 100:
            raise ValueError("pageSize must be between 1 and 100")

        if kind == "tos-bucket":
            client = self._tos_client()
            service_region = str(getattr(client, "actual_region", self.region))
            all_items = [
                _resource_item(item, region=str(item.get("Location") or service_region))
                for item in client.list_buckets()
                if not item.get("Location") or item.get("Location") == service_region
            ]
            all_items.sort(key=lambda item: (item["name"].casefold(), item["id"]))
            total_count = len(all_items)
            start = (page_number - 1) * page_size
            items = all_items[start : start + page_size]
        elif kind.startswith("cr-"):
            client = self._cr_client()
            service_region = str(getattr(client, "region", self.region))
            if kind == "cr-registry":
                page = client.list_registries(page_number, page_size)
            elif kind == "cr-namespace":
                if not registry:
                    raise ValueError("registry is required for CR namespaces")
                page = client.list_namespaces(registry, page_number, page_size)
            else:
                if not registry or not namespace:
                    raise ValueError(
                        "registry and namespace are required for CR repositories"
                    )
                page = client.list_repositories(
                    registry, namespace, page_number, page_size
                )
            raw_items = _page_items(page)
            total_count = int(page.get("TotalCount", len(raw_items)) or 0)
            items = [_resource_item(item, region=service_region) for item in raw_items]
        else:
            client = self._cp_client()
            service_region = str(getattr(client, "region", self.region))
            if kind == "cp-workspace":
                page = client.list_workspaces(page_number, page_size)
                raw_items = _page_items(page)
                total_count = int(page.get("TotalCount", len(raw_items)) or 0)
                items = [
                    _resource_item(item, region=service_region) for item in raw_items
                ]
            else:
                if not workspace_id:
                    raise ValueError(
                        "workspaceId is required for CodePipeline pipelines"
                    )
                page = client.list_pipelines(workspace_id, page_number, page_size)
                raw_items = _page_items(page)
                total_count = int(page.get("TotalCount", len(raw_items)) or 0)
                items = []
                for item in raw_items:
                    if client.is_agentkit_build_pipeline(item):
                        items.append(
                            _resource_item(item, region=service_region, compatible=True)
                        )

        items.sort(key=lambda item: (item["name"].casefold(), item["id"]))
        return {
            "serviceRegion": service_region,
            "items": items,
            "pageNumber": page_number,
            "pageSize": page_size,
            "totalCount": total_count,
            "hasMore": page_number * page_size < total_count,
        }

    def _require_existing_resource(
        self,
        kind: str,
        *,
        resource_id: str,
        registry: str = "",
        namespace: str = "",
        workspace_id: str = "",
    ) -> dict[str, Any]:
        service_region = self.region
        raw_item: dict[str, Any] | None = None
        compatible: bool | None = None
        if kind == "tos-bucket":
            client = self._tos_client()
            service_region = str(getattr(client, "actual_region", self.region))
            raw_item = next(
                (
                    item
                    for item in client.list_buckets()
                    if _item_id(item) == resource_id or _item_name(item) == resource_id
                ),
                None,
            )
        elif kind.startswith("cr-"):
            client = self._cr_client()
            service_region = str(getattr(client, "region", self.region))
            if kind == "cr-registry":
                raw_item = _find_in_pages(client.list_registries, resource_id)
            elif kind == "cr-namespace":
                raw_item = _find_in_pages(
                    lambda page, size: client.list_namespaces(registry, page, size),
                    resource_id,
                )
            else:
                raw_item = _find_in_pages(
                    lambda page, size: client.list_repositories(
                        registry, namespace, page, size
                    ),
                    resource_id,
                )
        else:
            client = self._cp_client()
            service_region = str(getattr(client, "region", self.region))
            if kind == "cp-workspace":
                raw_item = next(
                    iter(
                        _page_items(
                            client.list_workspaces(
                                page_size=100, workspace_ids=[resource_id]
                            )
                        )
                    ),
                    None,
                )
            else:
                raw_item = next(
                    iter(
                        _page_items(
                            client.list_pipelines(
                                workspace_id,
                                page_size=100,
                                pipeline_ids=[resource_id],
                            )
                        )
                    ),
                    None,
                )
                compatible = bool(
                    raw_item and client.is_agentkit_build_pipeline(raw_item)
                )
                if raw_item and not compatible:
                    raise ValueError(
                        f"Selected {kind} resource is not AgentKit-compatible: "
                        f"{resource_id}"
                    )
        if raw_item:
            return _resource_item(
                raw_item,
                region=service_region,
                compatible=compatible,
            )
        raise ValueError(f"Selected {kind} resource does not exist: {resource_id}")

    def resolve_deployment_config(
        self,
        resources: object,
        *,
        validate_existing: bool = True,
    ) -> dict[str, str]:
        if resources is None:
            return {}
        if not isinstance(resources, dict):
            raise TypeError("resources must be an object")

        resolved: dict[str, str] = {}
        tos = resources.get("tos") or {}
        cr = resources.get("cr") or {}
        cp = resources.get("codePipeline") or {}
        if (
            not isinstance(tos, dict)
            or not isinstance(cr, dict)
            or not isinstance(cp, dict)
        ):
            raise TypeError("Each deployment resource configuration must be an object")

        tos_mode = str(tos.get("mode") or "auto")
        cr_mode = str(cr.get("mode") or "auto")
        cp_mode = str(cp.get("mode") or "auto")
        for label, mode in (
            ("TOS", tos_mode),
            ("CR", cr_mode),
            ("CodePipeline", cp_mode),
        ):
            if mode not in RESOURCE_MODES:
                raise ValueError(f"Unsupported {label} resource mode: {mode}")

        if tos_mode != "auto":
            bucket = _required_text(tos, "bucket", "TOS bucket")
            if tos_mode == "existing" and validate_existing:
                self._require_existing_resource("tos-bucket", resource_id=bucket)
            resolved["tos_bucket"] = bucket

        if cr_mode != "auto":
            instance = _required_text(cr, "instance", "CR instance")
            namespace = _required_text(cr, "namespace", "CR namespace")
            repository = _required_text(cr, "repository", "CR repository")
            if cr_mode == "existing" and validate_existing:
                self._require_existing_resource("cr-registry", resource_id=instance)
                self._require_existing_resource(
                    "cr-namespace", resource_id=namespace, registry=instance
                )
                self._require_existing_resource(
                    "cr-repository",
                    resource_id=repository,
                    registry=instance,
                    namespace=namespace,
                )
            resolved.update(
                {
                    "cr_instance_name": instance,
                    "cr_namespace_name": namespace,
                    "cr_repo_name": repository,
                }
            )

        if cp_mode != "auto":
            workspace_name = _required_text(
                cp, "workspaceName", "CodePipeline workspace name"
            )
            pipeline_name = _required_text(
                cp, "pipelineName", "CodePipeline pipeline name"
            )
            resolved.update(
                {
                    "cp_workspace_name": workspace_name,
                    "cp_pipeline_name": pipeline_name,
                }
            )
            if cp_mode == "existing":
                workspace_id = _required_text(
                    cp, "workspaceId", "CodePipeline workspace ID"
                )
                pipeline_id = _required_text(
                    cp, "pipelineId", "CodePipeline pipeline ID"
                )
                if validate_existing:
                    self._require_existing_resource(
                        "cp-workspace", resource_id=workspace_id
                    )
                    pipeline = self._require_existing_resource(
                        "cp-pipeline",
                        resource_id=pipeline_id,
                        workspace_id=workspace_id,
                    )
                    if pipeline["name"] != pipeline_name:
                        raise ValueError(
                            "Selected CodePipeline pipeline name does not match its ID"
                        )
                resolved["cp_pipeline_id"] = pipeline_id

        return resolved


def mount_deployment_resource_routes(
    app: FastAPI,
    authorize: Callable[[Request], object],
    provider: str,
    resolve_credentials: Callable[[], CloudCredentials | None] | None = None,
) -> None:
    """Mount the deployment-page cloud resource query endpoint."""

    @app.get("/web/deployment-resources")
    async def _deployment_resources(request: Request):
        authorize(request)
        kind = str(request.query_params.get("kind") or "").strip()
        region = str(request.query_params.get("region") or "").strip()
        if not region:
            raise HTTPException(status_code=400, detail="region is required")
        try:
            page_number = int(request.query_params.get("pageNumber") or 1)
            page_size = int(request.query_params.get("pageSize") or 100)
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail="pageNumber and pageSize must be integers",
            ) from error
        credentials = resolve_credentials() if resolve_credentials else None
        service = DeploymentResourceService(provider, region, credentials)
        try:
            return await asyncio.to_thread(
                service.list_resources,
                kind,
                registry=str(request.query_params.get("registry") or "").strip(),
                namespace=str(request.query_params.get("namespace") or "").strip(),
                workspace_id=str(request.query_params.get("workspaceId") or "").strip(),
                page_number=page_number,
                page_size=page_size,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
