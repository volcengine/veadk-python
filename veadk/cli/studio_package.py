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

"""Build the source bundle used by a VeFaaS-hosted Studio."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from veadk.cli.studio_dependencies import stage_studio_dependency_wheels
from veadk.cli.studio_telemetry import (
    normalize_studio_apmplus_release_environment,
    studio_apmplus_release_environment_from_env,
)
from veadk.cli.frontend_branding import SiteLogo
from veadk.utils.cloud_provider import DEFAULT_CLOUD_PROVIDER, CloudProvider

STUDIO_RELEASE_ENVIRONMENT_FILENAME = ".studio-release-environment.json"


def stage_studio_provider_requirements(
    package_dir: Path,
    provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
) -> str:
    """Stage provider-specific wheels and return their requirements lines."""
    if provider != "byteplus":
        return ""
    dependencies = stage_studio_dependency_wheels(package_dir, provider=provider)
    return "".join(f"./{path.name}\n" for path in dependencies)


def studio_run_script(
    site_logo_filename: str | None = None,
    *,
    provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
) -> str:
    """Return the authenticated VeFaaS entrypoint used by Studio."""
    command = (
        "exec python3 -m veadk.cli.cli studio "
        f"--provider {provider} --auth-mode frontend"
    )
    if site_logo_filename:
        command += f' --site-logo "$ROOT_DIR/{site_logo_filename}"'
    command += ' --host "$HOST" --port "$PORT"\n'
    return (
        "#!/bin/bash\n"
        "set -ex\n"
        'ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        'cd "$ROOT_DIR"\n'
        'if [ -d "output" ]; then cd ./output/; fi\n'
        "HOST=0.0.0.0\n"
        "PORT=${_FAAS_RUNTIME_PORT:-8000}\n"
        "export PYTHONPATH=$PYTHONPATH:./site-packages\n"
        f"{command}"
    )


def build_frontend_assets(source_root: Path, output_dir: Path) -> None:
    """Build the checkout's React frontend into an isolated directory."""
    _validate_source_checkout(source_root)
    npm = shutil.which("npm")
    if npm is None:
        raise ValueError("npm is required to build the Studio frontend.")
    frontend_root = source_root / "frontend"
    try:
        subprocess.run([npm, "ci"], cwd=frontend_root, check=True)
        subprocess.run(
            [npm, "run", "build", "--", "--outDir", str(output_dir)],
            cwd=frontend_root,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise ValueError(
            f"Studio frontend build failed with exit code {error.returncode}."
        ) from error
    if not (output_dir / "index.html").is_file():
        raise ValueError("Studio frontend build produced no index.html.")


def write_studio_package(
    package_dir: Path,
    *,
    requirements: str,
    site_logo: SiteLogo | None,
    release_environment: dict[str, str] | None = None,
    provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
) -> None:
    """Write the Studio entrypoint, requirements, and optional logo."""
    package_dir.mkdir(parents=True, exist_ok=True)
    logo_filename = (
        f"site-logo.{site_logo.extension}" if site_logo is not None else None
    )
    (package_dir / "run.sh").write_text(
        studio_run_script(logo_filename, provider=provider), encoding="utf-8"
    )
    if site_logo is not None and logo_filename is not None:
        (package_dir / logo_filename).write_bytes(site_logo.content)
    (package_dir / "requirements.txt").write_text(requirements, encoding="utf-8")
    environment = normalize_studio_apmplus_release_environment(
        release_environment or {}
    )
    if environment:
        (package_dir / STUDIO_RELEASE_ENVIRONMENT_FILENAME).write_text(
            json.dumps(environment, ensure_ascii=True, sort_keys=True),
            encoding="utf-8",
        )


def studio_release_environment_from_env() -> dict[str, str]:
    """Return release-time Studio environment defaults from the publisher env."""
    return studio_apmplus_release_environment_from_env()


def read_studio_release_environment(
    package_dir: Path,
    *,
    remove: bool = False,
) -> dict[str, str]:
    """Read release-time Studio environment defaults from an extracted bundle."""
    path = package_dir / STUDIO_RELEASE_ENVIRONMENT_FILENAME
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Studio release environment is not valid JSON.") from error
    environment = normalize_studio_apmplus_release_environment(payload)
    if remove:
        path.unlink(missing_ok=True)
    return environment


def build_local_studio_requirements(
    source_root: Path,
    package_dir: Path,
    *,
    frontend_assets: Path | None = None,
    dependency_wheels: Path | None = None,
    provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
) -> str:
    """Build a local VeADK wheel and return its offline requirements."""
    _validate_source_checkout(source_root)
    package_dir.mkdir(parents=True, exist_ok=True)
    wheel_source = source_root
    if frontend_assets is not None:
        wheel_source = package_dir / "wheel-source"
        _stage_wheel_source(source_root, frontend_assets, wheel_source)

    uv = shutil.which("uv")
    if uv:
        command = [uv, "build", "--wheel", str(wheel_source), "-o", str(package_dir)]
    else:
        command = [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "-o",
            str(package_dir),
            str(wheel_source),
        ]
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as error:
        raise ValueError(
            f"Local VeADK wheel build failed with exit code {error.returncode}."
        ) from error
    wheels = list(package_dir.glob("veadk*.whl"))
    if not wheels:
        raise ValueError("Local source build produced no veadk wheel.")

    dependencies = stage_studio_dependency_wheels(
        package_dir,
        source_dir=dependency_wheels,
        provider=provider,
    )

    shutil.rmtree(package_dir / "wheel-source", ignore_errors=True)
    requirement_lines = [f"./{path.name}" for path in dependencies]
    requirement_lines.append(f"./{wheels[0].name}[database]")
    requirements = "".join(f"{line}\n" for line in requirement_lines)
    return requirements


def _validate_source_checkout(source_root: Path) -> None:
    """Require the files needed to build Studio from a source checkout."""
    required_paths = (
        source_root / "pyproject.toml",
        source_root / "README.md",
        source_root / "LICENSE",
        source_root / "frontend" / "package.json",
        source_root / "frontend" / "package-lock.json",
        source_root / "veadk",
    )
    if not all(path.exists() for path in required_paths):
        raise ValueError(
            f"Not a VeADK source checkout: {source_root}. Expected pyproject.toml, "
            "README.md, LICENSE, frontend/package.json, frontend/package-lock.json, "
            "and veadk/."
        )


def _stage_wheel_source(
    source_root: Path, frontend_assets: Path, wheel_source: Path
) -> None:
    """Copy package sources and substitute freshly built frontend assets."""
    wheel_source.mkdir(parents=True)
    for filename in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(source_root / filename, wheel_source / filename)
    git_metadata = source_root / ".git"
    if git_metadata.is_file():
        shutil.copy2(git_metadata, wheel_source / ".git")
    elif git_metadata.is_dir():
        (wheel_source / ".git").write_text(
            f"gitdir: {git_metadata.resolve()}\n", encoding="utf-8"
        )
    shutil.copytree(
        source_root / "veadk",
        wheel_source / "veadk",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "webui"),
    )
    frontend_package = wheel_source / "frontend"
    frontend_package.mkdir()
    shutil.copy2(source_root / "frontend" / "__init__.py", frontend_package)
    shutil.copytree(
        source_root / "frontend" / "server",
        frontend_package / "server",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(frontend_assets, wheel_source / "veadk" / "webui")
