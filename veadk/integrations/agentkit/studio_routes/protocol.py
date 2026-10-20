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

"""Wire contract for Studio-owned HTTP routes executed by the local BFF."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ROUTE_PROTOCOL_VERSION = "studio-route-channel/2"
ROUTE_CONTROL_PATH = "/__studio/routes/v1"
ROUTE_CAPABILITIES_PATH = f"{ROUTE_CONTROL_PATH}/capabilities"
ROUTE_CHANNEL_PATH = f"{ROUTE_CONTROL_PATH}/channel"
ROUTE_HTTP_CHANNEL_PATH = f"{ROUTE_CHANNEL_PATH}/http"
ROUTE_HTTP_MESSAGE_PATH = f"{ROUTE_HTTP_CHANNEL_PATH}/{{channel_id}}/messages"

MAX_ROUTES = 128
MAX_ROUTE_CATALOG_BYTES = 256 * 1024
MAX_ROUTE_TIMEOUT_MS = 120_000
MAX_ROUTE_REQUEST_BODY_BYTES = 1024 * 1024
MAX_ROUTE_RESPONSE_BODY_BYTES = 2 * 1024 * 1024

RESERVED_ROUTE_PATHS = frozenset(
    {
        "/run",
        "/run_sse",
        "/invoke",
        "/ping",
        "/docs",
        "/openapi.json",
    }
)
RESERVED_ROUTE_PREFIXES = (
    "/__studio",
    "/oauth2",
    "/assets",
    "/health",
)
STUDIO_SKILL_CATALOG_ROUTE_PATHS = frozenset(
    {
        "/harness/skills/findskill",
        "/harness/skills/spaces",
        "/harness/skills/spaces/{space_id}/skills",
    }
)
_PATH_PARAMETER_SEGMENT = re.compile(r"^\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_REQUEST_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9._~-]{1,256}$")


class StudioRouteManifest(BaseModel):
    """The declarative, non-executable portion of one BFF-owned route."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
    method: Literal["GET", "POST"]
    path: str = Field(min_length=2, max_length=512)
    handler_revision: str = Field(min_length=1, max_length=128)
    timeout_ms: int = Field(default=30_000, ge=1, le=MAX_ROUTE_TIMEOUT_MS)
    response_mode: Literal["json", "text"] = "json"

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("route path must start with exactly one slash")
        if value.endswith("/"):
            raise ValueError("route path must not end with a slash")
        if "?" in value or "#" in value or "\x00" in value:
            raise ValueError("route path must not contain query, fragment, or NUL")
        if ".." in value.split("/"):
            raise ValueError("route path must not contain parent traversal")
        if "{" in value or "}" in value:
            if value not in STUDIO_SKILL_CATALOG_ROUTE_PATHS:
                raise ValueError(
                    "path parameters are limited to Studio Skill catalog routes"
                )
            parameter_names = []
            for segment in value.removeprefix("/").split("/"):
                if "{" not in segment and "}" not in segment:
                    if not re.fullmatch(r"[A-Za-z0-9._~-]+", segment):
                        raise ValueError("route path contains an invalid segment")
                    continue
                match = _PATH_PARAMETER_SEGMENT.fullmatch(segment)
                if match is None:
                    raise ValueError("route path parameters must occupy one segment")
                parameter_names.append(match.group(1))
            if len(parameter_names) != len(set(parameter_names)):
                raise ValueError("route path contains duplicate parameter names")
        elif not re.fullmatch(r"/[A-Za-z0-9._~/-]+", value):
            raise ValueError("route path must be URL-safe")
        return value


@dataclass(frozen=True)
class RouteCatalogSnapshot:
    """An immutable complete route catalog accepted from one Studio BFF."""

    revision: str
    routes: tuple[StudioRouteManifest, ...]


def route_catalog_revision(
    routes: list[dict[str, Any]] | list[StudioRouteManifest],
) -> str:
    """Return a stable digest for one complete route catalog."""

    manifests = [
        item.model_dump(mode="json")
        if isinstance(item, StudioRouteManifest)
        else StudioRouteManifest.model_validate(item).model_dump(mode="json")
        for item in routes
    ]
    manifests.sort(key=lambda item: (item["method"], item["path"], item["id"]))
    canonical = json.dumps(
        manifests,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def validate_route_catalog(
    *,
    revision: str,
    raw_routes: object,
    native_route_keys: set[tuple[str, str]],
) -> RouteCatalogSnapshot:
    """Validate a complete replacement without mutating the active catalog."""

    if not isinstance(raw_routes, list):
        raise ValueError("catalog routes must be a list")
    if len(raw_routes) > MAX_ROUTES:
        raise ValueError(f"catalog exceeds the {MAX_ROUTES}-route limit")
    encoded = json.dumps(raw_routes, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(encoded) > MAX_ROUTE_CATALOG_BYTES:
        raise ValueError("catalog exceeds the maximum encoded size")

    routes = tuple(StudioRouteManifest.model_validate(item) for item in raw_routes)
    ids = [route.id for route in routes]
    duplicate_ids = sorted({route_id for route_id in ids if ids.count(route_id) > 1})
    if duplicate_ids:
        raise ValueError(f"duplicate route ids: {', '.join(duplicate_ids)}")

    keys = [(route.method, route.path) for route in routes]
    duplicate_keys = sorted({key for key in keys if keys.count(key) > 1})
    if duplicate_keys:
        formatted = ", ".join(f"{method} {path}" for method, path in duplicate_keys)
        raise ValueError(f"duplicate dynamic routes: {formatted}")

    for route in routes:
        if route.path in STUDIO_SKILL_CATALOG_ROUTE_PATHS and route.method != "GET":
            raise ValueError(f"Studio Skill catalog route must use GET: {route.path}")
        reserved = route.path in RESERVED_ROUTE_PATHS or route.path.startswith(
            RESERVED_ROUTE_PREFIXES
        )
        if route.path.startswith("/harness") and (
            route.path not in STUDIO_SKILL_CATALOG_ROUTE_PATHS
        ):
            reserved = True
        if reserved:
            raise ValueError(f"reserved route path: {route.path}")
        if (route.method, route.path) in native_route_keys:
            raise ValueError(
                f"route conflicts with Runtime: {route.method} {route.path}"
            )

    expected_revision = route_catalog_revision(list(routes))
    if revision != expected_revision:
        raise ValueError("catalog revision does not match its route manifests")
    return RouteCatalogSnapshot(revision=revision, routes=routes)


def match_route_path(template: str, request_path: str) -> dict[str, str] | None:
    """Match one validated exact/segment-template route without regex input."""

    if "{" not in template:
        return {} if template == request_path else None
    template_segments = template.removeprefix("/").split("/")
    request_segments = request_path.removeprefix("/").split("/")
    if len(template_segments) != len(request_segments):
        return None
    parameters: dict[str, str] = {}
    for expected, actual in zip(template_segments, request_segments):
        parameter = _PATH_PARAMETER_SEGMENT.fullmatch(expected)
        if parameter is None:
            if expected != actual:
                return None
            continue
        if _REQUEST_PATH_SEGMENT.fullmatch(actual) is None:
            return None
        parameters[parameter.group(1)] = actual
    return parameters
