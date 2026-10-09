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

"""Anonymous, bounded OCI discovery for the two Studio image repositories."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone

import httpx

from veadk.integrations.mpa.managed.config import ConfigurationError
from veadk.integrations.mpa.managed.studio_profile import STUDIO_IMAGE_REPOSITORIES

_ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)
_DIGEST = re.compile(r"sha256:[a-f0-9]{64}")
_TAG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
_MAX_BYTES = 1024 * 1024


class _Registry:
    def __init__(
        self, client: httpx.AsyncClient, repository: str, slots: asyncio.Semaphore
    ):
        host, self.repository = repository.split("/", 1)
        self.origin = httpx.URL("https://" + host)
        self.root = str(self.origin).rstrip("/") + "/v2/" + self.repository
        self.client = client
        self.slots = slots
        self.token = ""

    def same_origin(self, url: httpx.URL) -> bool:
        return (
            url.scheme == "https"
            and url.host == self.origin.host
            and url.port in (None, 443)
            and not url.userinfo
        )

    async def read(self, url: str, *, blob=False, authenticate=True):
        selected = httpx.URL(url)
        for redirects in range(6):
            headers = {"Accept": _ACCEPT}
            if self.token and self.same_origin(selected) and authenticate:
                headers["Authorization"] = "Bearer " + self.token
            async with self.client.stream("GET", selected, headers=headers) as response:
                if (
                    response.status_code == 401
                    and authenticate
                    and self.same_origin(selected)
                ):
                    if self.token:
                        raise ConfigurationError(
                            "Public image registry authentication failed"
                        )
                    await self.authorize(response.headers.get("www-authenticate", ""))
                    return await self.read(url, blob=blob)
                if response.status_code in (301, 302, 303, 307, 308):
                    target = selected.join(response.headers.get("location", ""))
                    allowed_storage = bool(
                        target.host
                        and (
                            target.host.endswith(".volces.com")
                            or target.host.endswith(".volcengine.com")
                        )
                    )
                    if (
                        not blob
                        or redirects == 5
                        or target.scheme != "https"
                        or target.port not in (None, 443)
                        or target.userinfo
                        or not (self.same_origin(target) or allowed_storage)
                    ):
                        raise ConfigurationError(
                            "Public image registry redirect is invalid"
                        )
                    selected = target
                    continue
                if response.status_code != 200:
                    raise ConfigurationError("Public image registry request failed")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > _MAX_BYTES:
                        raise ConfigurationError(
                            "Public image registry metadata exceeds size limit"
                        )
                next_url = response.links.get("next", {}).get("url", "")
                return bytes(data), response.headers, next_url
        raise ConfigurationError("Public image registry redirect limit exceeded")

    async def authorize(self, challenge: str):
        if not challenge.startswith("Bearer "):
            raise ConfigurationError("Public image registry authentication is invalid")
        values = dict(re.findall(r'(realm|service|scope)="([^"\\]*)"', challenge))
        realm = httpx.URL(values.get("realm", ""))
        expected_scope = "repository:" + self.repository + ":pull"
        if (
            not self.same_origin(realm)
            or values.get("scope") != expected_scope
            or values.get("service") != "harbor-registry"
        ):
            raise ConfigurationError("Public image registry authentication is invalid")
        target = realm.copy_merge_params(
            {"service": values["service"], "scope": expected_scope}
        )
        data, _, _ = await self.read(str(target), authenticate=False)
        value = json.loads(data)
        token = value.get("token") or value.get("access_token")
        if not isinstance(token, str) or not token or len(token) > 16384:
            raise ConfigurationError("Public image registry authentication is invalid")
        self.token = token

    async def document(self, kind: str, reference: str):
        if kind == "blobs" or reference.startswith("sha256:"):
            if not _DIGEST.fullmatch(reference):
                raise ConfigurationError("Public image registry digest is invalid")
        data, headers, _ = await self.read(
            self.root + "/" + kind + "/" + reference, blob=kind == "blobs"
        )
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        expected = (
            reference
            if reference.startswith("sha256:")
            else headers.get("docker-content-digest", digest)
        )
        if digest != expected:
            raise ConfigurationError(
                "Public image registry digest does not match content"
            )
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ConfigurationError("Public image registry metadata is invalid")
        return value, digest

    async def candidate(self, tag: str):
        async with self.slots:
            manifest, digest = await self.document("manifests", tag)
            if "manifests" in manifest:
                entries = manifest["manifests"]
                if not isinstance(entries, list):
                    raise ConfigurationError(
                        "Public image registry metadata is invalid"
                    )
                matches = [
                    entry
                    for entry in entries
                    if entry.get("platform", {}).get("os") == "linux"
                    and entry.get("platform", {}).get("architecture") == "amd64"
                ]
                if not matches:
                    return None
                if len(matches) != 1:
                    raise ConfigurationError(
                        "Public image registry platform metadata is ambiguous"
                    )
                manifest, _ = await self.document("manifests", matches[0]["digest"])
            config, _ = await self.document("blobs", manifest["config"]["digest"])
            if config.get("os") != "linux" or config.get("architecture") != "amd64":
                return None
            created = config.get("created")
            if not isinstance(created, str):
                raise ConfigurationError(
                    "Public image registry build metadata is invalid"
                )
            timestamp = re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(\d{1,9}))?(?:Z|[+-]\d{2}:\d{2})",
                created,
            )
            if timestamp is None:
                raise ConfigurationError(
                    "Public image registry build metadata is invalid"
                )
            built = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if built.tzinfo is None:
                raise ConfigurationError(
                    "Public image registry build metadata is invalid"
                )
            nanos = int((timestamp.group(1) or "").ljust(9, "0"))
            return built.astimezone(timezone.utc), nanos, tag, digest

    async def latest(self):
        url = self.root + "/tags/list?n=100"
        seen_pages = set()
        tags = set()
        while url:
            selected = httpx.URL(url)
            if (
                not self.same_origin(selected)
                or selected.path != httpx.URL(self.root + "/tags/list").path
                or url in seen_pages
            ):
                raise ConfigurationError("Public image registry pagination is invalid")
            if len(seen_pages) >= 10:
                raise ConfigurationError(
                    "Public image registry pagination limit exceeded"
                )
            seen_pages.add(url)
            data, _, next_url = await self.read(url)
            values = json.loads(data).get("tags")
            if values is None:
                values = []
            if not isinstance(values, list) or any(
                not isinstance(tag, str) or not _TAG.fullmatch(tag) for tag in values
            ):
                raise ConfigurationError(
                    "Public image registry tag metadata is invalid"
                )
            tags.update(values)
            if len(tags) > 100:
                raise ConfigurationError("Public image registry tag limit exceeded")
            url = str(selected.join(next_url)) if next_url else ""
        candidates = await asyncio.gather(
            *(self.candidate(tag) for tag in sorted(tags)), return_exceptions=True
        )
        eligible = []
        for candidate in candidates:
            if isinstance(candidate, BaseException):
                raise candidate
            if candidate is not None:
                eligible.append(candidate)
        if not eligible:
            raise ConfigurationError("Public image registry has no Linux/amd64 image")
        return (
            str(self.origin).rstrip("/").removeprefix("https://")
            + "/"
            + self.repository
            + "@"
            + max(eligible)[3]
        )


async def resolve_studio_images(
    fields=("runtimeImage", "workerImage"), *, transport=None
) -> dict[str, str]:
    """Resolve only requested defaults, independently of deployment credentials."""

    async def resolve():
        async with httpx.AsyncClient(
            timeout=15, transport=transport, follow_redirects=False
        ) as client:
            slots = asyncio.Semaphore(4)
            results = {}
            for field in fields:
                results[field] = await _Registry(
                    client, STUDIO_IMAGE_REPOSITORIES[field], slots
                ).latest()
            return results

    try:
        return await asyncio.wait_for(resolve(), timeout=60)
    except ConfigurationError:
        raise
    except (httpx.HTTPError, asyncio.TimeoutError):
        raise ConfigurationError(
            "Public image registry is unavailable; retry image discovery"
        ) from None
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise ConfigurationError("Public image registry metadata is invalid") from None
