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
import json
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from typing import Any, cast
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request

CloudCredentials = tuple[str, str, str | None]


class ManagedSidecarRegistryError(ValueError):
    """The managed Sidecar image cannot be safely anchored to a customer CR."""


def _safe_exception_detail(
    error: BaseException,
    credentials: CloudCredentials | None = None,
) -> str:
    """Keep the exception chain intact while removing credential values."""
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = str(current).strip() or type(current).__name__
        for secret in credentials or ():
            if secret:
                message = message.replace(secret, "***")
        if message not in parts:
            parts.append(message)
        current = current.__cause__ or current.__context__
    return "\nCaused by:\n".join(parts)


RESOURCE_KINDS = {
    "tos-bucket",
    "cr-registry",
    "cr-namespace",
    "cr-repository",
    "cp-workspace",
    "cp-pipeline",
}
RESOURCE_MODES = {"auto", "create", "existing"}
RESOURCE_TAG_PREFIX = "veadk:build-resource:"
_RESOURCE_TAG_FIELDS = {
    "tos": {
        "bucket": "tos-bucket",
    },
    "cr": {
        "instance": "cr-instance",
        "namespace": "cr-namespace",
        "repository": "cr-repository",
    },
    "codePipeline": {
        "workspaceId": "cp-workspace-id",
        "workspaceName": "cp-workspace-name",
        "pipelineId": "cp-pipeline-id",
        "pipelineName": "cp-pipeline-name",
    },
}
_RESOURCE_MODE_TAGS = {
    "tos": "tos-mode",
    "cr": "cr-mode",
    "codePipeline": "cp-mode",
}
_AGENTKIT_PIPELINE_PARAMETERS = {
    "CR_DOMAIN",
    "CR_INSTANCE",
    "CR_NAMESPACE",
    "CR_OCI",
    "CR_REGION",
    "CR_TAG",
    "DOCKERFILE_PATH",
    "TOS_BUCKET_NAME",
    "TOS_PROJECT_FILE_NAME",
    "TOS_PROJECT_FILE_PATH",
    "TOS_REGION",
}


def deployment_resource_tags(resources: object) -> dict[str, str]:
    """Encode Studio build-resource selections as individual Runtime tags."""
    if resources is None:
        resources = {}
    if not isinstance(resources, dict):
        raise TypeError("resources must be an object")

    tags: dict[str, str] = {}
    for group, mode_tag in _RESOURCE_MODE_TAGS.items():
        values = resources.get(group) or {}
        if not isinstance(values, dict):
            raise TypeError("Each deployment resource configuration must be an object")
        mode = str(values.get("mode") or "auto")
        if mode not in RESOURCE_MODES:
            raise ValueError(f"Unsupported resource mode: {mode}")
        tags[f"{RESOURCE_TAG_PREFIX}{mode_tag}"] = mode
        for field, tag_suffix in _RESOURCE_TAG_FIELDS[group].items():
            value = str(values.get(field) or "").strip()
            if value:
                tags[f"{RESOURCE_TAG_PREFIX}{tag_suffix}"] = value
    return tags


def deployment_resources_from_tags(
    tags: Mapping[str, str],
) -> dict[str, dict[str, str]] | None:
    """Decode Runtime tags, returning None for legacy Runtimes without them."""
    resource_tags = {
        key: str(value or "").strip()
        for key, value in tags.items()
        if key.startswith(RESOURCE_TAG_PREFIX)
    }
    if not resource_tags:
        return None

    resources: dict[str, dict[str, str]] = {}
    for group, mode_tag in _RESOURCE_MODE_TAGS.items():
        mode = resource_tags.get(f"{RESOURCE_TAG_PREFIX}{mode_tag}", "auto")
        if mode not in RESOURCE_MODES:
            return None
        values = {"mode": mode}
        for field, tag_suffix in _RESOURCE_TAG_FIELDS[group].items():
            value = resource_tags.get(f"{RESOURCE_TAG_PREFIX}{tag_suffix}", "")
            if value:
                values[field] = value
        resources[group] = values
    return resources


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


