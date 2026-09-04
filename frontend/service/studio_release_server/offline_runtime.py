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

"""Build the locked Linux wheelhouse consumed by VeFaaS Studio releases."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import (
    InvalidWheelFilename,
    canonicalize_name,
    parse_wheel_filename,
)
from packaging.version import InvalidVersion, Version

STUDIO_RUNTIME_LOCK = "studio-runtime.lock"
STUDIO_RUNTIME_WHEELHOUSE = "wheelhouse"
_LINUX_PLATFORMS = (
    "manylinux_2_17_x86_64",
    "manylinux2014_x86_64",
    "manylinux_2_28_x86_64",
    "linux_x86_64",
)
_PYTHON_VERSION = "3.12"
_PYTHON_ABI = "cp312"
_PIP_VERSION = "25.2"
_CANONICAL_PYPI_INDEX = "https://pypi.org/simple"
_INDEX_ENVIRONMENT_KEYS = (
    "UV_DEFAULT_INDEX",
    "UV_INDEX",
    "UV_INDEX_URL",
    "UV_EXTRA_INDEX_URL",
    "PIP_INDEX_URL",
    "PIP_EXTRA_INDEX_URL",
)


def _lock_check_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Validate the committed lock against its canonical package index."""
    lock_environment = dict(environment)
    for key in _INDEX_ENVIRONMENT_KEYS:
        lock_environment.pop(key, None)
    lock_environment["UV_DEFAULT_INDEX"] = _CANONICAL_PYPI_INDEX
    return lock_environment


def build_studio_offline_runtime(
    source_root: Path,
    package_dir: Path,
    *,
    veadk_wheel: Path,
    dependency_sources: Sequence[Path],
    environment: Mapping[str, str] | None = None,
) -> str:
    """Bundle every locked Linux dependency and return offline requirements."""
    lock_source = source_root / "uv.lock"
    if not lock_source.is_file():
        raise ValueError("Studio offline runtime requires uv.lock.")
    uv = shutil.which("uv", path=(environment or os.environ).get("PATH"))
    if uv is None:
        raise ValueError("uv is required to build the Studio offline runtime.")
    build_environment = dict(environment or os.environ)
    _run(
        [uv, "lock", "--check"],
        cwd=source_root,
        environment=_lock_check_environment(build_environment),
        failure="Studio runtime lock is stale.",
    )

    package_dir.mkdir(parents=True, exist_ok=True)
    wheelhouse = package_dir / STUDIO_RUNTIME_WHEELHOUSE
    wheelhouse.mkdir()
    runtime_lock = package_dir / STUDIO_RUNTIME_LOCK

    with tempfile.TemporaryDirectory(prefix="veadk_studio_runtime_") as tmp:
        workspace = Path(tmp)
        exported_lock = workspace / STUDIO_RUNTIME_LOCK
        _run(
            [
                uv,
                "export",
                "--frozen",
                "--no-dev",
                "--no-emit-project",
                "--no-hashes",
                "--format",
                "requirements-txt",
                "--output-file",
                str(exported_lock),
            ],
            cwd=source_root,
            environment=build_environment,
            failure="Could not export the locked Studio runtime.",
        )
        if (
            not exported_lock.is_file()
            or not exported_lock.read_text(encoding="utf-8").strip()
        ):
            raise ValueError("Studio runtime lock export is empty.")
        _write_linux_runtime_lock(exported_lock, runtime_lock)

        pure_wheels = workspace / "pure-wheels"
        pure_wheels.mkdir()
        if dependency_sources:
            pure_environment = dict(build_environment)
            # crcmod intentionally falls back to its portable Python
            # implementation when the optional C compiler is unavailable.
            pure_environment["CC"] = "veadk-studio-no-native-compiler"
            _run(
                [
                    uv,
                    "tool",
                    "run",
                    "--from",
                    f"pip=={_PIP_VERSION}",
                    "pip",
                    "wheel",
                    "--disable-pip-version-check",
                    "--no-deps",
                    "--wheel-dir",
                    str(pure_wheels),
                    *(str(path) for path in dependency_sources),
                ],
                cwd=source_root,
                environment=pure_environment,
                failure="Could not build portable Studio dependency wheels.",
            )
            built_sources = sorted(pure_wheels.glob("*.whl"))
            if len(built_sources) != len(dependency_sources) or any(
                not path.name.endswith("-py3-none-any.whl") for path in built_sources
            ):
                raise ValueError(
                    "Studio source dependencies did not produce portable wheels."
                )

        command = [
            uv,
            "tool",
            "run",
            "--from",
            f"pip=={_PIP_VERSION}",
            "pip",
            "download",
            "--disable-pip-version-check",
            "--dest",
            str(wheelhouse),
            "--only-binary=:all:",
        ]
        for platform_name in _LINUX_PLATFORMS:
            command.extend(("--platform", platform_name))
        command.extend(
            (
                "--implementation",
                "cp",
                "--python-version",
                _PYTHON_VERSION,
                "--abi",
                _PYTHON_ABI,
                "--find-links",
                str(pure_wheels),
                "--requirement",
                str(runtime_lock),
            )
        )
        _run(
            command,
            cwd=source_root,
            environment=build_environment,
            failure="Could not download the locked Linux Studio wheelhouse.",
        )
    staged_veadk = wheelhouse / veadk_wheel.name
    shutil.move(str(veadk_wheel), staged_veadk)
    if not staged_veadk.is_file():
        raise ValueError("Studio offline wheelhouse is incomplete.")
    _pin_runtime_lock_to_wheelhouse(runtime_lock, wheelhouse, staged_veadk)
    requirements = (
        "--no-index\n"
        f"--find-links ./{STUDIO_RUNTIME_WHEELHOUSE}\n"
        "--require-hashes\n"
        f"-r ./{STUDIO_RUNTIME_LOCK}\n"
        f"./{STUDIO_RUNTIME_WHEELHOUSE}/{staged_veadk.name} "
        f"--hash=sha256:{_sha256(staged_veadk)}\n"
    )
    _verify_offline_resolution(
        package_dir,
        staged_veadk,
        uv=uv,
        environment=build_environment,
    )
    return requirements


