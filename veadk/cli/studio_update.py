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

"""Locate and update an existing cloud-hosted Studio."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urljoin

import httpx
import requests
import volcenginesdkvefaas

from veadk.cli.frontend_branding import SiteLogo, resolve_site_logo
from veadk.integrations.ve_faas.ve_faas import VeFaaS
from veadk.utils.cloud_provider import (
    DEFAULT_CLOUD_PROVIDER,
    CloudProvider,
    default_region,
)

SUPPORTED_STUDIO_REGIONS = ("cn-beijing", "cn-shanghai")
_TRANSIENT_CLOUD_ERROR_MARKERS = (
    "connection aborted",
    "connection error",
    "connection reset",
    "connection timed out",
    "gateway timeout",
    "read timed out",
    "request timeout",
    "service unavailable",
    "temporarily unavailable",
    "the handshake operation timed out",
    "too many requests",
)


@dataclass(frozen=True)
class StudioDeploymentTarget:
    """Identifiers and scope of an existing Studio deployment."""

    application_name: str
    application_id: str
    function_id: str
    region: str
    project: str
    url: str


def find_studio_deployments(
    *,
    access_key: str,
    secret_key: str,
    session_token: str = "",
    application_name: str,
    region: str | None,
    project: str | None,
    provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
    attempts: int = 3,
    retry_delay_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> list[StudioDeploymentTarget]:
    """Find exact-name Studio Applications in the requested cloud scopes."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds must not be negative")
    regions = (
        (region,)
        if region is not None
        else (
            (default_region(provider),)
            if provider == "byteplus"
            else SUPPORTED_STUDIO_REGIONS
        )
    )
    targets = []
    for candidate_region in regions:
        service = VeFaaS(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            region=candidate_region,
            project_name=project or "default",
            provider=provider,
        )
        for attempt in range(1, attempts + 1):
            try:
                applications = service._list_application(app_name=application_name)
                region_targets = []
                for application in applications:
                    if application.get("Name") != application_name:
                        continue
                    target = _deployment_target(service, candidate_region, application)
                    if project is None or target.project == project:
                        region_targets.append(target)
            except Exception as error:
                if attempt >= attempts or not _is_retryable_cloud_read_error(error):
                    raise
                sleep(retry_delay_seconds * attempt)
                continue
            targets.extend(region_targets)
            break
    return targets


def load_deployed_site_logo(
    target: StudioDeploymentTarget,
    *,
    attempts: int = 3,
    retry_delay_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> SiteLogo | None:
    """Read the current logo so a code update does not reset branding."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds must not be negative")
    if not target.url:
        raise ValueError(
            "The existing Studio URL is unavailable; cannot safely preserve its logo."
        )
    config_url = urljoin(f"{target.url.rstrip('/')}/", "web/ui-config")
    for attempt in range(1, attempts + 1):
        try:
            response = httpx.get(config_url, follow_redirects=True, timeout=10.0)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            if attempt < attempts and _is_retryable_cloud_read_error(error):
                sleep(retry_delay_seconds * attempt)
                continue
            raise ValueError(
                f"Could not read existing Studio branding from {config_url}: "
                f"{error}. Retry later or pass --site-logo explicitly."
            ) from error
        break
    branding = payload.get("branding") if isinstance(payload, dict) else None
    if not isinstance(branding, dict) or "logoUrl" not in branding:
        raise ValueError(
            "The existing Studio did not return a recognizable branding configuration."
        )
    logo_url = branding.get("logoUrl")
    if not logo_url:
        return None
    return resolve_site_logo(urljoin(f"{target.url.rstrip('/')}/", str(logo_url)))


def _is_retryable_cloud_read_error(error: BaseException) -> bool:
    """Return whether a read-only cloud lookup failed transiently."""
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(
            current,
            (
                TimeoutError,
                ConnectionError,
                httpx.TimeoutException,
                httpx.NetworkError,
                requests.Timeout,
                requests.ConnectionError,
            ),
        ):
            return True
        message = str(current).lower()
        if any(marker in message for marker in _TRANSIENT_CLOUD_ERROR_MARKERS):
            return True
        current = current.__cause__ or current.__context__
    return False


def retry_transient_cloud_operation(
    operation: Callable[[], Any],
    *,
    attempts: int = 3,
    retry_delay_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Run an idempotent cloud operation with bounded transient retries."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds must not be negative")
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as error:
            if attempt >= attempts or not _is_retryable_cloud_read_error(error):
                raise
            sleep(retry_delay_seconds * attempt)
    raise AssertionError("unreachable")


def _deployment_target(
    service: VeFaaS,
    region: str,
    application: dict[str, Any],
) -> StudioDeploymentTarget:
    """Convert a VeFaaS Application response into an update target."""
    cloud_resource = application.get("CloudResource")
    if not cloud_resource:
        _, response = service._get_application_status(application["Id"])
        cloud_resource = response["Result"]["CloudResource"]
    resource = json.loads(cloud_resource)
    framework = resource["framework"]
    function_id = framework["function"]["Id"]
    function = cast(
        Any,
        service.client.get_function(
            volcenginesdkvefaas.GetFunctionRequest(id=function_id)
        ),
    )
    return StudioDeploymentTarget(
        application_name=application["Name"],
        application_id=application["Id"],
        function_id=function_id,
        region=region,
        project=function.project_name,
        url=framework.get("url", {}).get("system_url", ""),
    )
