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

"""Build and publish a Studio bundle without importing the VeADK package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_VERSION_PATTERN = re.compile(r"^\d{14}$")
_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_STUDIO_BUNDLE_BYTES = 300 * 1024 * 1024
_MAX_STUDIO_RELEASES = 50


class StudioPublisherError(ValueError):
    """Raised when a Studio release cannot be built or published."""


@dataclass(frozen=True)
class StudioReleaseManifest:
    """Public metadata for one immutable Studio release bundle."""

    version: str
    git_sha: str
    sha256: str
    size: int
    created_at: str
    changelog: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            parsed_version = datetime.strptime(self.version, "%Y%m%d%H%M%S").replace(
                tzinfo=ZoneInfo("Asia/Shanghai")
            )
        except ValueError as error:
            raise StudioPublisherError(
                "Studio release version must use Beijing time YYYYMMDDHHMMSS."
            ) from error
        if not _VERSION_PATTERN.fullmatch(self.version) or parsed_version.year < 2025:
            raise StudioPublisherError(
                "Studio release version must use Beijing time YYYYMMDDHHMMSS."
            )
        if not _GIT_SHA_PATTERN.fullmatch(self.git_sha):
            raise StudioPublisherError("Studio release gitSha must be a 40-digit SHA.")
        if not _SHA256_PATTERN.fullmatch(self.sha256):
            raise StudioPublisherError("Studio release sha256 is invalid.")
        if self.size <= 0 or self.size > _MAX_STUDIO_BUNDLE_BYTES:
            raise StudioPublisherError("Studio release bundle size is invalid.")
        try:
            datetime.fromisoformat(self.created_at)
        except ValueError as error:
            raise StudioPublisherError(
                "Studio release createdAt is invalid."
            ) from error
        if len(self.changelog) > 50 or any(
            not item.strip() or len(item) > 240 for item in self.changelog
        ):
            raise StudioPublisherError("Studio release changelog is invalid.")

    @classmethod
    def from_json(cls, payload: bytes | str) -> StudioReleaseManifest:
        try:
            raw = json.loads(payload)
            return cls(
                version=str(raw["version"]),
                git_sha=str(raw["gitSha"]),
                sha256=str(raw["sha256"]),
                size=int(raw["size"]),
                created_at=str(raw["createdAt"]),
                changelog=tuple(str(item) for item in raw.get("changelog", [])),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise StudioPublisherError("Studio release manifest is invalid.") from error

    def to_json(self) -> bytes:
        data = asdict(self)
        payload = {
            "version": data["version"],
            "gitSha": data["git_sha"],
            "sha256": data["sha256"],
            "size": data["size"],
            "createdAt": data["created_at"],
            "changelog": list(data["changelog"]),
        }
        return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()


def _normalize_prefix(prefix: str) -> str:
    normalized = prefix.strip().strip("/")
    if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise StudioPublisherError("Studio release prefix is invalid.")
    return normalized


def _bundle_key(prefix: str, version: str) -> str:
    return f"{prefix}/releases/{version}/studio-bundle.zip"


def _manifest_key(prefix: str, version: str) -> str:
    return f"{prefix}/releases/{version}/manifest.json"


def _latest_key(prefix: str) -> str:
    return f"{prefix}/latest.json"


def _catalog_key(prefix: str) -> str:
    return f"{prefix}/releases.json"


def _read_object(response: Any, max_bytes: int) -> bytes:
    content = bytearray()
    for chunk in response:
        if len(content) + len(chunk) > max_bytes:
            raise StudioPublisherError("Studio release manifest is too large.")
        content.extend(chunk)
    return bytes(content)


def _is_not_found(error: Exception) -> bool:
    return isinstance(error, KeyError) or getattr(error, "status_code", None) == 404


class StudioReleaseStore:
    """Publish immutable release objects and move the latest pointer last."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
        session_token: str,
        prefix: str,
        provider: str = "volcengine",
    ) -> None:
        import tos

        self._bucket = bucket
        self._prefix = _normalize_prefix(prefix)
        self._client = tos.TosClientV2(
            access_key,
            secret_key,
            security_token=session_token or None,
            endpoint=(
                f"tos-{region}.bytepluses.com"
                if provider == "byteplus"
                else f"tos-{region}.volces.com"
            ),
            region=region,
        )

    def publish(self, bundle: Path, manifest: StudioReleaseManifest) -> None:
        content = bundle.read_bytes()
        if (
            len(content) != manifest.size
            or hashlib.sha256(content).hexdigest() != manifest.sha256
        ):
            raise StudioPublisherError(
                "Studio release bundle does not match its manifest."
            )
        releases = self._existing_releases()
        if any(item.version > manifest.version for item in releases):
            raise StudioPublisherError(
                "Studio release version must be newer than the published releases."
            )
        manifest_bytes = manifest.to_json()
        self._client.put_object(
            bucket=self._bucket,
            key=_bundle_key(self._prefix, manifest.version),
            content=content,
            content_type="application/zip",
            forbid_overwrite=True,
        )
        self._client.put_object(
            bucket=self._bucket,
            key=_manifest_key(self._prefix, manifest.version),
            content=manifest_bytes,
            content_type="application/json",
            forbid_overwrite=True,
        )
        releases = [item for item in releases if item.version != manifest.version]
        releases.append(manifest)
        releases.sort(key=lambda item: item.version, reverse=True)
        catalog = (
            json.dumps(
                {
                    "releases": [
                        json.loads(item.to_json())
                        for item in releases[:_MAX_STUDIO_RELEASES]
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode()
        self._client.put_object(
            bucket=self._bucket,
            key=_catalog_key(self._prefix),
            content=catalog,
            content_type="application/json",
        )
        self._client.put_object(
            bucket=self._bucket,
            key=_latest_key(self._prefix),
            content=manifest_bytes,
            content_type="application/json",
        )

    def _existing_releases(self) -> list[StudioReleaseManifest]:
        try:
            response = self._client.get_object(
                bucket=self._bucket,
                key=_catalog_key(self._prefix),
            )
            raw_releases = json.loads(_read_object(response, 512 * 1024))["releases"]
            if (
                not isinstance(raw_releases, list)
                or len(raw_releases) > _MAX_STUDIO_RELEASES
            ):
                raise StudioPublisherError("Studio release catalog is invalid.")
            releases = [
                StudioReleaseManifest.from_json(json.dumps(item))
                for item in raw_releases
            ]
            return sorted(releases, key=lambda item: item.version, reverse=True)
        except Exception as error:
            if not _is_not_found(error):
                raise
        try:
            response = self._client.get_object(
                bucket=self._bucket,
                key=_latest_key(self._prefix),
            )
            return [StudioReleaseManifest.from_json(_read_object(response, 64 * 1024))]
        except Exception as error:
            if _is_not_found(error):
                return []
            raise


def _validate_source_checkout(source_root: Path) -> None:
    required = (
        source_root / "pyproject.toml",
        source_root / "README.md",
        source_root / "LICENSE",
        source_root / "frontend" / "package.json",
        source_root / "frontend" / "package-lock.json",
        source_root / "veadk",
    )
    if not all(path.exists() for path in required):
        raise StudioPublisherError("Release source is not a VeADK checkout.")


def _build_frontend_assets(
    source_root: Path,
    output_dir: Path,
    env: Mapping[str, str],
    *,
    changelog: tuple[str, ...] = (),
) -> None:
    npm = shutil.which("npm", path=env.get("PATH"))
    if npm is None:
        raise StudioPublisherError("npm is required to build the Studio frontend.")
    build_environment = dict(env)
    build_environment["VITE_STUDIO_RELEASE_CHANGELOG"] = json.dumps(
        list(changelog), ensure_ascii=False
    )
    try:
        subprocess.run(
            [npm, "ci"],
            cwd=source_root / "frontend",
            env=build_environment,
            check=True,
        )
        subprocess.run(
            [npm, "run", "build", "--", "--outDir", str(output_dir)],
            cwd=source_root / "frontend",
            env=build_environment,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise StudioPublisherError(
            f"Studio frontend build failed with exit code {error.returncode}."
        ) from error
    if not (output_dir / "index.html").is_file():
        raise StudioPublisherError("Studio frontend build produced no index.html.")


def stage_studio_wheel_source(
    source_root: Path,
    frontend_assets: Path,
    wheel_source: Path,
) -> None:
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
    frontend_root = source_root / "frontend"

    def ignore_frontend_build_inputs(directory: str, names: list[str]) -> set[str]:
        current = Path(directory)
        ignored = {
            name
            for name in names
            if name == "__pycache__"
            or name.endswith(".pyc")
            or name == ".vite"
            or name == ".env"
            or name.startswith(".env.")
        }
        if current == frontend_root:
            ignored.update(
                {
                    "README.md",
                    "SPEC.md",
                    "dist",
                    "index.html",
                    "node_modules",
                    "package-lock.json",
                    "package.json",
                    "public",
                    "scripts",
                    "skills",
                    "src",
                    "tests",
                    "tsconfig.json",
                    "vite.config.ts",
                    "vite.website-integration.config.ts",
                    "vitest.harness-sidecar.config.ts",
                }.intersection(names)
            )
        return ignored

    shutil.copytree(
        frontend_root,
        wheel_source / "frontend",
        ignore=ignore_frontend_build_inputs,
    )
    shutil.copytree(frontend_assets, wheel_source / "veadk" / "webui")


def studio_runtime_modules(source_root: Path) -> set[str]:
    """List every importable Python module shipped in the Studio wheel."""
    return {
        source.relative_to(source_root).as_posix()
        for package_name in ("veadk", "frontend")
        for source in (source_root / package_name).rglob("*.py")
    }


def validate_studio_wheel(wheel: Path, source_root: Path) -> None:
    """Reject release wheels missing any importable Studio runtime module."""
    required_modules = studio_runtime_modules(source_root)
    try:
        with zipfile.ZipFile(wheel) as archive:
            missing = required_modules.difference(archive.namelist())
    except (OSError, zipfile.BadZipFile) as error:
        raise StudioPublisherError("Built VeADK wheel is invalid.") from error
    if missing:
        raise StudioPublisherError(
            "Built VeADK wheel is missing Studio runtime modules: "
            + ", ".join(sorted(missing))
        )


def _build_local_requirements(
    source_root: Path,
    package_dir: Path,
    frontend_assets: Path,
    dependency_wheels: Path,
    env: Mapping[str, str],
) -> str:
    wheel_source = package_dir / "wheel-source"
    stage_studio_wheel_source(source_root, frontend_assets, wheel_source)
    uv = shutil.which("uv", path=env.get("PATH"))
    if uv is None:
        raise StudioPublisherError("uv is required to build the VeADK wheel.")
    try:
        subprocess.run(
            [uv, "build", "--wheel", str(wheel_source), "-o", str(package_dir)],
            env=env,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise StudioPublisherError(
            f"Local VeADK wheel build failed with exit code {error.returncode}."
        ) from error
    built_wheels = sorted(package_dir.glob("veadk*.whl"))
    if len(built_wheels) != 1:
        raise StudioPublisherError(
            "Local source build did not produce one VeADK wheel."
        )
    validate_studio_wheel(built_wheels[0], wheel_source)
    dependencies: list[Path] = []
    for source in sorted(dependency_wheels.glob("*.whl")):
        target = package_dir / source.name
        shutil.copy2(source, target)
        dependencies.append(target)
    if not dependencies:
        raise StudioPublisherError("Prepared Studio dependency wheels are missing.")
    shutil.rmtree(wheel_source)
    return "".join(f"./{path.name}\n" for path in (*dependencies, built_wheels[0]))


def _studio_run_script() -> str:
    return (
        "#!/bin/bash\n"
        "set -ex\n"
        'ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        'cd "$ROOT_DIR"\n'
        'if [ -d "output" ]; then cd ./output/; fi\n'
        "HOST=0.0.0.0\n"
        "PORT=${_FAAS_RUNTIME_PORT:-8000}\n"
        "export PYTHONPATH=$PYTHONPATH:./site-packages\n"
        "exec python3 -m veadk.cli.cli studio "
        '--provider "${CLOUD_PROVIDER:-${AGENTKIT_CLOUD_PROVIDER:-volcengine}}" '
        "--auth-mode frontend "
        '--host "$HOST" --port "$PORT"\n'
    )


def _zip_directory(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source))


def build_studio_release(
    *,
    source_root: Path,
    output_dir: Path,
    version: str,
    git_sha: str,
    changelog: tuple[str, ...],
    frontend_assets: Path | None,
    dependency_wheels: Path,
    env: Mapping[str, str],
) -> tuple[Path, StudioReleaseManifest]:
    """Build a release while treating VeADK only as source input."""
    _validate_source_checkout(source_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="studio_release_publisher_") as tmp:
        workspace = Path(tmp)
        resolved_frontend = frontend_assets
        if resolved_frontend is None:
            resolved_frontend = workspace / "frontend"
            _build_frontend_assets(
                source_root,
                resolved_frontend,
                env,
                changelog=changelog,
            )
        elif not (resolved_frontend / "index.html").is_file():
            raise StudioPublisherError(
                "Prepared Studio frontend assets contain no index.html."
            )
        package_dir = workspace / "package"
        package_dir.mkdir()
        requirements = _build_local_requirements(
            source_root,
            package_dir,
            resolved_frontend,
            dependency_wheels,
            env,
        )
        (package_dir / "run.sh").write_text(
            _studio_run_script(),
            encoding="utf-8",
            newline="\n",
        )
        (package_dir / "requirements.txt").write_text(requirements, encoding="utf-8")
        bundle = output_dir / f"studio-bundle-{version}.zip"
        _zip_directory(package_dir, bundle)
    content = bundle.read_bytes()
    manifest = StudioReleaseManifest(
        version=version,
        git_sha=git_sha,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        created_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(
            timespec="seconds"
        ),
        changelog=changelog,
    )
    (output_dir / f"manifest-{version}.json").write_bytes(manifest.to_json())
    return bundle, manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument(
        "--provider",
        choices=("volcengine", "byteplus"),
        default="volcengine",
    )
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--changelog", action="append", default=[])
    parser.add_argument("--frontend-assets", type=Path)
    parser.add_argument("--dependency-wheels", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    bundle, manifest = build_studio_release(
        source_root=args.source_root.resolve(),
        output_dir=args.output_dir.resolve(),
        version=args.version,
        git_sha=args.git_sha,
        changelog=tuple(args.changelog),
        frontend_assets=args.frontend_assets,
        dependency_wheels=args.dependency_wheels,
        env=os.environ,
    )
    credential_prefix = "BYTEPLUS" if args.provider == "byteplus" else "VOLCENGINE"
    store = StudioReleaseStore(
        bucket=args.bucket,
        region=args.region,
        access_key=os.getenv(f"{credential_prefix}_ACCESS_KEY", ""),
        secret_key=os.getenv(f"{credential_prefix}_SECRET_KEY", ""),
        session_token=os.getenv(f"{credential_prefix}_SESSION_TOKEN", ""),
        prefix=args.prefix,
        provider=args.provider,
    )
    store.publish(bundle, manifest)
    print(
        json.dumps(
            {
                "version": manifest.version,
                "gitSha": manifest.git_sha,
                "sha256": manifest.sha256,
                "size": manifest.size,
            }
        )
    )


if __name__ == "__main__":
    main()
