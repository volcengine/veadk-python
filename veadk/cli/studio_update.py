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
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urljoin

import httpx
import volcenginesdkvefaas

from veadk.cli.frontend_branding import SiteLogo, resolve_site_logo
from veadk.integrations.ve_faas.ve_faas import VeFaaS

SUPPORTED_STUDIO_REGIONS = ("cn-beijing", "cn-shanghai")


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
    application_name: str,
    region: str | None,
    project: str | None,
) -> list[StudioDeploymentTarget]:
    """Find exact-name Studio Applications in the requested cloud scopes."""
    regions = (region,) if region is not None else SUPPORTED_STUDIO_REGIONS
    targets = []
    for candidate_region in regions:
        service = VeFaaS(
            access_key=access_key,
            secret_key=secret_key,
            region=candidate_region,
            project_name=project or "default",
        )
        applications = service._list_application(app_name=application_name)
        for application in applications:
            if application.get("Name") != application_name:
                continue
            target = _deployment_target(service, candidate_region, application)
            if project is None or target.project == project:
                targets.append(target)
    return targets


def load_deployed_site_logo(target: StudioDeploymentTarget) -> SiteLogo | None:
    """Read the current logo so a code update does not reset branding."""
    if not target.url:
        raise ValueError(
            "The existing Studio URL is unavailable; cannot safely preserve its logo."
        )
    config_url = urljoin(f"{target.url.rstrip('/')}/", "web/ui-config")
    try:
        response = httpx.get(config_url, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise ValueError(
            f"Could not read existing Studio branding from {config_url}: {error}"
        ) from error
    branding = payload.get("branding") if isinstance(payload, dict) else None
    if not isinstance(branding, dict) or "logoUrl" not in branding:
        raise ValueError(
            "The existing Studio did not return a recognizable branding configuration."
        )
    logo_url = branding.get("logoUrl")
    if not logo_url:
        return None
    return resolve_site_logo(urljoin(f"{target.url.rstrip('/')}/", str(logo_url)))


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
