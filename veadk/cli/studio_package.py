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
import os
import shutil
import subprocess
import sys
from pathlib import Path

from frontend.service.studio_release_server.publisher import (
    stage_studio_wheel_source,
    validate_studio_wheel,
)
from veadk.cli.frontend_branding import SiteLogo
from veadk.cli.studio_dependencies import stage_studio_dependency_wheels
from veadk.utils.cloud_provider import DEFAULT_CLOUD_PROVIDER, CloudProvider


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
    provider: CloudProvider | None = DEFAULT_CLOUD_PROVIDER,
) -> str:
    """Return the authenticated VeFaaS entrypoint used by Studio."""
    provider_argument = (
        provider
        if provider is not None
        else '"${CLOUD_PROVIDER:-${AGENTKIT_CLOUD_PROVIDER:-volcengine}}"'
    )
    command = (
        "exec python3 -m veadk.cli.cli studio "
        f"--provider {provider_argument} --auth-mode frontend"
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


def build_frontend_assets(
    source_root: Path,
    output_dir: Path,
    *,
    changelog: tuple[str, ...] = (),
) -> None:
    """Build the checkout's React frontend into an isolated directory."""
    _validate_source_checkout(source_root)
    npm = shutil.which("npm")
    if npm is None:
        raise ValueError("npm is required to build the Studio frontend.")
    build_environment = os.environ.copy()
    build_environment["VITE_STUDIO_RELEASE_CHANGELOG"] = json.dumps(
        list(changelog), ensure_ascii=False
    )
    frontend_root = source_root / "frontend"
    try:
        subprocess.run(
            [npm, "ci"], cwd=frontend_root, env=build_environment, check=True
        )
        subprocess.run(
            [npm, "run", "build", "--", "--outDir", str(output_dir)],
            cwd=frontend_root,
            env=build_environment,
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
    provider: CloudProvider | None = DEFAULT_CLOUD_PROVIDER,
) -> None:
    """Write the Studio entrypoint, requirements, and optional logo."""
    package_dir.mkdir(parents=True, exist_ok=True)
    logo_filename = (
        f"site-logo.{site_logo.extension}" if site_logo is not None else None
    )
    (package_dir / "run.sh").write_text(
        studio_run_script(logo_filename, provider=provider),
        encoding="utf-8",
        newline="\n",
    )
    if site_logo is not None and logo_filename is not None:
        (package_dir / logo_filename).write_bytes(site_logo.content)
    (package_dir / "requirements.txt").write_text(requirements, encoding="utf-8")


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
    validate_studio_wheel(wheels[0], wheel_source)

    dependencies = stage_studio_dependency_wheels(
        package_dir,
        source_dir=dependency_wheels,
        provider=provider,
    )

    shutil.rmtree(package_dir / "wheel-source", ignore_errors=True)
    requirements = "".join(
        f"./{name}\n"
        for name in (*(path.name for path in dependencies), wheels[0].name)
    )
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
    stage_studio_wheel_source(source_root, frontend_assets, wheel_source)
