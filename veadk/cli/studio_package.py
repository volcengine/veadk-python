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

import hashlib
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from veadk.cli.frontend_branding import SiteLogo

_BUNDLED_WHEELS = (
    (
        "trustedmcp-0.0.5-py3-none-any.whl",
        "https://files.pythonhosted.org/packages/e0/5b/"
        "9d60a8633f4ab94c9ec0621b51a74d866086b4cb6579882fa4fb9186023b/"
        "trustedmcp-0.0.5-py3-none-any.whl",
        "3e89f6c9f5fb17cb70aaaa37df21a6e01722ccb1eec6cb8fc2e61417016986d4",
    ),
    (
        "volcengine_python_sdk-5.0.36-py2.py3-none-any.whl",
        "https://files.pythonhosted.org/packages/00/a1/"
        "9e246023bb847329bda43e516c64aa10d77b2d98c662f0e1179689020c23/"
        "volcengine_python_sdk-5.0.36-py2.py3-none-any.whl",
        "3a74fa7a7baa5d5f604b175f967660cd0aa4c7057ce44d98c4041fbaf7944b5b",
    ),
    (
        "tokenizers-0.22.2-cp39-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
        "https://files.pythonhosted.org/packages/2e/76/"
        "932be4b50ef6ccedf9d3c6639b056a967a86258c6d9200643f01269211ca/"
        "tokenizers-0.22.2-cp39-abi3-manylinux_2_17_x86_64."
        "manylinux2014_x86_64.whl",
        "369cc9fc8cc10cb24143873a0d95438bb8ee257bb80c71989e3ee290e8d72c67",
    ),
    (
        "openviking_sdk-0.1.4-py3-none-any.whl",
        "https://files.pythonhosted.org/packages/fe/af/"
        "4ca139b05f39c8ed04339d7c8aa56550df80f97d39768d2df9bd72fdbbb9/"
        "openviking_sdk-0.1.4-py3-none-any.whl",
        "1e9f23332b1b687dd7f272e660953992de60ad3e9d07d62f7460fd4aedb99616",
    ),
)


def studio_run_script(site_logo_filename: str | None = None) -> str:
    """Return the authenticated VeFaaS entrypoint used by Studio."""
    command = "exec python3 -m veadk.cli.cli studio --auth-mode frontend"
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
) -> None:
    """Write the Studio entrypoint, requirements, and optional logo."""
    package_dir.mkdir(parents=True, exist_ok=True)
    logo_filename = (
        f"site-logo.{site_logo.extension}" if site_logo is not None else None
    )
    (package_dir / "run.sh").write_text(
        studio_run_script(logo_filename), encoding="utf-8"
    )
    if site_logo is not None and logo_filename is not None:
        (package_dir / logo_filename).write_bytes(site_logo.content)
    (package_dir / "requirements.txt").write_text(requirements, encoding="utf-8")


def build_local_studio_requirements(
    source_root: Path,
    package_dir: Path,
    *,
    frontend_assets: Path | None = None,
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

    dependency_names = []
    for dependency_name, dependency_url, dependency_sha256 in _BUNDLED_WHEELS:
        with urllib.request.urlopen(dependency_url, timeout=60) as response:
            dependency_wheel = response.read()
        if hashlib.sha256(dependency_wheel).hexdigest() != dependency_sha256:
            raise ValueError(f"{dependency_name} checksum verification failed.")
        (package_dir / dependency_name).write_bytes(dependency_wheel)
        dependency_names.append(dependency_name)

    shutil.rmtree(package_dir / "wheel-source", ignore_errors=True)
    return "".join(f"./{name}\n" for name in (*dependency_names, wheels[0].name))


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
    shutil.copytree(frontend_assets, wheel_source / "veadk" / "webui")
