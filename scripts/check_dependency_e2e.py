#!/usr/bin/env python3
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

"""Release-time dependency E2E checks for the built VeADK wheel."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Iterable, Mapping, Sequence

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover - standalone script fallback
        from pip._vendor import tomli as tomllib  # type: ignore[no-redef]

try:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.utils import (
        canonicalize_name,
        parse_sdist_filename,
        parse_wheel_filename,
    )
    from packaging.version import InvalidVersion, Version
except ModuleNotFoundError:  # pragma: no cover - standalone script fallback
    from pip._vendor.packaging.markers import default_environment
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.specifiers import SpecifierSet
    from pip._vendor.packaging.utils import (
        canonicalize_name,
        parse_sdist_filename,
        parse_wheel_filename,
    )
    from pip._vendor.packaging.version import InvalidVersion, Version


RUNTIME_IMPORT_SMOKE = (
    "import veadk\n"
    "import google.adk\n"
    "import opentelemetry\n"
    "print('dependency smoke ok')\n"
)
UPPER_BOUND_OPERATORS = {"<", "<=", "==", "===", "~="}
HIGH_RISK_UPPER_BOUND_DEPENDENCIES = {"google-adk"}
SHARED_BASE_DEPENDENCY_PREFIXES = ("opentelemetry-",)
DECLARED_RANGE_CHECK_DEPENDENCIES = {
    "agentkit-sdk-python",
    "fastmcp",
    "google-adk",
    "jsonschema",
    "litellm",
    "mcp",
    "opentelemetry-exporter-otlp",
    "opentelemetry-instrumentation-logging",
    "tos",
}


def load_runtime_dependencies(pyproject: Path) -> list[str]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return list(data["project"]["dependencies"])


def validate_dependency_policy(dependencies: Sequence[str]) -> list[str]:
    violations: list[str] = []
    for dependency in dependencies:
        requirement = Requirement(dependency)
        name = canonicalize_name(requirement.name)
        if name in HIGH_RISK_UPPER_BOUND_DEPENDENCIES and not _has_upper_bound(
            requirement.specifier
        ):
            violations.append(f"{name} must declare an upper bound such as <3.")
        if name.startswith(SHARED_BASE_DEPENDENCY_PREFIXES) and _has_exact_pin(
            requirement.specifier
        ):
            violations.append(
                f"{name} must not be exact-pinned in base runtime dependencies."
            )
    return violations


def highest_satisfying_release(
    requirement_text: str,
    releases: Iterable[str],
    *,
    environment: Mapping[str, str] | None = None,
) -> str | None:
    requirement = Requirement(requirement_text)
    marker_environment = default_environment()
    if environment is not None:
        marker_environment.update(environment)
    if requirement.marker is not None and not requirement.marker.evaluate(
        marker_environment
    ):
        return None

    selected: Version | None = None
    for release in releases:
        try:
            version = Version(release)
        except InvalidVersion:
            continue
        if version.is_prerelease and not requirement.specifier.prereleases:
            continue
        if version in requirement.specifier:
            selected = version if selected is None else max(selected, version)
    return str(selected) if selected is not None else None


def run_policy(pyproject: Path) -> None:
    violations = validate_dependency_policy(load_runtime_dependencies(pyproject))
    if violations:
        raise SystemExit(
            "\n".join(f"dependency policy violation: {v}" for v in violations)
        )
    print("dependency policy ok")


def run_clean_install(dist_dir: Path) -> None:
    wheel = _single_wheel(dist_dir)
    with tempfile.TemporaryDirectory(prefix="veadk-dependency-e2e-") as temp_dir:
        venv = Path(temp_dir) / "venv"
        _create_venv(venv)
        python = _venv_python(venv)
        _run([python, "-m", "pip", "install", "--upgrade", "pip"])
        _run([python, "-m", "pip", "install", str(wheel)])
        _run([python, "-m", "pip", "check"])
        _run([python, "-c", RUNTIME_IMPORT_SMOKE])


def run_declared_range(pyproject: Path, dist_dir: Path) -> None:
    wheel = _single_wheel(dist_dir)
    with tempfile.TemporaryDirectory(prefix="veadk-dependency-range-") as temp_dir:
        venv = Path(temp_dir) / "venv"
        _create_venv(venv)
        python = _venv_python(venv)
        _run([python, "-m", "pip", "install", "--upgrade", "pip"])
        print(
            "checking high-risk dependency upgrades against the built wheel metadata, "
            "including current pinned runtime dependencies",
            flush=True,
        )
        pins = highest_runtime_dependency_pins(
            load_runtime_dependencies(pyproject),
            python=python,
        )
        failures: list[str] = []
        for pin in pins:
            print(f"checking declared range with {pin}", flush=True)
            command = [
                python,
                "-m",
                "pip",
                "install",
                "--dry-run",
                "--ignore-installed",
                str(wheel),
                pin,
            ]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    check=False,
                    text=True,
                    timeout=300,
                )
            except subprocess.TimeoutExpired as exc:
                failures.append(pin)
                print(
                    f"dependency range check timed out for {pin}: {' '.join(command)}",
                    file=sys.stderr,
                    flush=True,
                )
                if exc.stdout:
                    print(exc.stdout, flush=True)
                if exc.stderr:
                    print(exc.stderr, file=sys.stderr, flush=True)
                continue
            if result.returncode:
                failures.append(pin)
                if result.stdout:
                    print(result.stdout, flush=True)
                if result.stderr:
                    print(result.stderr, file=sys.stderr, flush=True)
            else:
                print(f"declared range ok: {pin}", flush=True)
        if failures:
            raise SystemExit(declared_range_failure_message(failures))
    print("declared range dependency pins:")
    for pin in pins:
        print(f"  {pin}")


def declared_range_failure_message(failures: Sequence[str]) -> str:
    formatted_failures = "\n".join(f"  - {pin}" for pin in failures)
    return (
        "Dependency E2E failed: the built VeADK wheel cannot be resolved with "
        "one or more high-risk dependencies at the highest versions allowed by "
        "pyproject.toml. This may mean the upgraded dependency conflicts with "
        "another current runtime pin.\n"
        "Failing dependency pins:\n"
        f"{formatted_failures}\n"
        "Developer action: inspect the pip resolver error above, then either "
        "fix VeADK compatibility or tighten the affected dependency's version "
        "range so published metadata does not allow an uninstallable "
        "combination."
    )


def highest_runtime_dependency_pins(
    dependencies: Sequence[str], *, python: str | None = None
) -> list[str]:
    candidates: list[str] = []
    for dependency in dependencies:
        requirement = Requirement(dependency)
        name = canonicalize_name(requirement.name)
        if name not in DECLARED_RANGE_CHECK_DEPENDENCIES:
            continue
        if requirement.url is not None:
            continue
        if not requirement_applies(requirement):
            continue
        candidates.append(dependency)

    pins = [
        _highest_runtime_dependency_pin(dependency, python=python)
        for dependency in candidates
    ]
    return [pin for pin in pins if pin is not None]


def _highest_runtime_dependency_pin(
    dependency: str, *, python: str | None
) -> str | None:
    requirement = Requirement(dependency)
    print(f"resolving highest declared release for {requirement.name}", flush=True)
    version = highest_declared_bound(requirement)
    if version is None:
        releases = _pypi_releases(requirement.name, python=python)
        version = highest_satisfying_release(dependency, releases)
    if version is None:
        return None
    return f"{requirement.name}=={version}"


def highest_declared_bound(requirement: Requirement) -> str | None:
    selected: Version | None = None
    for specifier in requirement.specifier:
        if specifier.operator not in {"==", "===", "<="}:
            continue
        try:
            version = Version(specifier.version)
        except InvalidVersion:
            continue
        if version in requirement.specifier:
            selected = version if selected is None else min(selected, version)
    return str(selected) if selected is not None else None


def requirement_applies(
    requirement: Requirement, environment: Mapping[str, str] | None = None
) -> bool:
    if requirement.marker is None:
        return True
    marker_environment = default_environment()
    if environment is not None:
        marker_environment.update(environment)
    return requirement.marker.evaluate(marker_environment)


def _pypi_releases(package_name: str, *, python: str | None) -> list[str]:
    if python is not None:
        releases = _pip_index_releases(package_name, python=python)
        if releases:
            return releases
    url = f"https://pypi.org/simple/{package_name}/"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.pypi.simple.v1+json",
            "User-Agent": "veadk-dependency-e2e",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
    except Exception as exc:
        raise SystemExit(
            f"Failed to resolve PyPI releases for {package_name}: {exc}"
        ) from exc

    if "files" not in data:
        url = f"https://pypi.org/pypi/{package_name}/json"
        request = urllib.request.Request(
            url, headers={"User-Agent": "veadk-dependency-e2e"}
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
        return _legacy_pypi_releases(data)

    return _simple_pypi_releases(data)


def _pip_index_releases(package_name: str, *, python: str) -> list[str]:
    try:
        result = subprocess.run(
            [python, "-m", "pip", "index", "versions", package_name],
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(
            f"Timed out while resolving PyPI releases for {package_name}."
        ) from exc
    if result.returncode:
        return []
    for line in result.stdout.splitlines():
        if line.startswith("Available versions:"):
            return [
                version.strip()
                for version in line.split(":", 1)[1].split(",")
                if version.strip()
            ]
    first_line = result.stdout.splitlines()[0] if result.stdout.splitlines() else ""
    if first_line.startswith(f"{package_name} (") and first_line.endswith(")"):
        return [first_line.rsplit("(", 1)[1].removesuffix(")")]
    return []


def _legacy_pypi_releases(data: Mapping[str, object]) -> list[str]:
    releases: list[str] = []
    python_version = Version(default_environment()["python_full_version"])
    raw_releases = data.get("releases")
    if not isinstance(raw_releases, dict):
        return releases
    for version, files in raw_releases.items():
        if not isinstance(files, list) or not files:
            continue
        if all(isinstance(file, dict) and file.get("yanked", False) for file in files):
            continue
        if not any(
            isinstance(file, dict) and _file_supports_python(file, python_version)
            for file in files
        ):
            continue
        releases.append(str(version))
    return releases


def _simple_pypi_releases(data: Mapping[str, object]) -> list[str]:
    raw_files = data.get("files")
    if not isinstance(raw_files, list):
        return []
    python_version = Version(default_environment()["python_full_version"])
    releases: set[str] = set()
    for file in raw_files:
        if not isinstance(file, dict):
            continue
        if file.get("yanked", False):
            continue
        if not _file_supports_python(file, python_version):
            continue
        version = _version_from_filename(file.get("filename"))
        if version is not None:
            releases.add(version)
    return sorted(releases, key=Version)


def _version_from_filename(filename: object) -> str | None:
    if not isinstance(filename, str):
        return None
    try:
        if filename.endswith(".whl"):
            return str(parse_wheel_filename(filename)[1])
        return str(parse_sdist_filename(filename)[1])
    except Exception:
        return None


def _file_supports_python(file: Mapping[str, object], python_version: Version) -> bool:
    requires_python = file.get("requires_python")
    if not isinstance(requires_python, str) or not requires_python:
        return True
    try:
        return python_version in SpecifierSet(requires_python)
    except Exception:
        return True


def _has_upper_bound(specifier: SpecifierSet) -> bool:
    return any(spec.operator in UPPER_BOUND_OPERATORS for spec in specifier)


def _has_exact_pin(specifier: SpecifierSet) -> bool:
    return any(spec.operator in {"==", "==="} for spec in specifier)


def _single_wheel(dist_dir: Path) -> Path:
    wheels = sorted(dist_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(
            f"Expected exactly one wheel in {dist_dir}, found {len(wheels)}."
        )
    return wheels[0]


def _create_venv(venv: Path) -> None:
    _run([sys.executable, "-m", "venv", str(venv)])


def _venv_python(venv: Path) -> str:
    executable = "python.exe" if os.name == "nt" else "python"
    python = venv / ("Scripts" if os.name == "nt" else "bin") / executable
    return str(python)


def _run(command: Sequence[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("policy")
    subparsers.add_parser("clean-install")
    subparsers.add_parser("declared-range")
    args = parser.parse_args(argv)

    if args.command == "policy":
        run_policy(args.pyproject)
    elif args.command == "clean-install":
        run_clean_install(args.dist_dir)
    elif args.command == "declared-range":
        run_declared_range(args.pyproject, args.dist_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
