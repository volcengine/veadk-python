from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parents[2]
    / "plugins/agentkit-studio/skills/codex-sandbox-upload/scripts/upload_project.py"
)


@pytest.fixture(scope="module")
def upload_project():
    spec = importlib.util.spec_from_file_location("codex_sandbox_upload", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    )


def _fixture_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "app.py").write_text('print("before")\n', encoding="utf-8")
    (repo / "deleted.txt").write_text("delete me\n", encoding="utf-8")
    (repo / "AGENTS.md").write_text("# Project instructions\n", encoding="utf-8")
    (repo / "important.log").write_text("tracked log\n", encoding="utf-8")
    (repo / ".coverage").write_text("tracked coverage\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "feat/demo", str(repo)], check=True)
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "remote", "add", "origin", "git@github.com:example/demo.git")
    (repo / "app.py").write_text('print("after")\n', encoding="utf-8")
    (repo / "deleted.txt").unlink()
    (repo / "new.txt").write_text("new file\n", encoding="utf-8")


def test_build_and_restore_preserves_worktree_and_github_auth(
    upload_project, tmp_path: Path
) -> None:
    source = tmp_path / "source"
    work = tmp_path / "work"
    stage = tmp_path / "stage"
    home = tmp_path / "home"
    destination = home / "demo"
    for directory in (work, stage, home):
        directory.mkdir()
    _fixture_repo(source)

    state = upload_project.inspect_project(source)
    bundle = upload_project.build_bundle(state, "demo", None, work, True)
    with tarfile.open(bundle, "r:gz") as archive:
        assert "github-credentials.json" not in archive.getnames()
        archive.extractall(stage)

    token = "ghp_test_secret_1234567890"
    credentials = tmp_path / "github-credentials.json"
    upload_project.write_github_credentials(credentials, token)
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    restored = subprocess.run(
        [
            sys.executable,
            str(stage / "restore_project.py"),
            "--stage",
            str(stage),
            "--repo",
            str(destination),
            "--github-credentials",
            str(credentials),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    result = json.loads(restored.stdout.strip().splitlines()[-1])

    assert result["githubAuth"] is True
    assert (destination / "app.py").read_text(encoding="utf-8") == 'print("after")\n'
    assert not (destination / "deleted.txt").exists()
    assert (destination / "new.txt").read_text(encoding="utf-8") == "new file\n"
    assert (destination / "AGENTS.md").is_file()
    assert (destination / "HANDOFF.md").is_file()
    assert (destination / "important.log").read_text(
        encoding="utf-8"
    ) == "tracked log\n"
    assert (destination / ".coverage").read_text(
        encoding="utf-8"
    ) == "tracked coverage\n"
    assert (
        subprocess.check_output(
            ["git", "-C", str(destination), "remote", "get-url", "origin"],
            text=True,
        ).strip()
        == "https://github.com/example/demo.git"
    )
    token_path = home / ".config/agentkit-studio/github-token"
    assert token_path.read_text(encoding="utf-8").strip() == token
    assert stat.S_IMODE(token_path.stat().st_mode) == 0o600
    assert token in (home / ".config/gh/hosts.yml").read_text(encoding="utf-8")
    assert not credentials.exists()


def test_preview_flags_tracked_sensitive_files(upload_project, tmp_path: Path) -> None:
    repo = tmp_path / "source"
    repo.mkdir()
    (repo / ".env").write_text("SECRET_KEY=not-a-real-secret\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "add", ".env")

    state = upload_project.inspect_project(repo)

    assert state.sensitive_paths == (".env",)


def test_live_upload_requires_approval_for_secret_assignments(
    upload_project, tmp_path: Path
) -> None:
    repo = tmp_path / "source"
    repo.mkdir()
    (repo / "config.py").write_text('API_KEY="abcdefghijklmnop"\n', encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "add", "config.py")

    with pytest.raises(upload_project.HandoffError, match="sensitive file warnings"):
        upload_project.main(["--repo", str(repo), "--yes"])


def test_service_url_preserves_private_endpoint_query(upload_project) -> None:
    assert (
        upload_project.service_url(
            "https://sandbox.example/root?Authorization=secret",
            "/v1/file/upload",
        )
        == "https://sandbox.example/root/v1/file/upload?Authorization=secret"
    )


def test_sanitize_remote_removes_embedded_credentials(upload_project) -> None:
    assert (
        upload_project.sanitize_remote(
            "https://user:token@github.com/example/demo.git?access_token=secret"
        )
        == "https://github.com/example/demo.git"
    )
