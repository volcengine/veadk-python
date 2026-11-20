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

"""Build the locked Linux wheel set consumed by VeFaaS Studio releases."""

from __future__ import annotations

import base64
import compileall
import csv
import io
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
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
_COLD_START_WHEEL_ROOTS = {
    "veadk-python": ("veadk", "frontend"),
    "google-adk": ("google/adk",),
    "agentkit-sdk-python": ("agentkit",),
    "google-genai": ("google/genai",),
    "mcp": ("mcp",),
    "dateparser": ("dateparser",),
    "fastapi": ("fastapi",),
    "sqlalchemy": ("sqlalchemy",),
    "aiohttp": ("aiohttp",),
    "tos": ("tos",),
    "trafilatura": ("trafilatura",),
    "htmldate": ("htmldate",),
    "authlib": ("authlib",),
    "volcengine-python-sdk": (
        "volcenginesdkid",
        "volcenginesdkvpc",
        "volcenginesdkarkruntime",
        "volcenginesdkvefaas",
        "volcenginesdkark",
        "volcenginesdkcore",
    ),
}
_COLD_START_SOURCE_EXCLUSIONS = re.compile(
    r"(?:template[/\\]\{\{|resources[/\\]samples)"
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
    optimize_cold_start: bool = False,
    thin_package_dir: Path | None = None,
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
    if optimize_cold_start:
        if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12):
            raise ValueError("Studio cold-start optimization requires CPython 3.12.")
    if thin_package_dir is not None:
        # Public artifacts must retain the exact PyPI bytes recorded in uv.lock.
        # Snapshot before full-bundle optimization, with an independent hash lock.
        shutil.copytree(wheelhouse, thin_package_dir)
        thin_veadk = thin_package_dir / staged_veadk.name
        if optimize_cold_start:
            _augment_checked_hash_wheel(
                thin_veadk, _COLD_START_WHEEL_ROOTS["veadk-python"]
            )
        thin_lock = thin_package_dir / STUDIO_RUNTIME_LOCK
        shutil.copy2(runtime_lock, thin_lock)
        _pin_runtime_lock_to_wheelhouse(thin_lock, thin_package_dir, thin_veadk)
        thin_requirements = build_studio_offline_requirements(
            thin_package_dir, wheel_prefix="./"
        )
        _verify_offline_resolution(
            thin_package_dir,
            thin_requirements,
            uv=uv,
            environment=build_environment,
        )
    if optimize_cold_start:
        _enhance_studio_cold_start_wheels(wheelhouse)
    _pin_runtime_lock_to_wheelhouse(runtime_lock, wheelhouse, staged_veadk)
    for wheel in sorted(wheelhouse.glob("*.whl")):
        destination = package_dir / wheel.name
        if destination.exists():
            raise ValueError("Studio offline wheel has a root-level conflict.")
        shutil.move(str(wheel), destination)
    try:
        wheelhouse.rmdir()
    except OSError as error:
        raise ValueError(
            "Studio offline wheelhouse contains unexpected files."
        ) from error
    requirements = build_studio_offline_requirements(
        package_dir,
        wheel_prefix="./",
    )
    _verify_offline_resolution(
        package_dir,
        requirements,
        uv=uv,
        environment=build_environment,
    )
    return requirements


def _enhance_studio_cold_start_wheels(wheelhouse: Path) -> dict[str, int]:
    """Add deterministic checked-hash CPython 3.12 bytecode to hot wheels."""
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12):
        raise ValueError("Studio cold-start optimization requires CPython 3.12.")
    selected: dict[str, tuple[Path, tuple[str, ...]]] = {}
    for wheel in sorted(wheelhouse.glob("*.whl")):
        try:
            name, _version, _build, _tags = parse_wheel_filename(wheel.name)
        except InvalidWheelFilename as error:
            raise ValueError("Studio wheelhouse contains an invalid wheel.") from error
        distribution = canonicalize_name(name)
        roots = _COLD_START_WHEEL_ROOTS.get(distribution)
        if roots is None:
            continue
        if distribution in selected:
            raise ValueError(
                "Studio cold-start wheelhouse contains duplicate distributions."
            )
        selected[distribution] = (wheel, roots)
    if set(selected) != set(_COLD_START_WHEEL_ROOTS):
        raise ValueError("Studio cold-start wheelhouse is incomplete.")

    enhanced: dict[str, int] = {}
    for distribution in _COLD_START_WHEEL_ROOTS:
        wheel, roots = selected[distribution]
        enhanced[wheel.name] = _augment_checked_hash_wheel(wheel, roots)
    return enhanced


