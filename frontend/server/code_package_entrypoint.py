# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""Resolve and prepare Python entry points for Studio code-package deployments."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_ENTRY_POINTS = ("app.py", "agentkit_app.py", "main.py")
MIGRATION_MANIFEST = "migration-result.json"
_BOOTSTRAP_STEM = "_veadk_studio_entrypoint"


def _validate_entry_point(
    base: Path,
    value: object,
    *,
    field_name: str = "entryPoint",
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    entry_point = value.strip()
    parts = entry_point.split("/")
    if (
        not entry_point
        or entry_point.startswith("/")
        or "\\" in entry_point
        or any(
            ord(character) < 32 or ord(character) == 127 for character in entry_point
        )
        or any(part in {"", ".", ".."} for part in parts)
        or not entry_point.endswith(".py")
        or parts[-1] == "__init__.py"
    ):
        raise ValueError(f"{field_name} must be a safe relative Python file path")

    root = base.resolve()
    target = (root / entry_point).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError(f"{field_name} does not exist in files: {entry_point}")
    return entry_point


def _manifest_entry_point(base: Path) -> object | None:
    manifest_path = base / MIGRATION_MANIFEST
    if not manifest_path.is_file():
        return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{MIGRATION_MANIFEST} must contain valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict) or "entrypoint" not in manifest:
        raise ValueError(f"{MIGRATION_MANIFEST} must declare entrypoint")
    return manifest["entrypoint"]


def resolve_code_package_entry_point(
    base: Path,
    requested: object | None,
) -> str:
    """Resolve a validated entry point, preserving legacy filename precedence."""
    root = base.resolve()
    manifest_entry_point = _manifest_entry_point(root)
    validated_manifest_entry_point: str | None = None
    if manifest_entry_point is not None:
        validated_manifest_entry_point = _validate_entry_point(
            root,
            manifest_entry_point,
            field_name=f"{MIGRATION_MANIFEST} entrypoint",
        )

    # An explicit UI selection overrides a valid manifest. Invalid manifests still
    # fail closed so browser and direct API clients observe the same package contract.
    if requested is not None:
        return _validate_entry_point(root, requested)
    if validated_manifest_entry_point is not None:
        return validated_manifest_entry_point
    for candidate in DEFAULT_ENTRY_POINTS:
        if (root / candidate).is_file():
            return candidate

    candidates = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if path.is_file()
        and path.name != "__init__.py"
        and path.resolve().is_relative_to(root)
    )
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError(
            "No supported Python entry point found; provide entryPoint or "
            "include app.py, agentkit_app.py, or main.py"
        )
    raise ValueError(
        "Multiple Python entry points found; provide entryPoint explicitly"
    )


def prepare_code_package_launch_entry_point(
    base: Path,
    entry_point: str,
) -> str:
    """Return an AgentKit-compatible entry file, generating a bootstrap if needed."""
    stem = entry_point.removesuffix(".py")
    module_parts = stem.split("/")
    if len(module_parts) == 1 and module_parts[0].isidentifier():
        return entry_point

    wrapper_path = base / f"{_BOOTSTRAP_STEM}.py"
    suffix = 1
    while wrapper_path.exists():
        wrapper_path = base / f"{_BOOTSTRAP_STEM}_{suffix}.py"
        suffix += 1

    if all(part.isidentifier() for part in module_parts):
        module_name = ".".join(module_parts)
        launch_source = (
            f"runpy.run_module({module_name!r}, run_name='__main__', alter_sys=True)\n"
        )
        imports = "import runpy\n"
    else:
        launch_source = (
            f"entry_point = Path(__file__).resolve().parent / {entry_point!r}\n"
            "sys.path.insert(0, str(entry_point.parent))\n"
            "runpy.run_path(str(entry_point), run_name='__main__')\n"
        )
        imports = "import runpy\nimport sys\nfrom pathlib import Path\n"

    wrapper_path.write_text(
        '"""Studio-generated bootstrap for an AgentKit entry point."""\n\n'
        f"{imports}\n"
        f"{launch_source}",
        encoding="utf-8",
    )
    return wrapper_path.name
