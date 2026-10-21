# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
# SPDX-License-Identifier: Apache-2.0

"""Pin Studio latest references before creating any Worker or Runtime intent."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import replace
from urllib.parse import urlsplit

import requests
from agentkit.toolkit.volcengine.cr import VeCR

from .database import DeploymentError

_MEDIA = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)
_LIMIT = 1024 * 1024
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


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
            "Latest snapshots require a trusted provider CR reference"
        )
    return match.groups()


def _read(response):
    try:
        body = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            body.extend(chunk)
            if len(body) > _LIMIT:
                raise DeploymentError("Registry response exceeds the snapshot limit")
        return bytes(body)
    finally:
        response.close()


def snapshot_image(image, cloud, *, selection=None):
    """Copy manifest bytes to a content-derived tag, or verify a saved selection."""
    host, repository = _reference(image, cloud.provider)
    base = f"https://{host}/v2/{repository}/manifests/"
    if selection is not None and (
        not isinstance(selection, dict)
        or not isinstance(selection.get("digest"), str)
        or not _DIGEST.fullmatch(selection["digest"])
        or selection.get("image")
        != image.removesuffix("latest") + "mpa-sha256-" + selection["digest"][7:]
    ):
        raise DeploymentError("Invalid registered image snapshot")
    try:
        credential = cloud._credentials()
        user, password, _ = VeCR(
            credential.access_key_id,
            credential.secret_access_key,
            region=cloud.region,
            provider=cloud.provider,
            session_token=credential.session_token,
        )._get_authorization_token(
            host.split(".", 1)[0].removesuffix("-" + cloud.region)
        )
        with requests.Session() as session:
            session.auth = (user, password)
            session.headers["Accept"] = ",".join(_MEDIA)

            def request(method, url, **kwargs):
                return session.request(
                    method,
                    url,
                    timeout=(10, 30),
                    allow_redirects=False,
                    stream=True,
                    **kwargs,
                )

            def manifest(reference, *, missing=False):
                response = request("GET", base + reference)
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
                        "GET",
                        params["realm"],
                        params={
                            "service": params.get("service", host),
                            "scope": f"repository:{repository}:pull,push",
                        },
                    )
                    if auth.status_code != 200:
                        auth.close()
                        raise DeploymentError("Registry token request failed")
                    tokens = json.loads(_read(auth))
                    token = tokens.get("token") or tokens.get("access_token")
                    if not isinstance(token, str) or not token:
                        raise DeploymentError("Registry token response is invalid")
                    session.auth = None
                    session.headers["Authorization"] = "Bearer " + token
                    response = request("GET", base + reference)
                if response.status_code == 404 and missing:
                    response.close()
                    return None
                if response.status_code != 200:
                    response.close()
                    raise DeploymentError("Unable to read registry image manifest")
                media = response.headers.get("Content-Type", "").split(";", 1)[0]
                declared = response.headers.get("Docker-Content-Digest")
                body = _read(response)
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
                return body, digest, media

            if selection is not None:
                saved = manifest(selection["image"].rsplit(":", 1)[1])
                assert saved is not None
                if saved[1] != selection["digest"]:
                    raise DeploymentError("Registered image snapshot content changed")
                return dict(selection)
            source = manifest("latest")
            assert source is not None
            tag = "mpa-sha256-" + source[1][7:]
            existing = manifest(tag, missing=True)
            if existing is None:
                response = request(
                    "PUT",
                    base + tag,
                    data=source[0],
                    headers={"Content-Type": source[2]},
                )
                response.close()
                if response.status_code not in (200, 201, 202):
                    raise DeploymentError("Unable to publish image snapshot tag")
                existing = manifest(tag)
            assert existing is not None
            if existing[1] != source[1]:
                raise DeploymentError("Image snapshot tag has conflicting content")
            return {"digest": source[1], "image": image.removesuffix("latest") + tag}
    except DeploymentError:
        raise
    except Exception:
        # SDK/HTTP/parser errors may include credentials or signed request URLs.
        raise DeploymentError(
            "Unable to resolve or verify Studio image snapshot"
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