def _augment_checked_hash_wheel(wheel: Path, roots: tuple[str, ...]) -> int:
    """Repack one wheel with checked-hash pyc files and a valid RECORD."""
    with tempfile.TemporaryDirectory(prefix="veadk_studio_pyc_") as tmp:
        extracted = Path(tmp) / "wheel"
        extracted.mkdir()
        try:
            with zipfile.ZipFile(wheel) as source:
                original = [(info, source.read(info)) for info in source.infolist()]
                source.extractall(extracted)
        except (OSError, zipfile.BadZipFile) as error:
            raise ValueError("Studio cold-start wheel is invalid.") from error

        pycs: list[Path] = []
        for relative in roots:
            source_root = extracted / relative
            if not source_root.is_dir():
                raise ValueError("Studio cold-start wheel is missing a hot path.")
            if not compileall.compile_dir(
                source_root,
                quiet=1,
                force=True,
                rx=_COLD_START_SOURCE_EXCLUSIONS,
                stripdir=str(extracted),
                prependdir="/opt/application/site-packages",
                invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH,
            ):
                raise ValueError("Studio cold-start bytecode compilation failed.")
            pycs.extend(source_root.rglob("*.pyc"))
        pycs = sorted(set(pycs))
        if not pycs:
            raise ValueError("Studio cold-start wheel produced no bytecode.")
        for pyc in pycs:
            header = pyc.read_bytes()[:8]
            if len(header) != 8 or int.from_bytes(header[4:8], "little") != 3:
                raise ValueError("Studio cold-start bytecode is not checked-hash.")

        record_entries = [
            (info, content)
            for info, content in original
            if info.filename.endswith(".dist-info/RECORD")
        ]
        if len(record_entries) != 1:
            raise ValueError("Studio cold-start wheel RECORD is invalid.")
        record_info, record_content = record_entries[0]
        rows = [
            row
            for row in csv.reader(io.StringIO(record_content.decode("utf-8")))
            if row
        ]
        pyc_names = {path.relative_to(extracted).as_posix() for path in pycs}
        rows = [
            row
            for row in rows
            if row[0] != record_info.filename and row[0] not in pyc_names
        ]
        for pyc in pycs:
            content = pyc.read_bytes()
            digest = base64.urlsafe_b64encode(sha256(content).digest())
            rows.append(
                [
                    pyc.relative_to(extracted).as_posix(),
                    "sha256=" + digest.rstrip(b"=").decode("ascii"),
                    str(len(content)),
                ]
            )
        rows.append([record_info.filename, "", ""])
        record_output = io.StringIO(newline="")
        csv.writer(record_output, lineterminator="\n").writerows(rows)

        rebuilt = Path(tmp) / wheel.name
        with zipfile.ZipFile(
            rebuilt,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as destination:
            for info, content in original:
                if info.filename in pyc_names:
                    continue
                destination.writestr(
                    info,
                    (
                        record_output.getvalue().encode("utf-8")
                        if info.filename == record_info.filename
                        else content
                    ),
                )
            for pyc in pycs:
                info = zipfile.ZipInfo(
                    pyc.relative_to(extracted).as_posix(),
                    date_time=(1980, 1, 1, 0, 0, 0),
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                destination.writestr(info, pyc.read_bytes())
        os.replace(rebuilt, wheel)
        return len(pycs)


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


def build_studio_offline_requirements(
    wheelhouse: Path,
    *,
    wheel_prefix: str,
) -> str:
    """Return a hash-pinned contract without relative index URLs."""
    if (
        not wheel_prefix.startswith("./")
        or ".." in Path(wheel_prefix).parts
        or "\n" in wheel_prefix
        or "\r" in wheel_prefix
    ):
        raise ValueError("Studio wheel prefix is invalid.")
    wheels = sorted(wheelhouse.glob("*.whl"))
    if not wheels:
        raise ValueError("Studio offline wheelhouse is empty.")

    distributions: set[str] = set()
    lines = ["--no-index", "--require-hashes"]
    for wheel in wheels:
        try:
            name, _version, _build, _tags = parse_wheel_filename(wheel.name)
        except InvalidWheelFilename as error:
            raise ValueError("Studio wheelhouse contains an invalid wheel.") from error
        distribution = canonicalize_name(name)
        if distribution in distributions:
            raise ValueError("Studio wheelhouse contains duplicate distributions.")
        distributions.add(distribution)
        lines.append(f"{wheel_prefix}{wheel.name} --hash=sha256:{_sha256(wheel)}")
    return "\n".join(lines) + "\n"


def _verify_offline_resolution(
    package_dir: Path,
    requirements: str,
    *,
    uv: str,
    environment: Mapping[str, str],
) -> None:
    """Resolve the exact stdin contract used by the dependency installer."""
    with tempfile.TemporaryDirectory(prefix="veadk_studio_verify_") as tmp:
        resolved = Path(tmp) / "resolved"
        resolved.mkdir()
        command = [
            uv,
            "pip",
            "install",
            "--dry-run",
            "--offline",
            "--no-index",
            "--require-hashes",
            "--no-python-downloads",
            "--python-version",
            _PYTHON_VERSION,
            "--python-platform",
            "x86_64-manylinux_2_28",
            "--target",
            str(resolved),
            "--requirements",
            "-",
        ]
        _run(
            command,
            cwd=package_dir,
            environment=environment,
            failure="Studio offline wheelhouse failed isolated resolution.",
            stdin=requirements,
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
    stdin: str | None = None,
) -> None:
    try:
        subprocess.run(
            command,
            cwd=cwd,
            env=dict(environment),
            check=True,
            input=stdin,
            stdout=subprocess.DEVNULL,
            text=stdin is not None,
        )
    except subprocess.CalledProcessError as error:
        raise ValueError(f"{failure} Exit code: {error.returncode}.") from error


__all__ = [
    "STUDIO_RUNTIME_LOCK",
    "STUDIO_RUNTIME_WHEELHOUSE",
    "build_studio_offline_requirements",
    "build_studio_offline_runtime",
]
