# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");

"""Resolve CP/CR resources and run environment image builds."""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from frontend.server.deployment_resources import (
    CloudCredentials,
    DeploymentResourceService,
    _is_agentkit_build_pipeline,
)
from frontend.server.storage import StudioProvider

from .models import (
    CodePipelineResource,
    ContainerRegistryResource,
    EnvironmentBuildStatus,
    EnvironmentBuildStep,
    EnvironmentBuildStepStatus,
    EnvironmentResourceInfo,
    EnvironmentResources,
)

CP_WORKSPACE_ENV = "VEADK_STUDIO_ENVIRONMENT_CP_WORKSPACE"
CR_REPOSITORY_ENV = "VEADK_STUDIO_ENVIRONMENT_CR_REPOSITORY"

_MANAGED_CP_WORKSPACE = "veadk-studio-environments"
_MANAGED_CP_PIPELINE = "veadk-studio-environment-build-v7"
_MANAGED_CR_REGISTRY = "veadk-studio-environments"
_MANAGED_CR_NAMESPACE = "runtime-environments"
_MANAGED_CR_REPOSITORY = "base-images"

_PIPELINE_PARAMETERS = [
    {
        "Key": "DOCKERFILE_PATH",
        "Value": "/workspace/environment/Dockerfile",
        "Dynamic": True,
        "Env": True,
    },
    {"Key": "DOWNLOAD_PATH", "Value": "/workspace", "Dynamic": True, "Env": True},
    {
        "Key": "PROJECT_ROOT_DIR",
        "Value": "/workspace/environment",
        "Dynamic": True,
        "Env": True,
    },
    {"Key": "TOS_BUCKET_NAME", "Value": "", "Dynamic": True},
    {"Key": "TOS_REGION", "Value": "", "Dynamic": True},
    {"Key": "TOS_PROJECT_FILE_NAME", "Value": "", "Dynamic": True, "Env": True},
    {"Key": "TOS_PROJECT_FILE_PATH", "Value": "", "Dynamic": True, "Env": True},
    {"Key": "CR_NAMESPACE", "Value": "", "Dynamic": True, "Env": True},
    {"Key": "CR_INSTANCE", "Value": "", "Dynamic": True, "Env": True},
    {"Key": "CR_DOMAIN", "Value": "", "Dynamic": True, "Env": True},
    {"Key": "CR_OCI", "Value": "", "Dynamic": True, "Env": True},
    {"Key": "CR_TAG", "Value": "", "Dynamic": True, "Env": True},
    {"Key": "CR_REGION", "Value": "", "Dynamic": True, "Env": True},
    {
        "Key": "PIP_INDEX_URL",
        "Value": "https://pypi.org/simple",
        "Dynamic": True,
        "Env": True,
    },
    {
        "Key": "PYTHON_SOURCE_BASE_URL",
        "Value": "https://www.python.org/ftp/python",
        "Dynamic": True,
        "Env": True,
    },
    {
        "Key": "PLAYWRIGHT_DOWNLOAD_HOST",
        "Value": "https://cdn.playwright.dev",
        "Dynamic": True,
        "Env": True,
    },
]

