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

"""Validate the explicit cloud configuration for managed Studio Sidecar use."""

from __future__ import annotations

import re
from collections.abc import Mapping

from veadk.utils.cloud_provider import CloudProvider

SIDECAR_BASE_IMAGE_ENV = "VEADK_STUDIO_HARNESS_SIDECAR_BASE_IMAGE"
SIDECAR_REGIONS_ENV = "VEADK_STUDIO_HARNESS_SIDECAR_REGIONS"
DEFAULT_SIDECAR_BASE_IMAGE = (
    "superagent-cn-beijing.cr.volces.com/superagent/harness-sidecar@sha256:"
    "e722cc8dcf8ba8771ef20cbd01c939f9d1772e6e0a079e1e6811411104765e95"
)
_REGISTRY_HOST_RE = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[1-9][0-9]{0,4})?")
_REPOSITORY_COMPONENT_RE = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")


class StudioSidecarConfigurationError(ValueError):
    """Raised when Studio Sidecar cloud settings are incomplete or unsafe."""


def normalize_studio_sidecar_environment(
    *,
    provider: CloudProvider,
    base_image: str | None,
    regions: str | None,
    required: bool = False,
) -> dict[str, str]:
    """Return validated Sidecar environment values for a Studio function.

    An empty image is accepted unless ``required`` is true. Managed Sidecar
    images are public, immutable artifacts, so registry reachability is not
    coupled to the Studio or Runtime region. ``regions`` remains an accepted
    compatibility input but is deliberately not persisted or enforced.
    """

    image = str(base_image or "").strip()
    raw_regions = str(regions or "").strip()
    if not image and not raw_regions and not required:
        return {}
    if provider != "volcengine":
        raise StudioSidecarConfigurationError(
            "Managed Harness Sidecar is currently supported only on Volcengine."
        )
    if not image:
        if required:
            managed_studio_sidecar_base_image()
        return {}
    return {SIDECAR_BASE_IMAGE_ENV: managed_studio_sidecar_base_image(image)}


def resolve_studio_sidecar_environment(
    *,
    provider: CloudProvider,
    base_image: str | None,
    regions: str | None,
    current_environment: Mapping[str, object] | None,
) -> dict[str, str]:
    """Resolve explicit or inherited Sidecar settings for a Studio update.

    Supplying the image option makes it authoritative. With no explicit image,
    an existing image is inherited so an ordinary Studio update cannot
    silently remove the managed Sidecar runtime prerequisite. The legacy
    region option never controls public-image reachability.
    """

    if base_image is not None or regions is not None:
        selected_base_image = base_image
        selected_regions = regions
    else:
        environment = current_environment or {}
        selected_base_image = str(environment.get(SIDECAR_BASE_IMAGE_ENV) or "")
        selected_regions = str(environment.get(SIDECAR_REGIONS_ENV) or "")
    return normalize_studio_sidecar_environment(
        provider=provider,
        base_image=selected_base_image,
        regions=selected_regions,
    )


def _validate_immutable_image(image: str) -> None:
    if (
        "://" in image
        or any(character.isspace() for character in image)
        or image.count("@sha256:") != 1
    ):
        raise StudioSidecarConfigurationError(
            f"{SIDECAR_BASE_IMAGE_ENV} must be an immutable OCI image pinned by "
            "@sha256 digest."
        )


def managed_studio_sidecar_base_image(override: str | None = None) -> str:
    """Return the release-pinned public base or a validated operator override."""

    image = str(override or "").strip() or DEFAULT_SIDECAR_BASE_IMAGE
    _validate_immutable_image(image)
    name, digest = image.split("@sha256:", 1)
    host, separator, repository = name.partition("/")
    if (
        not separator
        or _REGISTRY_HOST_RE.fullmatch(host) is None
        or _DIGEST_RE.fullmatch(digest) is None
        or not repository
        or ":" in repository
        or any(
            _REPOSITORY_COMPONENT_RE.fullmatch(component) is None
            for component in repository.split("/")
        )
    ):
        raise StudioSidecarConfigurationError(
            f"{SIDECAR_BASE_IMAGE_ENV} must be an immutable OCI image pinned by "
            "@sha256 digest."
        )
    return image


__all__ = [
    "DEFAULT_SIDECAR_BASE_IMAGE",
    "SIDECAR_BASE_IMAGE_ENV",
    "SIDECAR_REGIONS_ENV",
    "StudioSidecarConfigurationError",
    "managed_studio_sidecar_base_image",
    "normalize_studio_sidecar_environment",
    "resolve_studio_sidecar_environment",
]