def _write_linux_runtime_lock(exported_lock: Path, destination: Path) -> None:
    """Evaluate uv markers for the VeFaaS Linux/x86_64 Python 3.12 target."""
    environment: dict[str, str] = {
        key: str(value) for key, value in default_environment().items()
    }
    environment.update(
        {
            "implementation_name": "cpython",
            "os_name": "posix",
            "platform_machine": "x86_64",
            "platform_python_implementation": "CPython",
            "python_full_version": "3.12.0",
            "python_version": _PYTHON_VERSION,
            "sys_platform": "linux",
        }
    )
    selected: list[str] = []
    for raw_line in exported_lock.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            requirement = Requirement(line)
        except InvalidRequirement as error:
            raise ValueError(
                "Studio runtime lock contains an invalid requirement."
            ) from error
        if requirement.marker is not None and not requirement.marker.evaluate(
            environment
        ):
            continue
        selected.append(line.split(";", 1)[0].strip())
    if not selected:
        raise ValueError("Studio Linux runtime lock is empty.")
    destination.write_text("\n".join(selected) + "\n", encoding="utf-8")


def _pin_runtime_lock_to_wheelhouse(
    runtime_lock: Path,
    wheelhouse: Path,
    veadk_wheel: Path,
) -> None:
    """Replace the exported lock with hashes of the exact bundled wheels."""
    wheel_index: dict[tuple[str, Version], list[Path]] = {}
    dependency_wheels: set[Path] = set()
    for wheel in sorted(wheelhouse.glob("*.whl")):
        if wheel == veadk_wheel:
            continue
        try:
            name, version, _build, _tags = parse_wheel_filename(wheel.name)
        except InvalidWheelFilename as error:
            raise ValueError("Studio wheelhouse contains an invalid wheel.") from error
        wheel_index.setdefault((canonicalize_name(name), version), []).append(wheel)
        dependency_wheels.add(wheel)

    selected_wheels: set[Path] = set()
    locked_lines: list[str] = []
    for raw_line in runtime_lock.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            requirement = Requirement(line)
        except InvalidRequirement as error:
            raise ValueError(
                "Studio runtime lock contains an invalid requirement."
            ) from error
        specifiers = list(requirement.specifier)
        if (
            requirement.url is not None
            or len(specifiers) != 1
            or specifiers[0].operator != "=="
            or "*" in specifiers[0].version
        ):
            raise ValueError("Studio runtime dependency is not exactly pinned.")
        try:
            version = Version(specifiers[0].version)
        except InvalidVersion as error:
            raise ValueError("Studio runtime dependency version is invalid.") from error
        candidates = wheel_index.get(
            (canonicalize_name(requirement.name), version),
            [],
        )
        if not candidates:
            raise ValueError("Studio offline wheelhouse is incomplete.")
        selected_wheels.update(candidates)
        hashes = " ".join(
            f"--hash=sha256:{_sha256(candidate)}" for candidate in candidates
        )
        locked_lines.append(f"{line} {hashes}")

    if not locked_lines or selected_wheels != dependency_wheels:
        raise ValueError("Studio offline wheelhouse does not match its runtime lock.")
    runtime_lock.write_text("\n".join(locked_lines) + "\n", encoding="utf-8")


def _verify_offline_resolution(
    package_dir: Path,
    veadk_wheel: Path,
    *,
    uv: str,
    environment: Mapping[str, str],
) -> None:
    """Resolve the final bundle once with networking disabled before release."""
    with tempfile.TemporaryDirectory(prefix="veadk_studio_verify_") as tmp:
        workspace = Path(tmp)
        verification_requirements = workspace / "requirements.txt"
        verification_requirements.write_text(
            f"--find-links {(package_dir / STUDIO_RUNTIME_WHEELHOUSE).resolve().as_uri()}\n"
            "--require-hashes\n"
            f"-r {(package_dir / STUDIO_RUNTIME_LOCK).resolve()}\n"
            f"{veadk_wheel.resolve().as_uri()} "
            f"--hash=sha256:{_sha256(veadk_wheel)}\n",
            encoding="utf-8",
        )
        resolved = workspace / "resolved"
        resolved.mkdir()
        command = [
            uv,
            "tool",
            "run",
            "--from",
            f"pip=={_PIP_VERSION}",
            "pip",
            "download",
            "--disable-pip-version-check",
            "--no-index",
            "--only-binary=:all:",
        ]
        for platform_name in _LINUX_PLATFORMS:
            command.extend(("--platform", platform_name))
        command.extend(
            (
                "--implementation",
                "cp",
                "--python-version",
                _PYTHON_VERSION,
                "--abi",
                _PYTHON_ABI,
                "--dest",
                str(resolved),
                "--requirement",
                str(verification_requirements),
            )
        )
        _run(
            command,
            cwd=package_dir,
            environment=environment,
            failure="Studio offline wheelhouse failed isolated resolution.",
        )


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(
    command: list[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    failure: str,
) -> None:
    try:
        subprocess.run(
            command,
            cwd=cwd,
            env=dict(environment),
            check=True,
            stdout=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as error:
        raise ValueError(f"{failure} Exit code: {error.returncode}.") from error


__all__ = [
    "STUDIO_RUNTIME_LOCK",
    "STUDIO_RUNTIME_WHEELHOUSE",
    "build_studio_offline_runtime",
]