_PIPELINE_SPEC = """version: 1.0.0
agentPool: public/prod-v2-public
stages:
  - stage: build-environment
    displayName: Build environment image
    tasks:
      - task: build
        displayName: Build and push environment image
        timeout: 2h
        steps:
          - step: download
            displayName: Download TOS build context
            component: artifact@1.0.0/tos-download
            inputs:
              bucketName: $(parameters.TOS_BUCKET_NAME)
              bucketRegion: $(parameters.TOS_REGION)
              path: $TOS_PROJECT_FILE_PATH
              targetPath: $DOWNLOAD_PATH
          - step: extract
            displayName: Extract build context
            component: execCmd@1.0.0/shell
            inputs:
              cmd: |-
                mkdir -p $PROJECT_ROOT_DIR
                tar -zxvf $DOWNLOAD_PATH/$TOS_PROJECT_FILE_NAME -C $PROJECT_ROOT_DIR
              shell: BASH
          - step: build
            displayName: Build and push image
            component: build@2.0.0/buildkit-cr@5.0.0
            inputs:
              buildParams: "--build-arg PIP_INDEX_URL=$PIP_INDEX_URL --build-arg PYTHON_SOURCE_BASE_URL=$PYTHON_SOURCE_BASE_URL --build-arg PLAYWRIGHT_DOWNLOAD_HOST=$PLAYWRIGHT_DOWNLOAD_HOST"
              compression: gzip
              contextPath: $PROJECT_ROOT_DIR
              crDomain: $CR_DOMAIN
              disableSSLVerify: false
              loginCredential: []
              namespace: $CR_NAMESPACE
              region: $CR_REGION
              registryInstance: $CR_INSTANCE
              repo: $CR_OCI
              tag: $CR_TAG
              dockerfiles:
                default:
                  path: $DOCKERFILE_PATH
              useCache: true
              cacheType: default
              cacheUrl: ""
              nydusify: true
        outputs:
          - imageOutput_build
        workspace: {}
        resourcesPolicy: all
        resources:
          limits:
            cpu: 4C
            memory: 8Gi
"""


class EnvironmentResourceError(RuntimeError):
    pass


class EnvironmentCloudGateway(Protocol):
    def describe(self) -> EnvironmentResourceInfo: ...

    def start_build(
        self,
        *,
        context_key: str,
        image_tag: str,
    ) -> tuple[EnvironmentResources, str, str]: ...

    def build_status(
        self,
        resources: EnvironmentResources,
        run_id: str,
    ) -> EnvironmentBuildStatus: ...

    def build_steps(
        self,
        resources: EnvironmentResources,
        run_id: str,
    ) -> list[EnvironmentBuildStep]: ...

    def build_log(self, resources: EnvironmentResources, run_id: str) -> str: ...


@dataclass(frozen=True)
class EnvironmentResourceSettings:
    provider: StudioProvider
    region: str
    bucket: str
    cp_workspace: str = ""
    cr_repository: str = ""

    @classmethod
    def from_env(
        cls,
        *,
        provider: StudioProvider,
        region: str,
        bucket: str,
        source: Mapping[str, str] | None = None,
    ) -> EnvironmentResourceSettings:
        environment = source if source is not None else os.environ
        return cls(
            provider=provider,
            region=region,
            bucket=bucket,
            cp_workspace=str(environment.get(CP_WORKSPACE_ENV) or "").strip(),
            cr_repository=str(environment.get(CR_REPOSITORY_ENV) or "").strip(),
        )


