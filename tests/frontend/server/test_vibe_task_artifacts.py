from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from frontend.server.vibe_task.artifacts import (
    ArtifactDescriptor,
    ArtifactError,
    ArtifactManifest,
    MANIFEST_FILENAME,
    artifact_path,
    download_and_validate_artifact,
    package_project,
    remote_artifact_request,
    REMOTE_ARTIFACT_WORKER_SOURCE,
)


_HASHES = {
    "runtime_sha256": "1" * 64,
    "status_sha256": "2" * 64,
    "invoke_sha256": "3" * 64,
    "log_sha256": "4" * 64,
}


def manifest(revision: int = 3) -> ArtifactManifest:
    return ArtifactManifest(revision=revision, intent_revision=7, **_HASHES)


def test_packages_project_with_manifest_and_exclusions(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "agent.py").write_text("print('ok')\n")
    (project / "nested").mkdir()
    (project / "nested" / "config.json").write_text('{"enabled":true}\n')
    (project / ".env").write_text("SERVICE_TOKEN=not-packaged\n")
    (project / ".git").mkdir()
    (project / ".git" / "config").write_text("private")
    (project / "venv").mkdir()
    (project / "venv" / "python").write_text("binary")
    (project / "debug.log").write_text("raw log")
    (project / ".vibe").mkdir()
    (project / ".vibe" / "status.json").write_text("internal")

    descriptor = package_project(project, manifest(), artifact_root=tmp_path / "artifacts")

    output = tmp_path / "artifacts" / "3" / "artifact.zip"
    assert descriptor == ArtifactDescriptor(
        revision=3,
        path=artifact_path(3),
        sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        size=output.stat().st_size,
    )
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == [
            MANIFEST_FILENAME,
            "agent.py",
            "nested/config.json",
        ]
        value = json.loads(archive.read(MANIFEST_FILENAME))
    assert value == {
        "schemaVersion": 1,
        "revision": 3,
        "intentRevision": 7,
        "evaluationPerformed": False,
        "hashes": {
            "runtime": "1" * 64,
            "status": "2" * 64,
            "invoke": "3" * 64,
            "log": "4" * 64,
        },
    }


def test_remote_worker_is_dependency_free_and_request_is_canonical() -> None:
    compile(REMOTE_ARTIFACT_WORKER_SOURCE, "artifact-worker.py", "exec")
    assert "frontend.server" not in REMOTE_ARTIFACT_WORKER_SOURCE
    request = remote_artifact_request("vt-" + "a" * 12 + "-" + "b" * 24, manifest(1))
    assert request.endswith(b"\n")
    assert json.loads(request)["manifest"]["hashes"]["runtime"] == "1" * 64


