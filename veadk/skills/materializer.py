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

"""Materialize VeADK remote skills into local directories loadable by ADK."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import frontmatter
from google.adk.skills import load_skill_from_dir

from veadk.skills.exceptions import SkillMaterializeError
from veadk.skills.skill import Skill
from veadk.skills.utils import (
    _get_agentkit_endpoint,
    _get_cloud_credentials,
    download_skillhub_skill,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_SKILL_MD_NAMES = ("SKILL.md", "skill.md")


def materialize_remote_skill(
    skill: Skill,
    *,
    cache_dir: Path | None = None,
) -> Path:
    """Download one remote VeADK skill and return an ADK-loadable skill dir."""
    base_cache_dir = _default_cache_dir() if cache_dir is None else Path(cache_dir)
    _ensure_cache_dir(base_cache_dir)

    source_type = "skillhub" if skill.source_type == "skillhub" else "skillspace"
    source_id = skill.skill_space_id or skill.id or "unknown-source"
    version_key = skill_version_key(skill)
    version_dir = (
        base_cache_dir
        / source_type
        / _safe_cache_part(source_id)
        / _safe_cache_part(skill.name)
        / _safe_cache_part(version_key)
    )

    cached = _cached_skill_dir(version_dir)
    if cached is not None:
        try:
            load_skill_from_dir(cached)
            logger.info(f"Using cached ADK skill '{skill.name}' from {cached}")
            return cached
        except Exception as e:
            logger.warning(
                f"Cached ADK skill '{skill.name}' at {cached} is invalid: {e}. "
                "Redownloading."
            )
            shutil.rmtree(version_dir)
    elif version_dir.exists():
        shutil.rmtree(version_dir)

    zip_path = version_dir / f"{_safe_cache_part(skill.name)}.zip"
    staging_dir = version_dir / "__staging__"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    version_dir.mkdir(parents=True, exist_ok=True)

    _download_remote_skill(skill, zip_path)
    try:
        _safe_extract_zip(zip_path, staging_dir)
    finally:
        if zip_path.exists():
            zip_path.unlink()

    final_dir = _normalize_extracted_skill_dir(staging_dir, version_dir, skill)
    try:
        load_skill_from_dir(final_dir)
    except Exception as e:
        raise SkillMaterializeError(
            f"Skill directory '{final_dir}' failed ADK load validation: {e}"
        ) from e

    _cleanup_old_versions(version_dir)
    return final_dir


def _download_remote_skill(skill: Skill, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    if skill.source_type == "skillhub":
        if not download_skillhub_skill(skill, zip_path):
            raise SkillMaterializeError(
                f"Failed to download SkillHub skill '{skill.name}'."
            )
        return

    if not _download_legacy_skill_space_skill(skill, zip_path):
        raise SkillMaterializeError(
            f"Failed to download skill-space skill '{skill.name}'."
        )


def _download_legacy_skill_space_skill(skill: Skill, zip_path: Path) -> bool:
    if not skill.bucket_name or not skill.path:
        raise SkillMaterializeError(
            f"Skill-space skill '{skill.name}' is missing bucket or TOS path."
        )

    access_key, secret_key, session_token = _get_cloud_credentials()
    service, region, host = _get_agentkit_endpoint()
    scheme = os.getenv("AGENTKIT_TOP_SCHEME", "https").lower()
    cloud_provider = (os.getenv("CLOUD_PROVIDER") or "").lower()

    if cloud_provider == "vestack":
        return _download_legacy_skill_via_vestack(
            skill=skill,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            service=service,
            region=region,
            host=host,
            scheme=scheme,
            zip_path=zip_path,
        )

    from veadk.integrations.ve_tos.ve_tos import VeTOS

    tos_client = VeTOS(
        ak=access_key,
        sk=secret_key,
        session_token=session_token,
        bucket_name=skill.bucket_name,
        region=region,
    )
    return tos_client.download(
        bucket_name=skill.bucket_name,
        object_key=skill.path,
        save_path=str(zip_path),
    )


def _download_legacy_skill_via_vestack(
    *,
    skill: Skill,
    access_key: str,
    secret_key: str,
    session_token: str,
    service: str,
    region: str,
    host: str,
    scheme: str,
    zip_path: Path,
) -> bool:
    import requests

    from veadk.utils.volcengine_sign import ve_request

    path_parts = skill.path.split("/")
    if len(path_parts) < 3:
        logger.error(f"Invalid TosPath format for skill '{skill.name}': {skill.path}")
        return False

    skill_id = skill.id or path_parts[1]
    skill_version = path_parts[2]
    response = ve_request(
        request_body={
            "SkillId": skill_id,
            "SkillVersion": skill_version,
        },
        action="GenTempTosObjectDownloadUrl",
        ak=access_key,
        sk=secret_key,
        service=service,
        version="2025-10-30",
        region=region,
        host=host,
        header={"X-Security-Token": session_token},
        scheme=scheme,  # type: ignore[arg-type]
    )

    if isinstance(response, str):
        response = json.loads(response)
    if (
        isinstance(response, dict)
        and "ResponseMetadata" in response
        and "Error" in response["ResponseMetadata"]
    ):
        logger.error(
            f"Failed to get temporary download URL for '{skill.name}': "
            f"{response['ResponseMetadata']['Error']}"
        )
        return False

    signed_url = (
        response.get("Result", {}).get("SignedUrl")
        if isinstance(response, dict)
        else None
    )
    if not signed_url:
        logger.error(
            f"Failed to get SignedUrl from GenTempTosObjectDownloadUrl response: {response}"
        )
        return False

    try:
        http_response = requests.get(signed_url, timeout=60)
        http_response.raise_for_status()
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        zip_path.write_bytes(http_response.content)
        return True
    except Exception as e:
        logger.error(f"Failed to download skill '{skill.name}' from vestack: {e}")
        return False


def _safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
    dest_root = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                member_name = member.filename
                if (
                    member_name.startswith(("/", "\\"))
                    or Path(member_name).is_absolute()
                ):
                    raise SkillMaterializeError(
                        f"Unsafe absolute path in zip archive: '{member_name}'"
                    )
                target = (dest_root / member_name).resolve()
                if target != dest_root and dest_root not in target.parents:
                    raise SkillMaterializeError(
                        f"Unsafe path detected in zip archive: '{member_name}'"
                    )
            zf.extractall(path=str(dest_root))
    except zipfile.BadZipFile as e:
        raise SkillMaterializeError(
            f"Downloaded file '{zip_path}' is not a valid zip archive."
        ) from e


def _normalize_extracted_skill_dir(
    staging_dir: Path,
    version_dir: Path,
    source_skill: Skill,
) -> Path:
    skill_dir = _find_extracted_skill_dir(staging_dir)
    skill_md = _find_skill_md(skill_dir)
    if skill_md is None:
        raise SkillMaterializeError(
            f"Skill '{source_skill.name}' has no SKILL.md or skill.md after extraction."
        )

    declared_name = frontmatter.load(str(skill_md)).metadata.get("name")
    if not declared_name:
        raise SkillMaterializeError(
            f"Skill '{source_skill.name}' SKILL.md has no 'name' in frontmatter."
        )
    declared_name = str(declared_name)
    if not _is_safe_dir_name(declared_name):
        raise SkillMaterializeError(
            f"Skill '{source_skill.name}' has unsafe frontmatter name: {declared_name!r}."
        )

    final_dir = version_dir / declared_name
    if final_dir.exists():
        shutil.rmtree(final_dir)

    if skill_dir == staging_dir:
        staging_dir.rename(final_dir)
    else:
        shutil.move(str(skill_dir), str(final_dir))
        if staging_dir.exists():
            shutil.rmtree(staging_dir)

    logger.info(
        f"Materialized remote skill '{source_skill.name}' "
        f"(declared name='{declared_name}') to {final_dir}"
    )
    return final_dir


def _find_extracted_skill_dir(staging_dir: Path) -> Path:
    if _find_skill_md(staging_dir):
        return staging_dir

    candidates = [
        path.parent
        for path in staging_dir.rglob("*")
        if path.is_file() and path.name in _SKILL_MD_NAMES
    ]
    if not candidates:
        return staging_dir

    return sorted(
        candidates,
        key=lambda p: (len(p.relative_to(staging_dir).parts), str(p)),
    )[0]


def _cached_skill_dir(version_dir: Path) -> Path | None:
    if not version_dir.exists():
        return None
    candidates = [
        child
        for child in version_dir.iterdir()
        if child.is_dir() and child.name != "__staging__" and _find_skill_md(child)
    ]
    if len(candidates) != 1:
        return None
    return candidates[0]


def _find_skill_md(skill_dir: Path) -> Path | None:
    for name in _SKILL_MD_NAMES:
        path = skill_dir / name
        if path.exists() and path.is_file():
            return path
    return None


def _default_cache_dir() -> Path:
    configured = os.getenv("VEADK_SKILLS_CACHE_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path(tempfile.gettempdir()) / "veadk" / "skills"


def _ensure_cache_dir(cache_dir: Path) -> None:
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise SkillMaterializeError(
            f"Unable to create VeADK skills cache directory '{cache_dir}': {e}. "
            "Pass cache_dir=... to VeSkillRegistry or set "
            "VEADK_SKILLS_CACHE_DIR to a writable directory."
        ) from e


def skill_version_key(skill: Skill) -> str:
    """Return the cache version key for a remote skill metadata record."""
    if skill.version_id:
        return str(skill.version_id)

    legacy_version = _legacy_skillspace_version_key(skill.path)
    if legacy_version:
        return legacy_version

    metadata = skill.model_dump(mode="json", exclude_none=True)
    digest = hashlib.sha256(
        json.dumps(metadata, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"metadata-{digest}"


def _legacy_skillspace_version_key(path: str) -> str | None:
    path_parts = [part for part in path.split("/") if part]
    if len(path_parts) >= 3 and path_parts[0] == "skills":
        return path_parts[2]
    return None


def _cleanup_old_versions(current_version_dir: Path) -> None:
    skill_dir = current_version_dir.parent
    try:
        for version_dir in skill_dir.iterdir():
            if version_dir == current_version_dir or not version_dir.is_dir():
                continue
            shutil.rmtree(version_dir)
    except Exception as e:
        logger.warning(
            f"Failed to clean old cached skill versions under {skill_dir}: {e}"
        )


def _safe_cache_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)
    cleaned = cleaned.strip("._-")
    return cleaned or "unknown"


def _is_safe_dir_name(value: str) -> bool:
    if not value or value in {".", ".."}:
        return False
    path = Path(value)
    return not path.is_absolute() and len(path.parts) == 1
