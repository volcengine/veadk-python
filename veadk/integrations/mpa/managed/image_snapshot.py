# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
# SPDX-License-Identifier: Apache-2.0

"""Pin Studio latest to an existing public tag before Worker/Runtime intents."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import replace
from urllib.parse import parse_qsl, urljoin, urlsplit

import requests

from .database import DeploymentError

_MEDIA = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)
_LIMIT = 1024 * 1024
_MAX_PAGES = 20
_MAX_TAGS = 1000
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TAG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z")


def _reference(image, provider):
    suffix = {"volcengine": "volces", "byteplus": "bytepluses"}.get(provider)
    pattern = (
        r"([a-z0-9][a-z0-9-]*\.cr\."
        + str(suffix)
        + r"\.com)/([a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)+):latest"
    )
    match = re.fullmatch(pattern, image)
    if not match or suffix is None:
        raise DeploymentError(
            "Latest discovery requires a trusted provider CR reference"
        )
    return match.groups()


def _read(response, deadline):
    try:
        body = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            if time.monotonic() >= deadline:
                raise DeploymentError("Registry discovery exceeded its time budget")
            body.extend(chunk)
            if len(body) > _LIMIT:
                raise DeploymentError("Registry response exceeds the discovery limit")
        return bytes(body)
    finally:
        response.close()


def snapshot_image(image, cloud, *, selection=None):
    """Select an existing public tag by digest, or verify a persisted selection."""
    host, repository = _reference(image, cloud.provider)
    prefix = image.removesuffix("latest")
    saved_tag = ""
    if selection is not None:
        if not isinstance(selection, dict):
            raise DeploymentError("Invalid registered image selection")
        saved_image = selection.get("image")
        saved_tag = (
            saved_image.removeprefix(prefix)
            if isinstance(saved_image, str) and saved_image.startswith(prefix)
            else ""
        )
        if (
            not isinstance(selection.get("digest"), str)
            or not _DIGEST.fullmatch(selection["digest"])
            or not _TAG.fullmatch(saved_tag)
            or saved_tag == "latest"
        ):
            raise DeploymentError("Invalid registered image selection")
    base = f"https://{host}/v2/{repository}/"
    deadline = time.monotonic() + 120
    try:
        with requests.Session() as session:
            # Discovery is anonymous: do not inherit netrc credentials or proxy auth.
            session.trust_env = False
            session.auth = None
            session.headers["Accept"] = ",".join(_MEDIA)

            def request(url, **kwargs):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DeploymentError("Registry discovery exceeded its time budget")
                return session.request(
                    "GET",
                    url,
                    timeout=(min(10, remaining), min(30, remaining)),
                    allow_redirects=False,
                    stream=True,
                    **kwargs,
                )

            def get(url):
                response = request(url)
                if response.status_code == 401:
                    challenge = response.headers.get("WWW-Authenticate", "")
                    response.close()
                    params = dict(re.findall(r'(\w+)="([^\"]*)"', challenge))
                    realm = urlsplit(params.get("realm", ""))
                    if (
                        not challenge.startswith("Bearer ")
                        or realm.scheme != "https"
                        or realm.hostname != host
                        or realm.port not in (None, 443)
                        or realm.username is not None
                        or realm.password is not None
                    ):
                        raise DeploymentError(
                            "Untrusted registry authentication challenge"
                        )
                    auth = request(
                        params["realm"],
                        params={
                            "service": params.get("service", host),
                            "scope": f"repository:{repository}:pull",
                        },
                    )
                    if auth.status_code != 200:
                        auth.close()
                        raise DeploymentError("Anonymous registry token request failed")
                    tokens = json.loads(_read(auth, deadline))
                    token = tokens.get("token") or tokens.get("access_token")
                    if (
                        not isinstance(token, str)
                        or not token.strip()
                        or "\n" in token
                        or "\r" in token
                    ):
                        raise DeploymentError("Registry token response is invalid")
                    session.headers["Authorization"] = "Bearer " + token
                    response = request(url)
                return response

            def manifest(tag, *, missing=False):
                response = get(base + "manifests/" + tag)
                if response.status_code == 404 and missing:
                    response.close()
                    return None
                if response.status_code != 200:
                    response.close()
                    raise DeploymentError("Unable to read public registry manifest")
                media = response.headers.get("Content-Type", "").split(";", 1)[0]
                declared = response.headers.get("Docker-Content-Digest")
                body = _read(response, deadline)
                digest = "sha256:" + hashlib.sha256(body).hexdigest()
                document = json.loads(body)
                if (
                    media not in _MEDIA
                    or declared != digest
                    or not isinstance(document, dict)
                    or document.get("schemaVersion") != 2
                    or document.get("mediaType", media) != media
                ):
                    raise DeploymentError("Registry manifest validation failed")
                return digest

            if selection is not None:
                if manifest(saved_tag) != selection["digest"]:
                    raise DeploymentError("Registered image selection content changed")
                return dict(selection)
            digest = manifest("latest")
            assert digest is not None
            page = base + "tags/list?n=100"
            seen, tags = set(), []
            while page:
                if page in seen or len(seen) >= _MAX_PAGES:
                    raise DeploymentError(
                        "Registry tag pagination exceeds discovery limits"
                    )
                seen.add(page)
                response = get(page)
                if response.status_code != 200:
                    response.close()
                    raise DeploymentError("Unable to list public registry tags")
                link = response.headers.get("Link", "")
                document = json.loads(_read(response, deadline))
                names = document.get("tags") if isinstance(document, dict) else False
                if names is None:
                    names = []
                if not isinstance(names, list) or any(
                    not isinstance(tag, str) or not _TAG.fullmatch(tag) for tag in names
                ):
                    raise DeploymentError("Invalid registry tag list")
                tags.extend(names)
                if len(tags) > _MAX_TAGS:
                    raise DeploymentError("Registry tag list exceeds discovery limits")
                page = ""
                if link:
                    links = requests.utils.parse_header_links(link)
                    following = [
                        item["url"] for item in links if item.get("rel") == "next"
                    ]
                    if len(following) != 1:
                        raise DeploymentError("Invalid registry tag pagination")
                    page = urljoin(base + "tags/list", following[0])
                    parsed = urlsplit(page)
                    query = parse_qsl(parsed.query, keep_blank_values=True)
                    if (
                        parsed.scheme != "https"
                        or parsed.hostname != host
                        or parsed.port not in (None, 443)
                        or parsed.username is not None
                        or parsed.password is not None
                        or parsed.fragment
                        or parsed.path != f"/v2/{repository}/tags/list"
                        or len(dict(query)) != len(query)
                        or any(key not in {"n", "last"} for key, _ in query)
                        or any(
                            not value.isdecimal() or not 1 <= int(value) <= 100
                            for key, value in query
                            if key == "n"
                        )
                        or any(
                            not _TAG.fullmatch(value)
                            for key, value in query
                            if key == "last"
                        )
                        or page in seen
                    ):
                        raise DeploymentError("Untrusted registry tag pagination")
            ordered = sorted(set(tags) - {"latest"}, reverse=True)
            preferred = "mpa-sha256-" + digest[7:]
            if preferred in ordered:
                ordered.remove(preferred)
                ordered.insert(0, preferred)
            for tag in ordered:
                if manifest(tag, missing=True) == digest:
                    return {"digest": digest, "image": prefix + tag}
            raise DeploymentError(
                "No existing version tag matches latest; publish a unique tag first"
            )
    except DeploymentError:
        raise
    except Exception:
        # HTTP/parser errors may include tokens or arbitrary remote response text.
        raise DeploymentError(
            "Unable to resolve or verify public Studio image selection"
        ) from None


async def pin_studio_images(profile, entry, cloud):
    """Persist both selections under the existing agent deployment lock."""
    inputs = profile.image_defaults()
    latest = {key: value for key, value in inputs.items() if value.endswith(":latest")}
    record = await entry.read()
    saved = record.get("image_snapshots")
    if saved is None and not latest:
        return profile
    if saved is not None:
        if (
            not isinstance(saved, dict)
            or saved.get("requested") != inputs
            or not isinstance(saved.get("selected"), dict)
            or set(saved["selected"]) != set(latest)
        ):
            raise DeploymentError("Registered image selection differs from the request")
    elif any(
        record.get(key)
        for key in (
            "worker_id",
            "worker_hash",
            "runtime_id",
            "request_hash",
            "pending",
        )
    ):
        raise DeploymentError(
            "Existing deployment has no image snapshot; use a new agent"
        )
    selected = {}
    for key, image in latest.items():
        selected[key] = await asyncio.to_thread(
            snapshot_image,
            image,
            cloud,
            selection=saved["selected"][key] if saved is not None else None,
        )
    if saved is None:
        record["image_snapshots"] = {"requested": inputs, "selected": selected}
        await entry.save(record)
    images = {key: choice["image"] for key, choice in selected.items()}
    managed = profile.managed.model_copy(deep=True)
    if "runtimeImage" in images:
        managed.runtime.image = images["runtimeImage"]
    if "workerImage" in images:
        managed.worker.image = images["workerImage"]
    return replace(profile, managed=managed)