class StudioEnvironmentCloudGateway:
    """Thin, injectable adapter around the existing AgentKit CP and CR clients."""

    def __init__(
        self,
        settings: EnvironmentResourceSettings,
        credentials: CloudCredentials | None = None,
        *,
        resolve_credentials: Callable[[], CloudCredentials] | None = None,
        resource_service: DeploymentResourceService | None = None,
    ) -> None:
        if settings.provider not in {"volcengine", "byteplus"}:
            raise ValueError(f"Unsupported environment provider: {settings.provider}")
        if not settings.region or not settings.bucket:
            raise ValueError("Environment builds require a TOS bucket and region.")
        self.settings = settings
        self.credentials = credentials
        self._resolve_credentials = resolve_credentials
        self._resources = resource_service

    def describe(self) -> EnvironmentResourceInfo:
        registry, namespace, repository = self._configured_cr()
        cp_source = "provided" if self.settings.cp_workspace else "managed"
        cr_source = "provided" if self.settings.cr_repository else "managed"
        return EnvironmentResourceInfo(
            provider=self.settings.provider,
            region=self.settings.region,
            codePipeline=CodePipelineResource(
                source=cp_source,
                workspaceId=self.settings.cp_workspace,
                workspaceName=self.settings.cp_workspace or _MANAGED_CP_WORKSPACE,
                pipelineName=_MANAGED_CP_PIPELINE,
                consoleUrl=self._cp_console_url(""),
            ),
            containerRegistry=ContainerRegistryResource(
                source=cr_source,
                registry=registry,
                namespace=namespace,
                repository=repository,
                consoleUrl=self._cr_console_url(registry),
            ),
        )

    def start_build(
        self,
        *,
        context_key: str,
        image_tag: str,
    ) -> tuple[EnvironmentResources, str, str]:
        try:
            cp = self._resolve_code_pipeline()
            cr = self._resolve_container_registry()
            image_repository = f"{cr.domain}/{cr.namespace}/{cr.repository}"
            cr = cr.model_copy(update={"image_repository": image_repository})
            resources = EnvironmentResources(
                provider=self.settings.provider,
                region=self.settings.region,
                codePipeline=cp,
                containerRegistry=cr,
            )
            parameters = [
                {"Key": "TOS_BUCKET_NAME", "Value": self.settings.bucket},
                {"Key": "TOS_REGION", "Value": self.settings.region},
                {"Key": "TOS_PROJECT_FILE_NAME", "Value": Path(context_key).name},
                {"Key": "TOS_PROJECT_FILE_PATH", "Value": context_key},
                {"Key": "PROJECT_ROOT_DIR", "Value": "/workspace/environment"},
                {"Key": "DOWNLOAD_PATH", "Value": "/workspace"},
                {
                    "Key": "DOCKERFILE_PATH",
                    "Value": "/workspace/environment/Dockerfile",
                },
                {"Key": "CR_INSTANCE", "Value": cr.registry},
                {"Key": "CR_DOMAIN", "Value": cr.domain},
                {"Key": "CR_NAMESPACE", "Value": cr.namespace},
                {"Key": "CR_OCI", "Value": cr.repository},
                {"Key": "CR_TAG", "Value": image_tag},
                {"Key": "CR_REGION", "Value": self.settings.region},
                {"Key": "PIP_INDEX_URL", "Value": self._pip_index_url()},
                {
                    "Key": "PYTHON_SOURCE_BASE_URL",
                    "Value": self._python_source_base_url(),
                },
                {
                    "Key": "PLAYWRIGHT_DOWNLOAD_HOST",
                    "Value": self._playwright_download_host(),
                },
            ]
            run_id = (
                self._resource_service()
                ._cp_client()
                .run_pipeline(
                    workspace_id=cp.workspace_id,
                    pipeline_id=cp.pipeline_id,
                    description=f"Build Studio environment image: {image_tag}",
                    parameters=parameters,
                )
            )
            return resources, str(run_id), f"{image_repository}:{image_tag}"
        except EnvironmentResourceError:
            raise
        except Exception as error:
            raise EnvironmentResourceError(
                f"启动环境镜像构建失败：{_safe_error(error, self.credentials)}"
            ) from error

    def _pip_index_url(self) -> str:
        if self.settings.provider == "volcengine":
            return "https://mirrors.aliyun.com/pypi/simple/"
        return "https://pypi.org/simple"

    def _python_source_base_url(self) -> str:
        if self.settings.provider == "volcengine":
            return "https://mirrors.huaweicloud.com/python"
        return "https://www.python.org/ftp/python"

    def _playwright_download_host(self) -> str:
        if self.settings.provider == "volcengine":
            return "https://npmmirror.com/mirrors/playwright"
        return "https://cdn.playwright.dev"

    def build_status(
        self,
        resources: EnvironmentResources,
        run_id: str,
    ) -> EnvironmentBuildStatus:
        cp = resources.code_pipeline
        try:
            status = str(
                self._resource_service()
                ._cp_client()
                .get_pipeline_run_status(
                    workspace_id=cp.workspace_id,
                    pipeline_id=cp.pipeline_id,
                    run_id=run_id,
                )
            ).casefold()
        except Exception as error:
            raise EnvironmentResourceError(
                f"查询环境镜像构建状态失败：{_safe_error(error, self.credentials)}"
            ) from error
        if status in {"succeeded", "success", "completed"}:
            return "available"
        if status in {"failed", "error", "canceled", "cancelled", "terminated"}:
            return "failed"
        if status in {"pending", "queued", "created", "waiting"}:
            return "queued"
        return "building"

    def build_steps(
        self,
        resources: EnvironmentResources,
        run_id: str,
    ) -> list[EnvironmentBuildStep]:
        cp = resources.code_pipeline
        try:
            payload = (
                self._resource_service()
                ._cp_client()
                .list_pipeline_run_stages_inner(
                    workspace_id=cp.workspace_id,
                    pipeline_id=cp.pipeline_id,
                    pipeline_run_id=run_id,
                )
            )
        except Exception as error:
            raise EnvironmentResourceError(
                f"查询环境镜像构建步骤失败：{_safe_error(error, self.credentials)}"
            ) from error

        steps: list[EnvironmentBuildStep] = []
        for stage in _items(payload):
            for task in _items(stage, "Tasks", "tasks"):
                for index, step in enumerate(_items(task, "Steps", "steps")):
                    raw_name = _value(step, "Name", "name") or f"step-{index + 1}"
                    label = _step_label(
                        raw_name,
                        _value(step, "DisplayName", "displayName", "display_name"),
                    )
                    steps.append(
                        EnvironmentBuildStep.model_validate(
                            {
                                "key": raw_name,
                                "label": label,
                                "status": _step_status(
                                    _value(step, "Status", "status", "State", "state")
                                ),
                                "startedAt": _value(
                                    step,
                                    "StartTime",
                                    "startTime",
                                    "startedAt",
                                    "started_at",
                                )
                                or None,
                                "finishedAt": _value(
                                    step,
                                    "FinishTime",
                                    "finishTime",
                                    "finishedAt",
                                    "finished_at",
                                )
                                or None,
                            }
                        )
                    )
        return steps

    def build_log(self, resources: EnvironmentResources, run_id: str) -> str:
        cp = resources.code_pipeline
        path = ""
        try:
            with tempfile.NamedTemporaryFile(
                prefix="veadk-environment-build-", suffix=".log", delete=False
            ) as temporary:
                path = temporary.name
            output = (
                self._resource_service()
                ._cp_client()
                .download_and_merge_pipeline_logs(
                    workspace_id=cp.workspace_id,
                    pipeline_id=cp.pipeline_id,
                    pipeline_run_id=run_id,
                    output_file=path,
                )
            )
            return _redact(
                Path(output).read_text(encoding="utf-8", errors="replace"),
                self.credentials,
            )
        except Exception as error:  # noqa: BLE001 - log retrieval is best effort
            return f"无法读取构建日志：{_safe_error(error, self.credentials)}"
        finally:
            if path:
                Path(path).unlink(missing_ok=True)

    def _resolve_code_pipeline(self) -> CodePipelineResource:
        client = self._resource_service()._cp_client()
        selector = self.settings.cp_workspace
        source = "provided" if selector else "managed"
        workspace_name = selector or _MANAGED_CP_WORKSPACE
        workspace = self._find_workspace(client, workspace_name)
        if workspace is None and selector:
            raise EnvironmentResourceError(
                f"指定的 CodePipeline Workspace 不存在：{selector}"
            )
        if workspace is None:
            workspace_id = str(
                client.create_workspace(
                    name=workspace_name,
                    visibility="Account",
                    description="AgentKit Studio environment image builds",
                )
            )
        else:
            workspace_id = _item_id(workspace)
            workspace_name = _item_name(workspace)

        pipelines = client.list_pipelines(
            workspace_id,
            page_size=100,
            name_filter=_MANAGED_CP_PIPELINE,
        ).get("Items", [])
        exact = next(
            (
                item
                for item in pipelines
                if isinstance(item, dict) and _item_name(item) == _MANAGED_CP_PIPELINE
            ),
            None,
        )
        if exact is not None:
            if not _is_agentkit_build_pipeline(client, exact):
                raise EnvironmentResourceError(
                    "同名 CodePipeline Pipeline 已存在，但不是兼容的环境镜像构建流水线。"
                )
            pipeline_id = _item_id(exact)
        else:
            pipeline_id = str(
                client._create_pipeline(
                    workspace_id=workspace_id,
                    pipeline_name=_MANAGED_CP_PIPELINE,
                    spec=_PIPELINE_SPEC,
                    parameters=_PIPELINE_PARAMETERS,
                )
            )
        return CodePipelineResource(
            source=source,
            workspaceId=workspace_id,
            workspaceName=workspace_name,
            pipelineId=pipeline_id,
            pipelineName=_MANAGED_CP_PIPELINE,
            consoleUrl=self._cp_console_url(workspace_id),
        )

    def _find_workspace(self, client: Any, selector: str) -> dict[str, Any] | None:
        by_name = client.get_workspaces_by_name(selector, page_size=100)
        exact_name = next(
            (
                item
                for item in by_name.get("Items", [])
                if isinstance(item, dict) and _item_name(item) == selector
            ),
            None,
        )
        if exact_name is not None:
            return exact_name
        try:
            by_id = client.list_workspaces(page_size=100, workspace_ids=[selector])
        except ValueError:  # Some CP regions reject non-ID selectors outright.
            return None
        return next(
            (
                item
                for item in by_id.get("Items", [])
                if isinstance(item, dict) and _item_id(item) == selector
            ),
            None,
        )

    def _resolve_container_registry(self) -> ContainerRegistryResource:
        registry, namespace, repository = self._configured_cr()
        source = "provided" if self.settings.cr_repository else "managed"
        resource_service = self._resource_service()
        client = resource_service._cr_client()
        if source == "provided":
            resource_service._require_existing_resource(
                "cr-registry", resource_id=registry
            )
            resource_service._require_existing_resource(
                "cr-namespace", resource_id=namespace, registry=registry
            )
            resource_service._require_existing_resource(
                "cr-repository",
                resource_id=repository,
                registry=registry,
                namespace=namespace,
            )
        else:
            if not self._cr_resource_exists("cr-registry", registry):
                client._create_instance(registry)
            if not self._cr_resource_exists(
                "cr-namespace", namespace, registry=registry
            ):
                client._create_namespace(registry, namespace)
            if not self._cr_resource_exists(
                "cr-repository",
                repository,
                registry=registry,
                namespace=namespace,
            ):
                client._create_repo(registry, namespace, repository)
        domain = str(client._get_default_domain(registry) or "").strip()
        if not domain:
            raise EnvironmentResourceError(
                f"无法获取容器镜像仓库 {registry} 的访问域名。"
            )
        parsed = urlsplit(domain if "://" in domain else f"//{domain}")
        domain = str(parsed.netloc or parsed.path).strip("/")
        return ContainerRegistryResource(
            source=source,
            registry=registry,
            namespace=namespace,
            repository=repository,
            domain=domain,
            imageRepository=f"{domain}/{namespace}/{repository}",
            consoleUrl=self._cr_console_url(registry),
        )

    def _cr_resource_exists(
        self,
        kind: str,
        resource_id: str,
        *,
        registry: str = "",
        namespace: str = "",
    ) -> bool:
        page = self._resource_service().list_resources(
            kind,
            registry=registry,
            namespace=namespace,
            search=resource_id,
            page_size=100,
        )
        return any(
            str(item.get("id") or "") == resource_id
            or str(item.get("name") or "") == resource_id
            for item in page.get("items", [])
            if isinstance(item, dict)
        )

    def _configured_cr(self) -> tuple[str, str, str]:
        if not self.settings.cr_repository:
            account_bucket = re.fullmatch(
                r"veadk-studio-([0-9]+)", self.settings.bucket
            )
            account_id = account_bucket.group(1) if account_bucket else ""
            managed_registry = (
                f"agentkit-platform-{account_id}"
                if account_id and self.settings.provider == "byteplus"
                else f"agentkit-cli-{account_id}"
                if account_id
                else _MANAGED_CR_REGISTRY
            )
            return (
                managed_registry,
                _MANAGED_CR_NAMESPACE,
                _MANAGED_CR_REPOSITORY,
            )
        parts = [part.strip() for part in self.settings.cr_repository.split("/")]
        if len(parts) != 3 or any(not part for part in parts):
            raise EnvironmentResourceError(
                f"{CR_REPOSITORY_ENV} 必须使用 registry/namespace/repository 格式。"
            )
        if any(
            value in {".", ".."} or any(char.isspace() for char in value)
            for value in parts
        ):
            raise EnvironmentResourceError("CR Repository 坐标包含非法字符。")
        return parts[0], parts[1], parts[2]

    def _resource_service(self) -> DeploymentResourceService:
        if self._resources is None:
            credentials = (
                self._resolve_credentials()
                if self._resolve_credentials is not None
                else self.credentials
            )
            self.credentials = credentials
            self._resources = DeploymentResourceService(
                self.settings.provider,
                self.settings.region,
                credentials,
            )
        return self._resources

    def _cp_console_url(self, workspace_id: str) -> str:
        host = (
            "console.byteplus.com"
            if self.settings.provider == "byteplus"
            else "console.volcengine.com"
        )
        suffix = f"/workspace/{workspace_id}" if workspace_id else ""
        return f"https://{host}/cp/region:{self.settings.region}{suffix}"

    def _cr_console_url(self, registry: str) -> str:
        host = (
            "console.byteplus.com"
            if self.settings.provider == "byteplus"
            else "console.volcengine.com"
        )
        return f"https://{host}/cr/region:{self.settings.region}/instance/{registry}"