def _search_in_pages(
    fetch_page: Callable[[int, int], dict[str, Any]],
    search: str,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    normalized_search = search.casefold()
    page_number = 1
    page_size = 100
    while True:
        result = fetch_page(page_number, page_size)
        items = _page_items(result)
        matches.extend(
            item for item in items if normalized_search in _item_name(item).casefold()
        )
        total = int(result.get("TotalCount", len(items)) or 0)
        if not items or page_number * page_size >= total:
            return matches
        page_number += 1


def _tos_buckets(client: Any) -> list[dict[str, Any]]:
    list_buckets = getattr(client, "list_buckets", None)
    if callable(list_buckets):
        return cast(list[dict[str, Any]], list_buckets())

    result = client.client.list_buckets()
    return [
        {
            "Name": str(getattr(bucket, "name", "") or ""),
            "Location": str(getattr(bucket, "location", "") or ""),
        }
        for bucket in (getattr(result, "buckets", None) or [])
    ]


def _cr_page(
    client: Any,
    action: str,
    page_number: int,
    page_size: int,
    *,
    registry: str = "",
    namespace: str = "",
) -> dict[str, Any]:
    method_name = {
        "ListRegistries": "list_registries",
        "ListNamespaces": "list_namespaces",
        "ListRepositories": "list_repositories",
    }[action]
    method = getattr(client, method_name, None)
    if callable(method):
        if action == "ListRegistries":
            return cast(dict[str, Any], method(page_number, page_size))
        if action == "ListNamespaces":
            return cast(dict[str, Any], method(registry, page_number, page_size))
        return cast(
            dict[str, Any],
            method(registry, namespace, page_number, page_size),
        )

    request_body: dict[str, Any] = {
        "PageNumber": page_number,
        "PageSize": page_size,
    }
    if registry:
        request_body["Registry"] = registry
    if namespace:
        request_body["Namespace"] = namespace
    response = client._ve_request(request_body=request_body, action=action)
    metadata = response.get("ResponseMetadata") or {}
    if metadata.get("Error"):
        raise ValueError(
            f"{action} failed.\nOriginal response:\n"
            f"{json.dumps(response, ensure_ascii=False, default=str)}"
        )
    result = response.get("Result") or {}
    if not isinstance(result, dict):
        raise ValueError(f"{action} returned an invalid result")
    return result


def _registry_host(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""
    parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
    return str(parsed.hostname or "").rstrip(".").casefold()


def _managed_image_location(image: str) -> tuple[str, str]:
    candidate = image.strip()
    parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
    host = str(parsed.hostname or "").rstrip(".").casefold()
    path_parts = [part for part in parsed.path.split("/") if part]
    if not host or len(path_parts) < 2:
        raise ManagedSidecarRegistryError(
            "受控 Harness Sidecar 基础镜像地址无效，无法定位客户 CR。"
        )
    return host, path_parts[0]


def _cr_domains(client: Any, registry: str) -> list[dict[str, Any]]:
    list_domains = getattr(client, "list_domains", None)
    if callable(list_domains):
        result = list_domains(registry)
    else:
        private_list_domains = getattr(client, "_list_domains", None)
        if callable(private_list_domains):
            result = private_list_domains(registry)
        else:
            response = client._ve_request(
                request_body={"Registry": registry},
                action="ListDomains",
            )
            metadata = response.get("ResponseMetadata") or {}
            if metadata.get("Error"):
                raise ValueError("ListDomains failed")
            result = response.get("Result") or {}

    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        nested = result.get("Result") if "Result" in result else result
        if isinstance(nested, dict):
            return [item for item in nested.get("Items", []) if isinstance(item, dict)]
    raise ValueError("ListDomains returned an invalid result")


def _is_agentkit_build_pipeline(client: Any, pipeline: dict[str, Any]) -> bool:
    check = getattr(client, "is_agentkit_build_pipeline", None)
    if callable(check):
        return bool(check(pipeline))

    parameter_keys = {
        str(parameter.get("Key") or "")
        for parameter in (pipeline.get("Parameters") or [])
        if isinstance(parameter, dict)
    }
    spec = str(pipeline.get("Spec") or "")
    return (
        _AGENTKIT_PIPELINE_PARAMETERS <= parameter_keys
        and "tos-download" in spec
        and "buildkit-cr" in spec
    )


@contextmanager
def agentkit_code_pipeline_resources(config: Mapping[str, str]):
    """Make AgentKit 0.8.x honor Studio's selected CodePipeline resources."""
    workspace_name = str(config.get("cp_workspace_name") or "").strip()
    selected_pipeline_name = str(config.get("cp_pipeline_name") or "").strip()
    pipeline_id = str(config.get("cp_pipeline_id") or "").strip()
    if not workspace_name or not selected_pipeline_name:
        yield
        return

    from agentkit.toolkit.volcengine.code_pipeline import VeCodePipeline

    required_methods = (
        "workspace_exists_by_name",
        "get_workspaces_by_name",
        "create_workspace",
        "list_pipelines",
        "_create_pipeline",
    )
    if not all(hasattr(VeCodePipeline, name) for name in required_methods):
        yield
        return

    original_workspace_exists = VeCodePipeline.workspace_exists_by_name
    original_get_workspaces = VeCodePipeline.get_workspaces_by_name
    original_create_workspace = VeCodePipeline.create_workspace
    original_list_pipelines = VeCodePipeline.list_pipelines
    original_create_pipeline = VeCodePipeline._create_pipeline

    def workspace_exists(self, name: str) -> bool:
        del name
        return original_workspace_exists(self, workspace_name)

    def get_workspaces(
        self,
        name: str,
        page_number: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        del name
        return original_get_workspaces(
            self,
            workspace_name,
            page_number=page_number,
            page_size=page_size,
        )

    def create_workspace(
        self,
        name: str,
        visibility: str,
        description: str = "",
        visible_users: list[dict[str, int]] | None = None,
    ) -> str:
        del name
        return original_create_workspace(
            self,
            workspace_name,
            visibility,
            description=description,
            visible_users=visible_users,
        )

    def list_pipelines(
        self,
        workspace_id: str,
        page_number: int = 1,
        page_size: int = 10,
        name_filter: str = "",
        pipeline_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if pipeline_id:
            pipeline_ids = [pipeline_id]
            name_filter = ""
        elif name_filter:
            name_filter = selected_pipeline_name
        return original_list_pipelines(
            self,
            workspace_id,
            page_number=page_number,
            page_size=page_size,
            name_filter=name_filter,
            pipeline_ids=pipeline_ids,
        )

    def create_pipeline(
        self,
        workspace_id: str,
        pipeline_name: str,
        spec: str,
        parameters: list[dict[str, str]] | None = None,
    ) -> str:
        del pipeline_name
        return original_create_pipeline(
            self,
            workspace_id,
            selected_pipeline_name,
            spec,
            parameters=parameters,
        )

    VeCodePipeline.workspace_exists_by_name = workspace_exists
    VeCodePipeline.get_workspaces_by_name = get_workspaces
    VeCodePipeline.create_workspace = create_workspace
    VeCodePipeline.list_pipelines = list_pipelines
    VeCodePipeline._create_pipeline = create_pipeline
    try:
        yield
    finally:
        VeCodePipeline.workspace_exists_by_name = original_workspace_exists
        VeCodePipeline.get_workspaces_by_name = original_get_workspaces
        VeCodePipeline.create_workspace = original_create_workspace
        VeCodePipeline.list_pipelines = original_list_pipelines
        VeCodePipeline._create_pipeline = original_create_pipeline


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
            from agentkit.toolkit.volcengine.services.tos_service import (
                TOSService,
                TOSServiceConfig,
            )

            self._tos = TOSService(
                TOSServiceConfig(bucket="", region=self.region),
                provider=self.provider,
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
        search: str = "",
        page_number: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        if kind not in RESOURCE_KINDS:
            raise ValueError(f"Unsupported deployment resource kind: {kind}")
        if page_number < 1:
            raise ValueError("pageNumber must be at least 1")
        if page_size < 1 or page_size > 100:
            raise ValueError("pageSize must be between 1 and 100")
        search = search.strip()

        if kind == "tos-bucket":
            client = self._tos_client()
            service_region = str(getattr(client, "actual_region", self.region))
            all_items = [
                _resource_item(item, region=str(item.get("Location") or service_region))
                for item in _tos_buckets(client)
                if not item.get("Location") or item.get("Location") == service_region
            ]
            if search:
                normalized_search = search.casefold()
                all_items = [
                    item
                    for item in all_items
                    if normalized_search in item["name"].casefold()
                ]
            all_items.sort(key=lambda item: (item["name"].casefold(), item["id"]))
            total_count = len(all_items)
            start = (page_number - 1) * page_size
            items = all_items[start : start + page_size]
        elif kind.startswith("cr-"):
            client = self._cr_client()
            service_region = str(getattr(client, "region", self.region))
            if kind == "cr-registry":

                def fetch_page(number: int, size: int) -> dict[str, Any]:
                    return _cr_page(client, "ListRegistries", number, size)

            elif kind == "cr-namespace":
                if not registry:
                    raise ValueError("registry is required for CR namespaces")

                def fetch_page(number: int, size: int) -> dict[str, Any]:
                    return _cr_page(
                        client,
                        "ListNamespaces",
                        number,
                        size,
                        registry=registry,
                    )

            else:
                if not registry or not namespace:
                    raise ValueError(
                        "registry and namespace are required for CR repositories"
                    )

                def fetch_page(number: int, size: int) -> dict[str, Any]:
                    return _cr_page(
                        client,
                        "ListRepositories",
                        number,
                        size,
                        registry=registry,
                        namespace=namespace,
                    )

            if search:
                raw_items = _search_in_pages(fetch_page, search)
                items = [
                    _resource_item(item, region=service_region) for item in raw_items
                ]
                items.sort(key=lambda item: (item["name"].casefold(), item["id"]))
                total_count = len(items)
                start = (page_number - 1) * page_size
                items = items[start : start + page_size]
            else:
                page = fetch_page(page_number, page_size)
                raw_items = _page_items(page)
                total_count = int(page.get("TotalCount", len(raw_items)) or 0)
                items = [
                    _resource_item(item, region=service_region) for item in raw_items
                ]
        else:
            client = self._cp_client()
            service_region = str(getattr(client, "region", self.region))
            if kind == "cp-workspace":
                page = (
                    client.list_workspaces(page_number, page_size, name_filter=search)
                    if search
                    else client.list_workspaces(page_number, page_size)
                )
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
                page = (
                    client.list_pipelines(
                        workspace_id,
                        page_number,
                        page_size,
                        name_filter=search,
                    )
                    if search
                    else client.list_pipelines(workspace_id, page_number, page_size)
                )
                raw_items = _page_items(page)
                total_count = int(page.get("TotalCount", len(raw_items)) or 0)
                items = []
                for item in raw_items:
                    if _is_agentkit_build_pipeline(client, item):
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
                    for item in _tos_buckets(client)
                    if _item_id(item) == resource_id or _item_name(item) == resource_id
                ),
                None,
            )
        elif kind.startswith("cr-"):
            client = self._cr_client()
            service_region = str(getattr(client, "region", self.region))
            if kind == "cr-registry":
                raw_item = _find_in_pages(
                    lambda page, size: _cr_page(client, "ListRegistries", page, size),
                    resource_id,
                )
            elif kind == "cr-namespace":
                raw_item = _find_in_pages(
                    lambda page, size: _cr_page(
                        client,
                        "ListNamespaces",
                        page,
                        size,
                        registry=registry,
                    ),
                    resource_id,
                )
            else:
                raw_item = _find_in_pages(
                    lambda page, size: _cr_page(
                        client,
                        "ListRepositories",
                        page,
                        size,
                        registry=registry,
                        namespace=namespace,
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
                    raw_item and _is_agentkit_build_pipeline(client, raw_item)
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

    def anchor_managed_sidecar_registry(
        self,
        base_image: str,
        config: Mapping[str, str],
    ) -> dict[str, str]:
        """Bind account-owned bases while leaving external public bases unbound.

        A managed base can live in a platform-owned public registry. Such a
        registry is intentionally absent from the customer's ``ListRegistries``
        result, and the application image must still be pushed to a CR owned by
        the customer. Only anchor when the base host belongs to exactly one CR
        in the current account; a successful lookup with no match therefore
        means that the immutable base is external to the account.
        """
        if self.provider != "volcengine":
            raise ManagedSidecarRegistryError(
                "Harness Sidecar 当前无法定位所需的客户 CR。"
            )

        try:
            image_host, image_namespace = _managed_image_location(base_image)
            client = self._cr_client()
            registries = _search_in_pages(
                lambda page, size: _cr_page(
                    client,
                    "ListRegistries",
                    page,
                    size,
                ),
                "",
            )
            matches: list[str] = []
            for item in registries:
                registry = _item_name(item)
                phase = _item_status(item).casefold()
                if not registry or (phase and phase != "running"):
                    continue
                domains = _cr_domains(client, registry)
                if any(
                    _registry_host(str(domain.get("Domain") or "")) == image_host
                    for domain in domains
                ):
                    matches.append(registry)
        except ManagedSidecarRegistryError:
            raise
        except Exception as error:
            raise ManagedSidecarRegistryError(
                "无法从当前账号唯一定位受控 Harness Sidecar 基础镜像所在的 CR。"
            ) from error

        if not matches:
            return dict(config)
        if len(matches) != 1:
            raise ManagedSidecarRegistryError(
                "无法从当前账号唯一定位受控 Harness Sidecar 基础镜像所在的 CR。"
            )
        registry = matches[0]

        configured_registry = str(config.get("cr_instance_name") or "").strip()
        configured_namespace = str(config.get("cr_namespace_name") or "").strip()
        if (configured_registry and configured_registry != registry) or (
            configured_namespace and configured_namespace != image_namespace
        ):
            raise ManagedSidecarRegistryError(
                "所选 CR 与受控 Harness Sidecar 基础镜像不在同一实例和命名空间，"
                "请改用自动创建 CR 或选择匹配资源。"
            )

        try:
            self._require_existing_resource(
                "cr-namespace",
                resource_id=image_namespace,
                registry=registry,
            )
        except Exception as error:
            raise ManagedSidecarRegistryError(
                "受控 Harness Sidecar 基础镜像所在的 CR 命名空间不可用。"
            ) from error

        anchored = dict(config)
        anchored["cr_instance_name"] = registry
        anchored["cr_namespace_name"] = image_namespace
        return anchored


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
                search=str(request.query_params.get("search") or "").strip(),
                page_number=page_number,
                page_size=page_size,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=_safe_exception_detail(error, credentials),
            ) from error
        except Exception as error:
            raise HTTPException(
                status_code=502,
                detail=_safe_exception_detail(error, credentials),
            ) from error