def test_remote_worker_packages_expected_fixed_paths(tmp_path: Path) -> None:
    home = tmp_path / "home" / "gem"
    task_id = "vt-" + "a" * 12 + "-" + "b" * 24
    project = home / "workspace" / task_id
    project.mkdir(parents=True)
    (project / "agent.py").write_text("pass\n")
    task_root = home / ".vibe" / "task"
    task_root.mkdir(parents=True)
    worker = task_root / "artifact-worker.py"
    request_path = task_root / "artifact-request.json"
    source = REMOTE_ARTIFACT_WORKER_SOURCE.replace(
        'ROOT = "/home/gem/.vibe/task/artifacts"', f"ROOT = {str(task_root / 'artifacts')!r}"
    ).replace('WORKSPACES = "/home/gem/workspace"', f"WORKSPACES = {str(home / 'workspace')!r}")
    source = source.replace(
        'sys.argv[1] != "/home/gem/.vibe/task/artifact-request.json"',
        f"sys.argv[1] != {str(request_path)!r}",
    )
    worker.write_text(source)
    request_path.write_bytes(remote_artifact_request(task_id, manifest(1)))

    completed = subprocess.run(
        [sys.executable, str(worker), str(request_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    descriptor = json.loads(completed.stdout)
    output = task_root / "artifacts" / "1" / "artifact.zip"
    assert descriptor["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert json.loads((output.parent / "descriptor.json").read_text()) == descriptor
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == [MANIFEST_FILENAME, "agent.py"]


def test_package_is_deterministic_across_source_mtimes(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    first = project / "z.py"
    second = project / "a.py"
    first.write_text("z = 1\n")
    second.write_text("a = 1\n")

    one = package_project(project, manifest(1), artifact_root=tmp_path / "one")
    first.touch()
    second.touch()
    two = package_project(project, manifest(1), artifact_root=tmp_path / "two")

    assert one.sha256 == two.sha256
    assert (tmp_path / "one/1/artifact.zip").read_bytes() == (
        tmp_path / "two/1/artifact.zip"
    ).read_bytes()


@pytest.mark.parametrize(
    "contents, supplied",
    [
        ("token = supplied-value\n", ("supplied-value",)),
        ("SERVICE_SECRET_ACCESS_KEY=embedded-value\n", ()),
        ("password: embedded-value\n", ()),
    ],
)
def test_rejects_supplied_secrets_and_sensitive_assignments(
    tmp_path: Path, contents: str, supplied: tuple[str, ...]
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "config.py").write_text(contents)

    with pytest.raises(ArtifactError, match="secret|Sensitive"):
        package_project(
            project,
            manifest(),
            secret_values=supplied,
            artifact_root=tmp_path / "artifacts",
        )


def test_rejects_symlink_and_file_count_limit(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    (project / "link").symlink_to(outside)
    with pytest.raises(ArtifactError, match="Symlinks"):
        package_project(project, manifest(), artifact_root=tmp_path / "artifacts")

    (project / "link").unlink()
    (project / "one").write_text("1")
    (project / "two").write_text("2")
    with pytest.raises(ArtifactError, match="file count"):
        package_project(
            project,
            manifest(),
            artifact_root=tmp_path / "artifacts",
            max_files=1,
        )


class Transport:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.calls: list[tuple[str, int]] = []

    async def download(self, path: str, *, max_bytes: int) -> bytes:
        self.calls.append((path, max_bytes))
        return self.content


@pytest.mark.asyncio
async def test_host_download_validates_descriptor_digest_and_zip(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "agent.py").write_text("pass\n")
    descriptor = package_project(
        project, manifest(), artifact_root=tmp_path / "artifacts"
    )
    content = (tmp_path / "artifacts/3/artifact.zip").read_bytes()
    transport = Transport(content)

    assert await download_and_validate_artifact(transport, descriptor) == content
    assert transport.calls == [(artifact_path(3), len(content))]

    bad_digest = {**descriptor.as_dict(), "sha256": "0" * 64}
    with pytest.raises(ArtifactError, match="digest"):
        await download_and_validate_artifact(Transport(content), bad_digest)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/home/gem/.vibe/task/artifacts/3/../artifact.zip",
        "/home/gem/.vibe/task/artifacts/4/artifact.zip",
        "/tmp/artifact.zip",
    ],
)
async def test_host_rejects_descriptor_path_manipulation(path: str) -> None:
    descriptor = {
        "revision": 3,
        "path": path,
        "sha256": "0" * 64,
        "size": 1,
    }
    transport = Transport(b"x")
    with pytest.raises(ArtifactError, match="path"):
        await download_and_validate_artifact(transport, descriptor)
    assert transport.calls == []


@pytest.mark.asyncio
async def test_host_rejects_unsafe_zip_member() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(MANIFEST_FILENAME, "{}")
        archive.writestr("../escape", "bad")
    content = buffer.getvalue()
    descriptor = {
        "revision": 2,
        "path": artifact_path(2),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
    }
    with pytest.raises(ArtifactError, match="unsafe path"):
        await download_and_validate_artifact(Transport(content), descriptor)