def _item_name(item: Mapping[str, Any]) -> str:
    return str(item.get("Name") or item.get("name") or "").strip()


def _item_id(item: Mapping[str, Any]) -> str:
    return str(item.get("Id") or item.get("ID") or _item_name(item)).strip()


def _value(item: Any, *names: str) -> str:
    if isinstance(item, Mapping):
        for name in names:
            value = item.get(name)
            if value is not None:
                return str(value).strip()
        return ""
    for name in names:
        value = getattr(item, name, None)
        if value is not None:
            return str(value).strip()
    return ""


def _items(item: Any, *names: str) -> list[Any]:
    if not names:
        names = ("Items", "items")
    if isinstance(item, Mapping):
        for name in names:
            value = item.get(name)
            if isinstance(value, list):
                return value
        return []
    for name in names:
        value = getattr(item, name, None)
        if isinstance(value, list):
            return value
    return []


def _step_status(value: str) -> EnvironmentBuildStepStatus:
    status = value.casefold().replace("_", "").replace("-", "")
    if status in {"succeeded", "success", "completed", "complete", "passed"}:
        return "succeeded"
    if status in {"failed", "error", "canceled", "cancelled", "terminated"}:
        return "failed"
    if status in {"running", "executing", "inprogress", "processing"}:
        return "running"
    return "pending"


def _step_label(name: str, display_name: str) -> str:
    normalized = name.casefold()
    labels = {
        "download": "下载构建上下文",
        "extract": "解压构建上下文",
        "build": "构建并推送镜像",
    }
    return labels.get(normalized, display_name or name)


def _safe_error(error: BaseException, credentials: CloudCredentials | None) -> str:
    detail = str(error).strip() or type(error).__name__
    return _redact(detail, credentials)


def _redact(detail: str, credentials: CloudCredentials | None) -> str:
    for secret in credentials or ():
        if secret:
            detail = detail.replace(secret, "***")
    detail = re.sub(
        r'(?i)(["\']?(?:sessionToken|accessKeyId|secretAccessKey|access_key|secret_key|registryToken|dockerPassword|password|token)["\']?\s*[:=]\s*["\']?)([^"\',\s}]+)',
        r"\1***",
        detail,
    )
    detail = re.sub(
        r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)[^\s]+",
        r"\1***",
        detail,
    )
    return detail


__all__ = [
    "CP_WORKSPACE_ENV",
    "CR_REPOSITORY_ENV",
    "EnvironmentCloudGateway",
    "EnvironmentResourceError",
    "EnvironmentResourceSettings",
    "StudioEnvironmentCloudGateway",
]
