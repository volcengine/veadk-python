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
"""Recover an editable, source-preserving view of a legacy Runtime.

The control plane and OCI image are privileged server-side inputs. Parsers keep
MCP credentials separate from public configuration and browser-facing drafts.
Network and cloud clients are injected so the parsing and filesystem rules
remain independently testable.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import secrets
import tarfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Protocol
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from veadk.cli.generated_agent_skills import CanonicalSkillSnapshot

__all__ = [
    "apply_source_preserving_edits",
    "build_sidecar_mcp_servers_json",
    "build_source_preserving_overlay",
    "canonicalize_source_preserving_mcp_credentials",
    "ImageReference",
    "LegacyRecoveryError",
    "McpRecovery",
    "merge_mcp_recoveries",
    "mcp_reuse_supplied_credentials",
    "mcp_editor_draft_without_credentials",
    "mcp_secret_values_for_draft_references",
    "mcp_secret_values_from_runtime_environment",
    "mcp_secret_values_from_toolset",
    "OciImageInspector",
    "pin_source_image",
    "preserve_runtime_skills",
    "RecoveredSkill",
    "RegistryCredential",
    "recover_mcp_from_runtime_environment",
    "recover_mcp_from_toolset",
    "retained_mcp_secret_values",
    "resolve_source_preserving_mcp_owner",
    "resolve_source_preserving_mcp_secrets",
    "source_preserving_mcp_changed",
]

_IMAGE_HOST_RE = re.compile(
    r"^(?P<registry>[a-z0-9][a-z0-9-]{1,62})-(?P<region>cn-[a-z0-9-]+)"
    r"\.cr\.volces\.com$"
)
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REPOSITORY_COMPONENT_RE = re.compile(r"^[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*$")
_TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
_MCP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$")
_OCI_MANIFEST_TYPES = {
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
}
_OCI_INDEX_TYPES = {
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
}
_MANIFEST_ACCEPT = ", ".join(sorted(_OCI_MANIFEST_TYPES | _OCI_INDEX_TYPES))
_SUPPORTED_LAYER_TYPES = {
    "application/vnd.oci.image.layer.v1.tar",
    "application/vnd.oci.image.layer.v1.tar+gzip",
    "application/vnd.docker.image.rootfs.diff.tar",
    "application/vnd.docker.image.rootfs.diff.tar.gzip",
}
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_MAX_LAYER_BYTES = 1024 * 1024 * 1024
_MAX_LAYER_MEMBERS = 250_000
_MAX_SKILL_FILES = 256
_MAX_SKILL_FILE_BYTES = 1024 * 1024
_MAX_SKILL_TOTAL_BYTES = 8 * 1024 * 1024
_MAX_MCP_SECRET_BYTES = 8192


def _legacy_mcp_auth_reference(name: str, url: str) -> str:
    identity = hashlib.sha256(f"{name}\0{url}".encode("utf-8")).hexdigest()[:16]
    return f"VEADK_STUDIO_LEGACY_MCP_{identity.upper()}_AUTH_TOKEN"


_SITECUSTOMIZE = r'''"""Studio legacy Skill overlay; generated server-side."""
from __future__ import annotations

import json
import os
from pathlib import Path

_ROOT = Path(os.environ.get("VEADK_STUDIO_SKILL_OVERLAY", ""))


def _names(filename):
    value = json.loads((_ROOT / filename).read_text(encoding="utf-8"))
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise RuntimeError("Studio Skill overlay manifest is invalid: " + filename)
    names = set(value)
    if len(names) != len(value):
        raise RuntimeError("Studio Skill overlay manifest has duplicate names")
    return names


def _overlay_skills(selected):
    try:
        from google.adk.skills import load_skill_from_dir
    except Exception as error:
        raise RuntimeError("Studio Skill loader is unavailable") from error
    loaded = {}
    for name in sorted(selected):
        directory = _ROOT / "skills" / name
        if not directory.is_dir():
            raise RuntimeError("Studio Skill overlay directory is missing: " + name)
        try:
            skill = load_skill_from_dir(directory)
        except Exception as error:
            raise RuntimeError("Studio Skill overlay failed to load: " + name) from error
        loaded_name = str(getattr(skill, "name", ""))
        if loaded_name != name or loaded_name in loaded:
            raise RuntimeError("Studio Skill overlay identity is invalid: " + name)
        loaded[name] = skill
    return loaded


def _merge(original, managed, overlays):
    result = [
        item
        for item in list(original or [])
        if str(getattr(item, "name", "")) not in managed
    ]
    result.extend(overlays[name] for name in sorted(overlays))
    names = [str(getattr(item, "name", "")) for item in result]
    if not all(names) or len(names) != len(set(names)):
        raise RuntimeError("Studio Skill overlay produces duplicate identities")
    return result


def _apply_skills(root_agent):
    managed = _names("managed.json")
    selected = _names("selected.json")
    if not managed and not selected:
        return
    try:
        from google.adk.tools.skill_toolset import SkillToolset
    except Exception as error:
        raise RuntimeError("Studio SkillToolset is unavailable") from error
    overlays = _overlay_skills(selected)
    tools = list(getattr(root_agent, "tools", None) or [])
    toolsets = [tool for tool in tools if isinstance(tool, SkillToolset)]
    if len(toolsets) > 1:
        raise RuntimeError("Studio Skill overlay requires at most one root SkillToolset")
    if toolsets:
        toolset = toolsets[0]
        current = getattr(toolset, "_skills", None)
        if not isinstance(current, dict):
            raise RuntimeError("Studio SkillToolset layout is unsupported")
        merged = _merge(list(current.values()), managed, overlays)
        toolset._skills = {str(getattr(skill, "name", "")): skill for skill in merged}
        return
    if managed:
        raise RuntimeError("Studio cannot remove Skills without a root SkillToolset")
    tools.append(SkillToolset(skills=list(overlays.values()), registry=None))
    root_agent.tools = tools


def _mcp_configuration():
    value = json.loads((_ROOT / "mcp.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict) or any(
        not isinstance(name, str) or not name or not isinstance(items, list)
        for name, items in value.items()
    ):
        raise RuntimeError("Studio MCP overlay manifest is invalid")
    return value


def _replace_mcp(root_agent, configuration):
    if not configuration:
        return
    try:
        from google.adk.tools.mcp_tool.mcp_session_manager import (
            StreamableHTTPConnectionParams,
        )
        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
    except Exception as error:
        raise RuntimeError("Studio MCP overlay dependencies are unavailable") from error

    visited = set()

    def visit(agent):
        name = str(getattr(agent, "name", ""))
        if not name or name in visited:
            raise RuntimeError("Studio MCP overlay Agent identity is invalid")
        visited.add(name)
        configured = configuration.get(name)
        if isinstance(configured, list):
            tools = [
                item
                for item in list(getattr(agent, "tools", None) or [])
                if not isinstance(item, McpToolset)
            ]
            for item in configured:
                if not isinstance(item, dict) or item.get("transport") != "http":
                    raise RuntimeError("Studio MCP overlay entry is invalid")
                reference = str(item.get("authTokenEnv") or "")
                headers = None
                if reference:
                    token = os.environ.get(reference, "")
                    if not token:
                        raise RuntimeError(
                            "Configured MCP credential is unavailable: " + reference
                        )
                    headers = {"Authorization": "Bearer " + token}
                url = str(item.get("url") or "")
                if not url:
                    raise RuntimeError("Studio MCP overlay URL is unavailable")
                params = StreamableHTTPConnectionParams(url=url, headers=headers)
                tools.append(McpToolset(connection_params=params))
            agent.tools = tools
        for child in list(getattr(agent, "sub_agents", None) or []):
            visit(child)

    visit(root_agent)
    missing = set(configuration).difference(visited)
    if missing:
        raise RuntimeError("Studio MCP overlay Agent topology has changed")


def _mark_ready():
    marker = Path(
        os.environ.get(
            "VEADK_STUDIO_OVERLAY_READY_FILE",
            "/tmp/veadk-studio-overlay-ready",
        )
    )
    marker.write_text("ready\n", encoding="utf-8")


def _install():
    if not _ROOT.is_dir():
        raise RuntimeError("Studio overlay root is unavailable")

    try:
        from google.adk.apps.app import App
    except Exception as error:
        raise RuntimeError("Studio App compatibility hook is unavailable") from error
    original_app_init = App.__init__
    if getattr(original_app_init, "_veadk_studio_overlay", False):
        return

    def app_init(self, *args, **kwargs):
        original_app_init(self, *args, **kwargs)
        root_agent = getattr(self, "root_agent", None)
        if root_agent is None:
            raise RuntimeError("Studio overlay requires a root Agent")
        _apply_skills(root_agent)
        _replace_mcp(root_agent, _mcp_configuration())
        _mark_ready()

    app_init._veadk_studio_overlay = True
    App.__init__ = app_init


_install()
'''


class LegacyRecoveryError(RuntimeError):
    """A legacy snapshot is absent, ambiguous, or unsafe to edit."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def build_source_preserving_overlay(
    *,
    source_image: str,
    published_draft: Mapping[str, Any],
    edited_draft: Mapping[str, Any],
    canonical_skills: Iterable[CanonicalSkillSnapshot],
    application_mcp: bool,
) -> tuple[dict[str, str], ...]:
    """Build a minimal OCI layer that keeps the deployed application intact."""

    image = ImageReference.parse(source_image)
    if _DIGEST_RE.fullmatch(image.reference) is None or "@" not in source_image:
        raise LegacyRecoveryError("legacy_image_not_digest_pinned")

    def selected(value: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        items = value.get("selectedSkills")
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, Mapping)]

    managed_names: set[str] = set()
    published_runtime_skills: dict[str, tuple[str, str]] = {}
    for item in selected(published_draft):
        name = str(item.get("name") or item.get("folder") or "").strip()
        folder = str(item.get("folder") or name).strip()
        if (
            _SKILL_NAME_RE.fullmatch(name) is None
            or folder != name
            or name in managed_names
            or name in published_runtime_skills
        ):
            raise LegacyRecoveryError("legacy_overlay_published_skill_invalid")
        if item.get("source") == "runtime":
            published_runtime_skills[name] = (
                folder,
                str(item.get("description") or ""),
            )
        else:
            managed_names.add(name)
    selected_names: set[str] = set()
    preserved_runtime_names: set[str] = set()
    edited_names: set[str] = set()
    files: dict[str, str] = {}
    total_bytes = 0
    total_files = 0
    snapshots: dict[str, CanonicalSkillSnapshot] = {}
    for snapshot in canonical_skills:
        if snapshot.name in snapshots:
            raise LegacyRecoveryError("legacy_overlay_skill_duplicate")
        snapshots[snapshot.name] = snapshot
    for item in selected(edited_draft):
        name = str(item.get("name") or item.get("folder") or "").strip()
        folder = str(item.get("folder") or name).strip()
        if name in edited_names:
            raise LegacyRecoveryError("legacy_overlay_skill_duplicate")
        edited_names.add(name)
        if item.get("source") == "runtime":
            published_runtime = published_runtime_skills.get(name)
            if (
                published_runtime is None
                or folder != name
                or published_runtime != (folder, str(item.get("description") or ""))
            ):
                raise LegacyRecoveryError("legacy_overlay_runtime_skill_untrusted")
            preserved_runtime_names.add(name)
            continue
        if (
            _SKILL_NAME_RE.fullmatch(name) is None
            or folder != name
            or item.get("source") != "local"
        ):
            raise LegacyRecoveryError("legacy_overlay_skill_invalid")
        selected_names.add(name)
        snapshot = snapshots.get(name)
        if snapshot is None or not snapshot.files:
            raise LegacyRecoveryError("legacy_overlay_skill_files_missing")
        for canonical_file in snapshot.files:
            path = PurePosixPath(canonical_file.path)
            expected = PurePosixPath("skills") / name
            if (
                path.is_absolute()
                or any(part in {"", ".", ".."} for part in path.parts)
                or not path.is_relative_to(expected)
                or path == expected
            ):
                raise LegacyRecoveryError("legacy_overlay_skill_path_invalid")
            content = canonical_file.content
            size = len(content.encode("utf-8"))
            if size > _MAX_SKILL_FILE_BYTES:
                raise LegacyRecoveryError("legacy_skill_file_too_large")
            total_bytes += size
            total_files += 1
            if total_bytes > _MAX_SKILL_TOTAL_BYTES:
                raise LegacyRecoveryError("legacy_skill_total_too_large")
            if total_files > _MAX_SKILL_FILES:
                raise LegacyRecoveryError("legacy_skill_file_count_limit")
            target = PurePosixPath(".veadk-studio-overlay") / path
            if target.as_posix() in files:
                raise LegacyRecoveryError("legacy_overlay_skill_path_duplicate")
            files[target.as_posix()] = content
        if f".veadk-studio-overlay/skills/{name}/SKILL.md" not in files:
            raise LegacyRecoveryError("legacy_overlay_skill_manifest_missing")

    if set(snapshots) != selected_names:
        raise LegacyRecoveryError("legacy_overlay_skill_snapshot_untrusted")

    managed_names.update(
        set(published_runtime_skills).difference(preserved_runtime_names)
    )

    files[".veadk-studio-overlay/managed.json"] = json.dumps(
        sorted(managed_names), ensure_ascii=False, separators=(",", ":")
    )
    files[".veadk-studio-overlay/selected.json"] = json.dumps(
        sorted(selected_names), ensure_ascii=False, separators=(",", ":")
    )
    files[".veadk-studio-overlay/mcp.json"] = json.dumps(
        _source_preserving_mcp_configuration(edited_draft) if application_mcp else {},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    files[".veadk-studio-python/sitecustomize.py"] = _SITECUSTOMIZE
    files["Dockerfile"] = "\n".join(
        (
            f"FROM {source_image}",
            "COPY .veadk-studio-overlay /opt/veadk-studio-overlay",
            "COPY .veadk-studio-python /opt/veadk-studio-python",
            "ENV VEADK_STUDIO_SKILL_OVERLAY=/opt/veadk-studio-overlay",
            "ENV VEADK_STUDIO_OVERLAY_READY_FILE=/tmp/veadk-studio-overlay-ready",
            "ENV PYTHONPATH=/opt/veadk-studio-python:${PYTHONPATH}",
            "",
        )
    )
    files["app.py"] = (
        "# Build context marker only; the inherited image preserves its original "
        "entrypoint.\n"
    )
    return tuple(
        {"path": path, "content": content} for path, content in sorted(files.items())
    )


def source_preserving_mcp_changed(
    published_draft: Mapping[str, Any],
    edited_draft: Mapping[str, Any],
) -> bool:
    """Return whether the public MCP shape or credential references changed."""

    return _source_preserving_mcp_configuration(
        published_draft
    ) != _source_preserving_mcp_configuration(edited_draft)


def resolve_source_preserving_mcp_owner(
    *,
    sidecar_enabled: bool,
    effective_components: Iterable[str],
    mcp_toolset_id: str,
) -> str:
    """Resolve exactly one owner for source-preserving MCP configuration."""

    sidecar_owns_mcp = sidecar_enabled and bool(
        {str(item) for item in effective_components}
        & {"mcp_gateway", "mcp_resilience", "sql_readonly"}
    )
    platform_owns_mcp = bool(str(mcp_toolset_id or "").strip())
    if sidecar_owns_mcp and platform_owns_mcp:
        raise LegacyRecoveryError("legacy_mcp_ownership_ambiguous")
    if platform_owns_mcp:
        return "platform"
    if sidecar_owns_mcp:
        return "sidecar"
    return "application"


@dataclass(frozen=True)
class RegistryCredential:
    username: str
    password: str


@dataclass(frozen=True)
class ImageReference:
    registry_host: str
    registry_name: str
    region: str
    repository: str
    reference: str

    @classmethod
    def parse(cls, value: str) -> ImageReference:
        raw = str(value or "").strip()
        if "://" in raw or any(char.isspace() for char in raw):
            raise LegacyRecoveryError("legacy_image_reference_invalid")
        host, separator, remainder = raw.partition("/")
        match = _IMAGE_HOST_RE.fullmatch(host)
        if not separator or match is None:
            raise LegacyRecoveryError("legacy_image_registry_unsupported")
        repository = remainder
        reference = "latest"
        if "@" in remainder:
            repository, reference = remainder.rsplit("@", 1)
        else:
            last_slash = remainder.rfind("/")
            last_colon = remainder.rfind(":")
            if last_colon > last_slash:
                repository, reference = (
                    remainder[:last_colon],
                    remainder[last_colon + 1 :],
                )
        if (
            not repository
            or repository.startswith("/")
            or repository.endswith("/")
            or any(part in {"", ".", ".."} for part in repository.split("/"))
            or any(
                _REPOSITORY_COMPONENT_RE.fullmatch(part) is None
                for part in repository.split("/")
            )
            or not reference
            or (
                _DIGEST_RE.fullmatch(reference) is None
                and _TAG_RE.fullmatch(reference) is None
            )
            or len(repository) > 512
            or len(reference) > 256
        ):
            raise LegacyRecoveryError("legacy_image_reference_invalid")
        return cls(
            registry_host=host,
            registry_name=match.group("registry"),
            region=match.group("region"),
            repository=repository,
            reference=reference,
        )

    def pinned(self, digest: str) -> str:
        if _DIGEST_RE.fullmatch(digest) is None:
            raise LegacyRecoveryError("legacy_image_digest_invalid")
        return f"{self.registry_host}/{self.repository}@{digest}"


def pin_source_image(
    image: ImageReference,
    digest_provider: Callable[[ImageReference], str],
) -> str:
    """Pin a deployed tag using a trusted control-plane digest provider."""

    if _DIGEST_RE.fullmatch(image.reference):
        return image.pinned(image.reference)
    digest = str(digest_provider(image) or "").strip()
    if _DIGEST_RE.fullmatch(digest) is None:
        raise LegacyRecoveryError("legacy_image_digest_invalid")
    return image.pinned(digest)


def preserve_runtime_skills(
    names: Iterable[tuple[str, str]],
) -> tuple[dict[str, str], ...]:
    """Represent opaque deployed Skills without fabricating their files."""

    preserved: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_name, raw_description in names:
        name = str(raw_name or "").strip()
        description = str(raw_description or "")
        if (
            _SKILL_NAME_RE.fullmatch(name) is None
            or name in seen
            or len(description.encode("utf-8")) > _MAX_SKILL_FILE_BYTES
        ):
            raise LegacyRecoveryError("legacy_runtime_skill_invalid")
        seen.add(name)
        preserved.append(
            {
                "source": "runtime",
                "folder": name,
                "name": name,
                "description": description,
            }
        )
        if len(preserved) > 64:
            raise LegacyRecoveryError("legacy_runtime_skill_count_limit")
    return tuple(preserved)


@dataclass(frozen=True)
class RecoveredSkill:
    name: str
    description: str
    image_root: str
    files: tuple[dict[str, str], ...]
    digest: str

    def as_selected_skill(self) -> dict[str, Any]:
        return {
            "source": "local",
            "folder": self.name,
            "name": self.name,
            "description": self.description,
            "localFiles": [dict(item) for item in self.files],
        }


@dataclass(frozen=True)
class McpRecovery:
    tools: tuple[dict[str, Any], ...]
    configured_reference_keys: tuple[str, ...]
    format: str


def merge_mcp_recoveries(*recoveries: McpRecovery) -> McpRecovery:
    """Merge independently trusted MCP sources and reject ambiguity."""

    tools: list[dict[str, Any]] = []
    references: list[str] = []
    formats: list[str] = []
    seen_names: set[str] = set()
    seen_urls: set[str] = set()
    for recovery in recoveries:
        if recovery.format != "none":
            formats.append(recovery.format)
        for tool in recovery.tools:
            name = str(tool.get("name") or "")
            url = str(tool.get("url") or "")
            if name in seen_names or url in seen_urls:
                raise LegacyRecoveryError("legacy_mcp_recovery_duplicate")
            tools.append(dict(tool))
            seen_names.add(name)
            seen_urls.add(url)
        for reference in recovery.configured_reference_keys:
            if reference in references:
                raise LegacyRecoveryError("legacy_mcp_auth_reference_duplicate")
            references.append(reference)
    return McpRecovery(
        tools=tuple(tools),
        configured_reference_keys=tuple(references),
        format="+".join(formats) if formats else "none",
    )


def _draft_nodes(
    node: Mapping[str, Any], *, depth: int = 0
) -> Iterable[Mapping[str, Any]]:
    if depth > 16:
        raise LegacyRecoveryError("legacy_overlay_agent_graph_too_deep")
    yield node
    children = node.get("subAgents")
    if isinstance(children, list):
        if len(children) > 256:
            raise LegacyRecoveryError("legacy_overlay_agent_graph_too_large")
        for child in children:
            if isinstance(child, Mapping):
                yield from _draft_nodes(child, depth=depth + 1)
    workflow = node.get("workflow")
    workflow_nodes = workflow.get("nodes") if isinstance(workflow, Mapping) else None
    if isinstance(workflow_nodes, list):
        if len(workflow_nodes) > 256:
            raise LegacyRecoveryError("legacy_overlay_agent_graph_too_large")
        for item in workflow_nodes:
            child = item.get("agent") if isinstance(item, Mapping) else None
            if isinstance(child, Mapping):
                yield from _draft_nodes(child, depth=depth + 1)


def _draft_node_index(
    draft: Mapping[str, Any],
) -> dict[str, tuple[tuple[str, ...], Mapping[str, Any]]]:
    """Index a draft by stable Agent identity and its parent path."""

    indexed: dict[str, tuple[tuple[str, ...], Mapping[str, Any]]] = {}

    def visit(
        node: Mapping[str, Any], parent_path: tuple[str, ...], depth: int
    ) -> None:
        if depth > 16:
            raise LegacyRecoveryError("legacy_overlay_agent_graph_too_deep")
        name = str(node.get("name") or "").strip()
        if not name or name in indexed:
            raise LegacyRecoveryError("legacy_overlay_agent_identity_invalid")
        indexed[name] = (parent_path, node)
        child_path = (*parent_path, name)
        children = node.get("subAgents")
        if isinstance(children, list):
            if len(children) > 256:
                raise LegacyRecoveryError("legacy_overlay_agent_graph_too_large")
            for child in children:
                if not isinstance(child, Mapping):
                    raise LegacyRecoveryError("legacy_overlay_agent_graph_invalid")
                visit(child, child_path, depth + 1)
        workflow = node.get("workflow")
        workflow_nodes = (
            workflow.get("nodes") if isinstance(workflow, Mapping) else None
        )
        if isinstance(workflow_nodes, list):
            if len(workflow_nodes) > 256:
                raise LegacyRecoveryError("legacy_overlay_agent_graph_too_large")
            for item in workflow_nodes:
                child = item.get("agent") if isinstance(item, Mapping) else None
                if not isinstance(child, Mapping):
                    raise LegacyRecoveryError("legacy_overlay_agent_graph_invalid")
                visit(child, child_path, depth + 1)

    visit(draft, (), 0)
    return indexed


def apply_source_preserving_edits(
    published_draft: Mapping[str, Any],
    requested_draft: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply only editable Skill/MCP fields to a trusted published draft.

    The browser cannot replace instructions, models, topology, source files or
    deployment settings in source-preserving mode.  Those fields always come
    from the server-recovered immutable snapshot.
    """

    published = _draft_node_index(published_draft)
    requested = _draft_node_index(requested_draft)
    if {name: path for name, (path, _node) in published.items()} != {
        name: path for name, (path, _node) in requested.items()
    }:
        raise LegacyRecoveryError("legacy_overlay_agent_graph_changed")

    for name, (_path, node) in requested.items():
        deployment = node.get("deployment")
        if isinstance(deployment, Mapping) and "envValues" in deployment:
            requested_env_values = deployment.get("envValues")
            if requested_env_values is not None and not isinstance(
                requested_env_values, Mapping
            ):
                raise LegacyRecoveryError("legacy_overlay_draft_env_forbidden")
            published_deployment = published[name][1].get("deployment")
            published_env_values = (
                published_deployment.get("envValues")
                if isinstance(published_deployment, Mapping)
                else None
            )
            if requested_env_values and (
                not isinstance(published_env_values, Mapping)
                or dict(requested_env_values) != dict(published_env_values)
            ):
                raise LegacyRecoveryError("legacy_overlay_draft_env_forbidden")
        tools = node.get("mcpTools")
        if tools is None:
            continue
        if not isinstance(tools, list):
            raise LegacyRecoveryError("legacy_overlay_mcp_invalid")
        for tool in tools:
            if not isinstance(tool, Mapping):
                raise LegacyRecoveryError("legacy_overlay_mcp_invalid")
            if str(tool.get("authToken") or ""):
                raise LegacyRecoveryError("legacy_overlay_mcp_secret_forbidden")

    edited = copy.deepcopy(dict(published_draft))
    edited_nodes = _draft_node_index(edited)
    for name, (_path, target) in edited_nodes.items():
        source = requested[name][1]
        assert isinstance(target, dict)
        for field, empty in (
            ("mcpTools", []),
            ("selectedSkills", []),
            ("skills", []),
        ):
            raw_value = source.get(field, empty)
            if not isinstance(raw_value, list):
                raise LegacyRecoveryError(f"legacy_overlay_{field}_invalid")
            target[field] = copy.deepcopy(raw_value)
    return edited


def _mcp_tool_bindings(
    draft: Mapping[str, Any],
) -> dict[str, tuple[str, str, str]]:
    bindings: dict[str, tuple[str, str, str]] = {}
    for node in _draft_nodes(draft):
        agent_name = str(node.get("name") or "").strip()
        raw_tools = node.get("mcpTools")
        if raw_tools is None:
            continue
        if not isinstance(raw_tools, list):
            raise LegacyRecoveryError("legacy_overlay_mcp_invalid")
        for index, raw_tool in enumerate(raw_tools):
            if not isinstance(raw_tool, Mapping):
                raise LegacyRecoveryError("legacy_overlay_mcp_invalid")
            if str(raw_tool.get("transport") or "http") != "http":
                continue
            url = _safe_mcp_url(raw_tool.get("url"))
            name = _mcp_name(raw_tool.get("name"), url, index)
            reference = str(raw_tool.get("authTokenEnv") or "").strip()
            if not reference:
                continue
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", reference) is None:
                raise LegacyRecoveryError("legacy_mcp_auth_reference_invalid")
            if reference in bindings:
                raise LegacyRecoveryError("legacy_mcp_auth_reference_duplicate")
            bindings[reference] = (
                agent_name,
                name,
                _canonical_mcp_url_key(url),
            )
    return bindings


def _validated_secret(value: Any) -> str:
    secret = str(value or "")
    if (
        not secret
        or len(secret.encode("utf-8")) > _MAX_MCP_SECRET_BYTES
        or "\r" in secret
        or "\n" in secret
    ):
        raise LegacyRecoveryError("legacy_mcp_credential_invalid")
    return secret


def _canonical_supplied_mcp_credentials(
    *,
    draft: Mapping[str, Any],
    supplied_credentials: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, str, str], str]:
    """Bind submitted credentials to names canonicalized from the draft.

    Older Studio snapshots may contain human-readable MCP display names that
    predate the generated-name contract.  Such a name is accepted only when
    the submitted Agent/name/URL tuple exactly matches a tool in the current
    server-validated draft.  Arbitrary invalid names remain rejected.
    """

    aliases: dict[
        tuple[str, str, str],
        tuple[str, str, str],
    ] = {}
    for node in _draft_nodes(draft):
        agent_name = str(node.get("name") or "").strip()
        raw_tools = node.get("mcpTools")
        if not agent_name or not isinstance(raw_tools, list):
            continue
        for index, raw_tool in enumerate(raw_tools):
            if not isinstance(raw_tool, Mapping):
                continue
            if str(raw_tool.get("transport") or "http") != "http":
                continue
            url = _safe_mcp_url(raw_tool.get("url"))
            raw_name = str(raw_tool.get("name") or "").strip()
            canonical_name = _mcp_name(raw_name, url, index)
            url_key = _canonical_mcp_url_key(url)
            canonical_identity = (agent_name, canonical_name, url_key)
            candidate_names = [canonical_name]
            if not raw_name or (
                len(raw_name) <= 80
                and all(ord(character) >= 32 for character in raw_name)
                and "\x7f" not in raw_name
            ):
                candidate_names.append(raw_name)
            for candidate_name in candidate_names:
                alias = (agent_name, candidate_name, url_key)
                previous = aliases.get(alias)
                if previous is not None and previous != canonical_identity:
                    raise LegacyRecoveryError("legacy_mcp_recovery_duplicate")
                aliases[alias] = canonical_identity

    supplied: dict[tuple[str, str, str], str] = {}
    for index, raw in enumerate(supplied_credentials):
        if index >= 256 or not isinstance(raw, Mapping):
            raise LegacyRecoveryError("legacy_mcp_credential_input_invalid")
        agent_name = str(raw.get("agentName") or "").strip()
        name = str(raw.get("name") or "").strip()
        url = _safe_mcp_url(raw.get("url"))
        input_identity = (agent_name, name, _canonical_mcp_url_key(url))
        identity = aliases.get(input_identity)
        if identity is None:
            if not agent_name or _MCP_NAME_RE.fullmatch(name) is None:
                raise LegacyRecoveryError("legacy_mcp_credential_input_invalid")
            identity = input_identity
        if identity in supplied:
            raise LegacyRecoveryError("legacy_mcp_credential_input_duplicate")
        supplied[identity] = _validated_secret(raw.get("value"))
    return supplied


def resolve_source_preserving_mcp_secrets(
    *,
    published_draft: Mapping[str, Any],
    edited_draft: Mapping[str, Any],
    recovered_values: Mapping[str, str],
    supplied_values: Mapping[str, str],
) -> dict[str, str]:
    """Resolve active MCP credentials without trusting browser references.

    A recovered secret may only remain attached to the exact Agent/name/URL
    identity from the published snapshot.  A newly supplied value may replace
    it or authenticate a new endpoint.
    """

    published = _mcp_tool_bindings(published_draft)
    edited = _mcp_tool_bindings(edited_draft)
    resolved: dict[str, str] = {}
    for reference, identity in edited.items():
        supplied = str(supplied_values.get(reference) or "")
        if supplied:
            resolved[reference] = _validated_secret(supplied)
            continue
        if reference not in published:
            raise LegacyRecoveryError("legacy_mcp_credential_missing")
        if published[reference] != identity:
            raise LegacyRecoveryError("legacy_mcp_credential_identity_changed")
        recovered = recovered_values.get(reference)
        if not recovered:
            raise LegacyRecoveryError("legacy_mcp_credential_missing")
        resolved[reference] = _validated_secret(recovered)
    return resolved


def canonicalize_source_preserving_mcp_credentials(
    *,
    published_draft: Mapping[str, Any],
    edited_draft: Mapping[str, Any],
    recovered_values: Mapping[str, str],
    supplied_credentials: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Bind MCP secrets to server-validated endpoint identities.

    Browser-selected environment names are never authoritative. Existing
    credentials retain their published reference only for an exact
    Agent/name/URL match; new values receive a server-generated reference.
    Source-preserving v1 deliberately supports HTTP MCP only.
    """

    canonical = copy.deepcopy(dict(edited_draft))
    published_bindings = _mcp_tool_bindings(published_draft)
    published_by_identity: dict[tuple[str, str, str], str] = {}
    for reference, identity in published_bindings.items():
        if identity in published_by_identity:
            raise LegacyRecoveryError("legacy_mcp_recovery_duplicate")
        published_by_identity[identity] = reference

    supplied = _canonical_supplied_mcp_credentials(
        draft=canonical,
        supplied_credentials=supplied_credentials,
    )

    used_supplied: set[tuple[str, str, str]] = set()
    resolved: dict[str, str] = {}
    seen_identities: set[tuple[str, str, str]] = set()
    for agent_name, (_path, node) in _draft_node_index(canonical).items():
        tools = node.get("mcpTools")
        if tools is None:
            continue
        if not isinstance(tools, list):
            raise LegacyRecoveryError("legacy_overlay_mcp_invalid")
        for index, raw_tool in enumerate(tools):
            if not isinstance(raw_tool, dict):
                raise LegacyRecoveryError("legacy_overlay_mcp_invalid")
            if str(raw_tool.get("transport") or "http") != "http":
                raise LegacyRecoveryError("legacy_overlay_mcp_stdio_unsupported")
            url = _safe_mcp_url(raw_tool.get("url"))
            name = _mcp_name(raw_tool.get("name"), url, index)
            identity = (agent_name, name, _canonical_mcp_url_key(url))
            if identity in seen_identities:
                raise LegacyRecoveryError("legacy_mcp_recovery_duplicate")
            seen_identities.add(identity)
            raw_tool["name"] = name
            raw_tool["transport"] = "http"
            raw_tool["url"] = url
            requested_reference = str(raw_tool.get("authTokenEnv") or "").strip()
            published_reference = published_by_identity.get(identity, "")
            supplied_value = supplied.get(identity, "")
            if supplied_value:
                reference = published_reference or _source_preserving_mcp_reference(
                    *identity
                )
                raw_tool["authTokenEnv"] = reference
                resolved[reference] = supplied_value
                used_supplied.add(identity)
                continue
            if published_reference and requested_reference == published_reference:
                recovered = recovered_values.get(published_reference)
                if not recovered:
                    raise LegacyRecoveryError("legacy_mcp_credential_missing")
                raw_tool["authTokenEnv"] = published_reference
                resolved[published_reference] = _validated_secret(recovered)
                continue
            if requested_reference:
                raise LegacyRecoveryError("legacy_mcp_credential_missing")
            raw_tool.pop("authTokenEnv", None)

    if used_supplied != set(supplied):
        raise LegacyRecoveryError("legacy_mcp_credential_identity_changed")
    return canonical, resolved


def _source_preserving_mcp_reference(
    agent_name: str,
    name: str,
    url: str,
) -> str:
    identity = hashlib.sha256(
        f"{agent_name}\0{name}\0{url}".encode("utf-8")
    ).hexdigest()[:16]
    return f"VEADK_STUDIO_LEGACY_MCP_{identity.upper()}_AUTH_TOKEN"


def build_sidecar_mcp_servers_json(
    *,
    draft: Mapping[str, Any],
    secret_values: Mapping[str, str],
    supplied_credentials: Iterable[Mapping[str, Any]] = (),
) -> str:
    """Build the Sidecar MCP server list entirely on the Studio server."""

    supplied = _canonical_supplied_mcp_credentials(
        draft=draft,
        supplied_credentials=supplied_credentials,
    )

    servers: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_urls: set[str] = set()
    used_supplied: set[tuple[str, str, str]] = set()
    for node in _draft_nodes(draft):
        agent_name = str(node.get("name") or "").strip()
        if not agent_name:
            raise LegacyRecoveryError("legacy_overlay_agent_identity_invalid")
        raw_tools = node.get("mcpTools")
        if not isinstance(raw_tools, list):
            continue
        for index, raw_tool in enumerate(raw_tools):
            if not isinstance(raw_tool, Mapping):
                raise LegacyRecoveryError("legacy_overlay_mcp_invalid")
            if str(raw_tool.get("transport") or "http") != "http":
                continue
            url = _safe_mcp_url(raw_tool.get("url"))
            name = _mcp_name(raw_tool.get("name"), url, index)
            url_key = _canonical_mcp_url_key(url)
            if name in seen_names:
                raise LegacyRecoveryError("legacy_mcp_name_duplicate")
            if url_key in seen_urls:
                raise LegacyRecoveryError("legacy_mcp_url_duplicate")
            reference = str(raw_tool.get("authTokenEnv") or "").strip()
            identity = (agent_name, name, url_key)
            server: dict[str, Any] = {"name": name, "url": url}
            secret = supplied.get(identity, "")
            if secret:
                used_supplied.add(identity)
            elif reference:
                secret = secret_values.get(reference, "")
                if not secret:
                    raise LegacyRecoveryError("legacy_mcp_credential_missing")
            if secret:
                server["headers"] = {
                    "Authorization": "Bearer " + _validated_secret(secret)
                }
            servers.append(server)
            seen_names.add(name)
            seen_urls.add(url_key)
    if used_supplied != set(supplied):
        raise LegacyRecoveryError("legacy_mcp_credential_identity_changed")
    return json.dumps(servers, ensure_ascii=False, separators=(",", ":"))


def mcp_editor_draft_without_credentials(
    draft: Mapping[str, Any],
) -> dict[str, Any]:
    """Return an editor draft containing references but never secret values."""

    sanitized = copy.deepcopy(dict(draft))
    for node in _draft_nodes(sanitized):
        raw_tools = node.get("mcpTools")
        if not isinstance(raw_tools, list):
            continue
        for raw_tool in raw_tools:
            if not isinstance(raw_tool, dict):
                raise LegacyRecoveryError("legacy_overlay_mcp_invalid")
            raw_tool.pop("authToken", None)
    return sanitized


def _source_preserving_mcp_configuration(
    draft: Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    configuration: dict[str, list[dict[str, Any]]] = {}
    total = 0
    for node in _draft_nodes(draft):
        name = str(node.get("name") or "").strip()
        if not name or name in configuration:
            raise LegacyRecoveryError("legacy_overlay_agent_identity_invalid")
        raw_tools = node.get("mcpTools")
        if not isinstance(raw_tools, list):
            raw_tools = []
        normalized: list[dict[str, Any]] = []
        for index, raw_tool in enumerate(raw_tools):
            total += 1
            if total > 256 or not isinstance(raw_tool, Mapping):
                raise LegacyRecoveryError("legacy_overlay_mcp_invalid")
            transport = str(raw_tool.get("transport") or "http")
            tool_name = str(raw_tool.get("name") or f"mcp_{index + 1}").strip()
            if _MCP_NAME_RE.fullmatch(tool_name) is None:
                raise LegacyRecoveryError("legacy_mcp_name_invalid")
            if transport == "http":
                url = _safe_mcp_url(raw_tool.get("url"))
                reference = str(raw_tool.get("authTokenEnv") or "").strip()
                if (
                    reference
                    and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", reference) is None
                ):
                    raise LegacyRecoveryError("legacy_mcp_auth_reference_invalid")
                normalized.append(
                    {
                        "name": tool_name,
                        "transport": "http",
                        "url": url,
                        "authTokenEnv": reference,
                    }
                )
                continue
            if transport != "stdio":
                raise LegacyRecoveryError("legacy_overlay_mcp_transport_invalid")
            command = str(raw_tool.get("command") or "").strip()
            args = raw_tool.get("args")
            if (
                not command
                or len(command) > 4096
                or "\x00" in command
                or not isinstance(args, list)
                or len(args) > 128
                or any(
                    not isinstance(value, str) or len(value) > 8192 or "\x00" in value
                    for value in args
                )
            ):
                raise LegacyRecoveryError("legacy_overlay_mcp_stdio_invalid")
            normalized.append(
                {
                    "name": tool_name,
                    "transport": "stdio",
                    "command": command,
                    "args": list(args),
                }
            )
        configuration[name] = normalized
    return configuration


def _safe_mcp_url(value: Any) -> str:
    url = str(value or "").strip()
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as error:
        raise LegacyRecoveryError("legacy_mcp_url_invalid") from error
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or len(url) > 4096
    ):
        raise LegacyRecoveryError("legacy_mcp_url_invalid")
    del port
    return url


def _canonical_mcp_url_key(value: Any) -> str:
    """Normalize an HTTP MCP URL for equality checks without rewriting it."""

    url = _safe_mcp_url(value)
    parsed = urlsplit(url)
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").casefold()
    host = f"[{hostname}]" if ":" in hostname else hostname
    port = parsed.port
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    path = parsed.path.rstrip("/")
    return f"{scheme}://{host}{path}"


def _mcp_name(value: Any, url: str, index: int) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        candidate = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    candidate = re.sub(r"[^A-Za-z0-9_.-]+", "_", candidate).strip("_.-")
    if not candidate:
        candidate = f"mcp_{index + 1}"
    if _MCP_NAME_RE.fullmatch(candidate) is None:
        raise LegacyRecoveryError("legacy_mcp_name_invalid")
    return candidate


def _valid_headers(value: Any) -> bool:
    if not isinstance(value, Mapping) or len(value) > 16:
        return False
    for raw_name, raw_value in value.items():
        name = str(raw_name or "").strip()
        header_value = str(raw_value or "")
        if (
            _HEADER_NAME_RE.fullmatch(name) is None
            or not header_value
            or len(header_value) > 8192
            or "\r" in header_value
            or "\n" in header_value
        ):
            return False
    return True


def _bearer_token(value: Any) -> str:
    if value in (None, {}):
        return ""
    if not _valid_headers(value):
        raise LegacyRecoveryError("legacy_mcp_headers_invalid")
    headers = {
        str(name).strip().casefold(): str(header_value)
        for name, header_value in value.items()
    }
    if set(headers) != {"authorization"}:
        raise LegacyRecoveryError("legacy_mcp_headers_unsupported")
    authorization = headers["authorization"]
    if not authorization.startswith("Bearer ") or not authorization[7:]:
        raise LegacyRecoveryError("legacy_mcp_headers_unsupported")
    return authorization[7:]


def recover_mcp_from_runtime_environment(
    environment: Mapping[str, str],
) -> McpRecovery:
    """Recover public MCP shape while retaining secrets only by opaque key.

    ``MCP_SERVERS_JSON`` may contain arbitrary authentication headers.  The
    browser sees the server name and URL plus the environment key as an opaque
    configured marker, never the JSON/header values.
    """

    raw_servers = str(environment.get("MCP_SERVERS_JSON") or "").strip()
    if raw_servers:
        try:
            payload = json.loads(raw_servers)
        except (TypeError, ValueError) as error:
            raise LegacyRecoveryError("legacy_mcp_servers_json_invalid") from error
        if not isinstance(payload, list) or not 1 <= len(payload) <= 32:
            raise LegacyRecoveryError("legacy_mcp_servers_json_invalid")
        tools: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for index, item in enumerate(payload):
            if not isinstance(item, Mapping):
                raise LegacyRecoveryError("legacy_mcp_servers_json_invalid")
            url = _safe_mcp_url(item.get("url"))
            name = _mcp_name(item.get("name"), url, index)
            if name in seen_names:
                raise LegacyRecoveryError("legacy_mcp_servers_json_duplicate")
            token = _bearer_token(item.get("headers"))
            configured = bool(token)
            reference = _legacy_mcp_auth_reference(name, url) if configured else ""
            tools.append(
                {
                    "name": name,
                    "transport": "http",
                    "url": url,
                    "authTokenEnv": reference,
                }
            )
            seen_names.add(name)
        return McpRecovery(
            tools=tuple(tools),
            configured_reference_keys=tuple(
                str(item["authTokenEnv"]) for item in tools if item["authTokenEnv"]
            ),
            format="servers-json",
        )

    raw_urls = str(environment.get("MCP_URLS") or "").strip()
    if not raw_urls:
        return McpRecovery(tools=(), configured_reference_keys=(), format="none")
    urls = [item.strip() for item in raw_urls.split(",") if item.strip()]
    if not 1 <= len(urls) <= 32:
        raise LegacyRecoveryError("legacy_mcp_urls_invalid")
    configured = bool(str(environment.get("MCP_API_KEY") or ""))
    tools = []
    seen: set[str] = set()
    for index, item in enumerate(urls):
        url = _safe_mcp_url(item)
        if url in seen:
            raise LegacyRecoveryError("legacy_mcp_urls_duplicate")
        tools.append(
            {
                "name": _mcp_name("", url, index),
                "transport": "http",
                "url": url,
                "authTokenEnv": (
                    _legacy_mcp_auth_reference(_mcp_name("", url, index), url)
                    if configured
                    else ""
                ),
            }
        )
        seen.add(url)
    return McpRecovery(
        tools=tuple(tools),
        configured_reference_keys=tuple(
            str(item["authTokenEnv"]) for item in tools if item["authTokenEnv"]
        ),
        format="urls",
    )


def mcp_secret_values_from_runtime_environment(
    environment: Mapping[str, str],
) -> dict[str, str]:
    """Return legacy MCP secrets keyed by opaque editor references.

    The result is server-only deployment input.  Callers must never serialize,
    log or persist it outside the Runtime environment update request.
    """

    recovery = recover_mcp_from_runtime_environment(environment)
    if recovery.format == "servers-json":
        payload = json.loads(str(environment.get("MCP_SERVERS_JSON") or ""))
        values: dict[str, str] = {}
        for tool, item in zip(recovery.tools, payload, strict=True):
            reference = str(tool.get("authTokenEnv") or "")
            token = _bearer_token(item.get("headers"))
            if reference and token:
                values[reference] = token
        return values
    if recovery.format == "urls":
        token = str(environment.get("MCP_API_KEY") or "")
        return {
            reference: token
            for reference in recovery.configured_reference_keys
            if token
        }
    return {}


def mcp_secret_values_for_draft_references(
    *,
    draft: Mapping[str, Any],
    recovery: McpRecovery,
    recovered_values: Mapping[str, str],
) -> dict[str, str]:
    """Bind recovered secrets to the references used by a published draft.

    Managed Sidecar Runtimes store effective credentials inside
    ``MCP_SERVERS_JSON`` under opaque recovery references.  Published drafts
    can retain an older generated environment name.  This function joins the
    two representations only through the server-validated MCP name and URL;
    browser-selected environment names are never trusted as secret selectors.
    """

    recovered_by_identity: dict[tuple[str, str], str] = {}
    ambiguous: set[tuple[str, str]] = set()
    for index, tool in enumerate(recovery.tools):
        url = _safe_mcp_url(tool.get("url"))
        identity = (_mcp_name(tool.get("name"), url, index), url)
        reference = str(tool.get("authTokenEnv") or "").strip()
        value = str(recovered_values.get(reference) or "")
        if not reference or not value:
            continue
        if identity in recovered_by_identity:
            ambiguous.add(identity)
        else:
            recovered_by_identity[identity] = _validated_secret(value)
    for identity in ambiguous:
        recovered_by_identity.pop(identity, None)

    resolved: dict[str, str] = {}
    for reference, (_agent_name, name, url) in _mcp_tool_bindings(draft).items():
        value = recovered_by_identity.get((name, url), "")
        if value:
            resolved[reference] = value
    return resolved


def retained_mcp_secret_values(
    *,
    published_draft: Mapping[str, Any],
    edited_draft: Mapping[str, Any],
    published_reference_values: Mapping[str, str],
) -> dict[str, str]:
    """Keep a stored credential only while its complete identity is unchanged."""

    published = _mcp_tool_bindings(published_draft)
    edited = _mcp_tool_bindings(edited_draft)
    return {
        reference: _validated_secret(published_reference_values[reference])
        for reference, identity in edited.items()
        if published.get(reference) == identity
        and published_reference_values.get(reference)
    }


def mcp_reuse_supplied_credentials(
    *,
    published_draft: Mapping[str, Any],
    edited_draft: Mapping[str, Any],
    published_reference_values: Mapping[str, str],
    reuse_requests: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, str], ...]:
    """Turn explicit, server-validated reuse decisions into supplied secrets.

    Reuse is accepted only for the same Agent and canonical MCP name.  The URL
    may change because that is the user-confirmed operation.  A credential from
    another tool can never be selected through a browser-provided reference.
    """

    published = _mcp_tool_bindings(published_draft)
    edited = _mcp_tool_bindings(edited_draft)
    supplied: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, request in enumerate(reuse_requests):
        if index >= 256 or not isinstance(request, Mapping):
            raise LegacyRecoveryError("legacy_mcp_reuse_input_invalid")
        source_reference = str(request.get("sourceAuthTokenEnv") or "").strip()
        source_identity = published.get(source_reference)
        edited_identity = edited.get(source_reference)
        secret = str(published_reference_values.get(source_reference) or "")
        if source_identity is None or edited_identity is None or not secret:
            raise LegacyRecoveryError("legacy_mcp_reuse_source_missing")
        raw_credential = {
            "agentName": str(request.get("agentName") or "").strip(),
            "name": str(request.get("name") or "").strip(),
            "url": str(request.get("url") or "").strip(),
            "value": "validated-reuse-marker",
        }
        canonical = _canonical_supplied_mcp_credentials(
            draft=edited_draft,
            supplied_credentials=(raw_credential,),
        )
        if len(canonical) != 1:
            raise LegacyRecoveryError("legacy_mcp_reuse_input_invalid")
        requested_identity = next(iter(canonical))
        if edited_identity != requested_identity or (
            source_identity[0],
            source_identity[1],
        ) != (requested_identity[0], requested_identity[1]):
            raise LegacyRecoveryError("legacy_mcp_reuse_identity_changed")
        if requested_identity in seen:
            raise LegacyRecoveryError("legacy_mcp_reuse_input_duplicate")
        seen.add(requested_identity)
        supplied.append(
            {
                "agentName": raw_credential["agentName"],
                "name": raw_credential["name"],
                "url": raw_credential["url"],
                "value": _validated_secret(secret),
            }
        )
    return tuple(supplied)


def _toolset_endpoint(toolset: Mapping[str, Any]) -> str:
    configurations = toolset.get("network_configurations")
    if not isinstance(configurations, list):
        configurations = []
    public = [
        item
        for item in configurations
        if isinstance(item, Mapping)
        and str(item.get("network_type") or "").casefold() == "public"
        and item.get("endpoint")
    ]
    candidates = public or [
        item
        for item in configurations
        if isinstance(item, Mapping) and item.get("endpoint")
    ]
    if len(candidates) != 1:
        raise LegacyRecoveryError("legacy_mcp_toolset_endpoint_ambiguous")
    endpoint = str(candidates[0].get("endpoint") or "").rstrip("/")
    path = str(toolset.get("path") or "").strip()
    if path and not path.startswith("/"):
        path = "/" + path
    return _safe_mcp_url(endpoint + path)


def _toolset_key_auth(toolset: Mapping[str, Any]) -> tuple[str, str]:
    configuration = toolset.get("authorizer_configuration")
    if not isinstance(configuration, Mapping):
        return "", ""
    authorizer_type = str(configuration.get("authorizer_type") or "").casefold()
    if authorizer_type in {"", "none"}:
        return "", ""
    authorizer = configuration.get("authorizer")
    key_auth = authorizer.get("key_auth") if isinstance(authorizer, Mapping) else None
    api_keys = key_auth.get("api_keys") if isinstance(key_auth, Mapping) else None
    keys = [
        str(item.get("key") or "")
        for item in api_keys or []
        if isinstance(item, Mapping) and str(item.get("key") or "")
    ]
    if "key" not in authorizer_type or len(keys) != 1:
        raise LegacyRecoveryError("legacy_mcp_toolset_auth_unsupported")
    endpoint = _toolset_endpoint(toolset)
    name = _mcp_name(toolset.get("name"), endpoint, 0)
    return _legacy_mcp_auth_reference(name, endpoint), keys[0]


def recover_mcp_from_toolset(toolset: Mapping[str, Any]) -> McpRecovery:
    """Recover one AgentKit managed Toolset without returning its API key."""

    endpoint = _toolset_endpoint(toolset)
    name = _mcp_name(toolset.get("name"), endpoint, 0)
    reference, _secret = _toolset_key_auth(toolset)
    return McpRecovery(
        tools=(
            {
                "name": name,
                "transport": "http",
                "url": endpoint,
                "authTokenEnv": reference,
            },
        ),
        configured_reference_keys=(reference,) if reference else (),
        format="agentkit-toolset",
    )


def mcp_secret_values_from_toolset(toolset: Mapping[str, Any]) -> dict[str, str]:
    """Return a managed Toolset API key under its opaque editor reference."""

    reference, secret = _toolset_key_auth(toolset)
    return {reference: secret} if reference and secret else {}


class _Response(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def headers(self) -> Mapping[str, str]: ...

    @property
    def content(self) -> bytes: ...

    def json(self) -> Any: ...

    def raise_for_status(self) -> object: ...


class OciImageInspector:
    """Resolve a Volcengine CR image and extract bounded Skill directories."""

    def __init__(
        self,
        credential_provider: Callable[[ImageReference], RegistryCredential],
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._credential_provider = credential_provider
        self._client = client or httpx.Client(timeout=60.0, follow_redirects=False)

    def _request(
        self,
        image: ImageReference,
        path: str,
        *,
        accept: str | None = None,
    ) -> _Response:
        credential = self._credential_provider(image)
        headers = {"Accept": accept} if accept else {}
        url = f"https://{image.registry_host}{path}"
        response = self._client.get(
            url,
            headers=headers,
            auth=(credential.username, credential.password),
        )
        if response.status_code == 401:
            challenge = str(response.headers.get("www-authenticate") or "")
            response = self._bearer_request(
                image,
                url,
                challenge,
                credential,
                headers,
            )
        if response.status_code in {401, 403}:
            raise LegacyRecoveryError("legacy_image_registry_pull_denied")
        if not 200 <= response.status_code < 300:
            raise LegacyRecoveryError("legacy_image_registry_unavailable")
        return response

    def _bearer_request(
        self,
        image: ImageReference,
        target_url: str,
        challenge: str,
        credential: RegistryCredential,
        headers: Mapping[str, str],
    ) -> _Response:
        if not challenge.startswith("Bearer "):
            raise LegacyRecoveryError("legacy_image_registry_auth_failed")
        attributes = dict(re.findall(r'([A-Za-z]+)="([^"\r\n]+)"', challenge[7:]))
        realm = attributes.get("realm", "")
        parsed_realm = urlsplit(realm)
        realm_hostname = (parsed_realm.hostname or "").lower()
        try:
            realm_port = parsed_realm.port
        except ValueError as error:
            raise LegacyRecoveryError("legacy_image_registry_auth_failed") from error
        if (
            parsed_realm.scheme != "https"
            or not parsed_realm.netloc
            or parsed_realm.username is not None
            or parsed_realm.password is not None
            or not (
                realm_hostname == "volces.com" or realm_hostname.endswith(".volces.com")
            )
            or realm_port not in {None, 443}
        ):
            raise LegacyRecoveryError("legacy_image_registry_auth_failed")
        query = parse_qs(parsed_realm.query, keep_blank_values=True)
        for key in ("service", "scope"):
            if attributes.get(key):
                query[key] = [attributes[key]]
        auth_url = parsed_realm._replace(
            query=urlencode(query, doseq=True), fragment=""
        ).geturl()
        token_response = self._client.get(
            auth_url,
            auth=(credential.username, credential.password),
        )
        if token_response.status_code in {401, 403}:
            raise LegacyRecoveryError("legacy_image_registry_auth_failed")
        if not 200 <= token_response.status_code < 300:
            raise LegacyRecoveryError("legacy_image_registry_unavailable")
        token_payload = token_response.json()
        token = str(
            (token_payload.get("token") or token_payload.get("access_token") or "")
            if isinstance(token_payload, Mapping)
            else ""
        )
        if not token:
            raise LegacyRecoveryError("legacy_image_registry_auth_failed")
        return self._client.get(
            target_url,
            headers={**headers, "Authorization": f"Bearer {token}"},
        )

    def _manifest(
        self, image: ImageReference, reference: str
    ) -> tuple[dict[str, Any], str]:
        response = self._request(
            image,
            f"/v2/{image.repository}/manifests/{reference}",
            accept=_MANIFEST_ACCEPT,
        )
        if len(response.content) > _MAX_MANIFEST_BYTES:
            raise LegacyRecoveryError("legacy_image_manifest_too_large")
        try:
            payload = response.json()
        except (TypeError, ValueError) as error:
            raise LegacyRecoveryError("legacy_image_manifest_invalid") from error
        if not isinstance(payload, dict):
            raise LegacyRecoveryError("legacy_image_manifest_invalid")
        digest = str(response.headers.get("docker-content-digest") or "")
        if _DIGEST_RE.fullmatch(digest) is None:
            raise LegacyRecoveryError("legacy_image_manifest_digest_missing")
        return payload, digest

    def resolve_manifest(self, image: ImageReference) -> tuple[dict[str, Any], str]:
        payload, digest = self._manifest(image, image.reference)
        media_type = str(payload.get("mediaType") or "")
        if media_type in _OCI_INDEX_TYPES or isinstance(payload.get("manifests"), list):
            candidates = [
                item
                for item in payload.get("manifests", [])
                if isinstance(item, Mapping)
                and str((item.get("platform") or {}).get("os") or "") == "linux"
                and str((item.get("platform") or {}).get("architecture") or "")
                == "amd64"
                and _DIGEST_RE.fullmatch(str(item.get("digest") or ""))
            ]
            if len(candidates) != 1:
                raise LegacyRecoveryError("legacy_image_platform_ambiguous")
            payload, digest = self._manifest(image, str(candidates[0]["digest"]))
            media_type = str(payload.get("mediaType") or "")
        if media_type and media_type not in _OCI_MANIFEST_TYPES:
            raise LegacyRecoveryError("legacy_image_manifest_unsupported")
        if not isinstance(payload.get("layers"), list):
            raise LegacyRecoveryError("legacy_image_manifest_invalid")
        return payload, digest

    def extract_skills(
        self,
        image: ImageReference,
        names: Iterable[tuple[str, str]],
    ) -> tuple[str, tuple[RecoveredSkill, ...]]:
        requested = {name: description for name, description in names}
        if not requested:
            _manifest, digest = self.resolve_manifest(image)
            return image.pinned(digest), ()
        if len(requested) > 64 or any(
            _SKILL_NAME_RE.fullmatch(name) is None for name in requested
        ):
            raise LegacyRecoveryError("legacy_skill_name_invalid")

        manifest, digest = self.resolve_manifest(image)
        roots: dict[str, dict[str, dict[str, bytes]]] = {name: {} for name in requested}
        for layer in manifest["layers"]:
            if not isinstance(layer, Mapping):
                raise LegacyRecoveryError("legacy_image_layer_invalid")
            layer_digest = str(layer.get("digest") or "")
            layer_type = str(layer.get("mediaType") or "")
            layer_size = int(layer.get("size") or 0)
            if (
                _DIGEST_RE.fullmatch(layer_digest) is None
                or layer_type not in _SUPPORTED_LAYER_TYPES
                or layer_size < 0
                or layer_size > _MAX_LAYER_BYTES
            ):
                raise LegacyRecoveryError("legacy_image_layer_unsupported")
            response = self._request(
                image,
                f"/v2/{image.repository}/blobs/{layer_digest}",
            )
            if len(response.content) > _MAX_LAYER_BYTES:
                raise LegacyRecoveryError("legacy_image_layer_too_large")
            actual_digest = "sha256:" + hashlib.sha256(response.content).hexdigest()
            if not secrets.compare_digest(actual_digest, layer_digest):
                raise LegacyRecoveryError("legacy_image_layer_digest_mismatch")
            self._apply_layer(roots, requested, response.content)

        recovered = []
        for name, description in requested.items():
            candidates = roots[name]
            complete = [
                (root, files)
                for root, files in candidates.items()
                if "SKILL.md" in files
            ]
            if len(complete) != 1:
                raise LegacyRecoveryError(
                    "legacy_skill_missing"
                    if not complete
                    else "legacy_skill_root_ambiguous"
                )
            image_root, files = complete[0]
            recovered.append(
                self._recovered_skill(name, description, image_root, files)
            )
        return image.pinned(digest), tuple(recovered)

    @staticmethod
    def _apply_layer(
        roots: dict[str, dict[str, dict[str, bytes]]],
        requested: Mapping[str, str],
        content: bytes,
    ) -> None:
        try:
            archive = tarfile.open(fileobj=io.BytesIO(content), mode="r:*")
        except (tarfile.TarError, OSError) as error:
            raise LegacyRecoveryError("legacy_image_layer_invalid") from error
        with archive:
            for index, member in enumerate(archive):
                if index >= _MAX_LAYER_MEMBERS:
                    raise LegacyRecoveryError("legacy_image_layer_member_limit")
                path = OciImageInspector._safe_tar_path(member.name)
                parts = path.parts
                for name in requested:
                    match_index = next(
                        (
                            item
                            for item in range(len(parts) - 1)
                            if parts[item] == "skills" and parts[item + 1] == name
                        ),
                        None,
                    )
                    if match_index is None:
                        continue
                    root = PurePosixPath(*parts[: match_index + 2]).as_posix()
                    relative = PurePosixPath(*parts[match_index + 2 :]).as_posix()
                    if not relative or relative == ".":
                        continue
                    files = roots[name].setdefault(root, {})
                    base = PurePosixPath(relative).name
                    parent = PurePosixPath(relative).parent
                    if base == ".wh..wh..opq":
                        prefix = "" if str(parent) == "." else parent.as_posix() + "/"
                        for existing in list(files):
                            if existing.startswith(prefix):
                                files.pop(existing, None)
                        continue
                    if base.startswith(".wh."):
                        target = parent / base[4:]
                        files.pop(target.as_posix(), None)
                        continue
                    if member.issym() or member.islnk():
                        raise LegacyRecoveryError("legacy_skill_symlink_forbidden")
                    if not member.isfile():
                        continue
                    if member.size > _MAX_SKILL_FILE_BYTES:
                        raise LegacyRecoveryError("legacy_skill_file_too_large")
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise LegacyRecoveryError("legacy_image_layer_invalid")
                    data = stream.read(_MAX_SKILL_FILE_BYTES + 1)
                    if len(data) != member.size or len(data) > _MAX_SKILL_FILE_BYTES:
                        raise LegacyRecoveryError("legacy_skill_file_too_large")
                    files[relative] = data

    @staticmethod
    def _safe_tar_path(value: str) -> PurePosixPath:
        normalized = str(value or "").removeprefix("./")
        path = PurePosixPath(normalized)
        if (
            not normalized
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise LegacyRecoveryError("legacy_image_layer_path_invalid")
        return path

    @staticmethod
    def _recovered_skill(
        name: str,
        description: str,
        image_root: str,
        raw_files: Mapping[str, bytes],
    ) -> RecoveredSkill:
        if len(raw_files) > _MAX_SKILL_FILES:
            raise LegacyRecoveryError("legacy_skill_file_count_limit")
        total = sum(len(value) for value in raw_files.values())
        if total > _MAX_SKILL_TOTAL_BYTES:
            raise LegacyRecoveryError("legacy_skill_total_too_large")
        files: list[dict[str, str]] = []
        digest = hashlib.sha256()
        for relative, raw in sorted(raw_files.items()):
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError as error:
                raise LegacyRecoveryError(
                    "legacy_skill_binary_file_forbidden"
                ) from error
            target = f"skills/{name}/{relative}"
            digest.update(target.encode("utf-8") + b"\0" + raw + b"\0")
            files.append({"path": target, "content": content})
        return RecoveredSkill(
            name=name,
            description=description,
            image_root=image_root,
            files=tuple(files),
            digest=digest.hexdigest(),
        )
