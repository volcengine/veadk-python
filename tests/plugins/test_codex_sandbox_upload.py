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

from __future__ import annotations

import base64
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

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


def _history_file(tmp_path: Path) -> Path:
    history = tmp_path / "conversation-history.json"
    history.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "messages": [
                    {"role": "user", "content": "修复登录超时"},
                    {"role": "assistant", "content": "已定位重试逻辑。"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return history


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
    history = _history_file(tmp_path)

    with pytest.raises(upload_project.HandoffError, match="sensitive file warnings"):
        upload_project.main(
            [
                "--repo",
                str(repo),
                "--agent-name",
                "迁移项目",
                "--history",
                str(history),
                "--yes",
            ]
        )


def test_dry_run_builds_and_validates_the_actual_handoff_bundle(
    upload_project, tmp_path: Path
) -> None:
    repo = tmp_path / "source"
    repo.mkdir()
    (repo / "app.py").write_text('print("hello")\n', encoding="utf-8")
    history = _history_file(tmp_path)
    handoff = tmp_path / "handoff.md"
    handoff.write_text("# Continue the login timeout fix\n", encoding="utf-8")

    assert (
        upload_project.main(
            [
                "--repo",
                str(repo),
                "--studio-url",
                "https://studio.example",
                "--agent-name",
                "修复登录超时",
                "--handoff",
                str(handoff),
                "--history",
                str(history),
                "--dry-run",
            ]
        )
        == 0
    )
    with pytest.raises(upload_project.HandoffError, match="studio-url"):
        upload_project.main(
            [
                "--repo",
                str(repo),
                "--studio-url",
                "not-a-url",
                "--agent-name",
                "修复登录超时",
                "--handoff",
                str(handoff),
                "--history",
                str(history),
                "--dry-run",
            ]
        )
    with pytest.raises(upload_project.HandoffError, match="cannot read handoff"):
        upload_project.main(
            [
                "--repo",
                str(repo),
                "--studio-url",
                "https://studio.example",
                "--agent-name",
                "修复登录超时",
                "--handoff",
                str(tmp_path / "missing.md"),
                "--history",
                str(history),
                "--dry-run",
            ]
        )


def test_service_url_preserves_private_endpoint_query(upload_project) -> None:
    assert (
        upload_project.service_url(
            "https://sandbox.example/root?Authorization=secret",
            "/v1/file/upload",
        )
        == "https://sandbox.example/root/v1/file/upload?Authorization=secret"
    )


def test_tls_context_loads_macos_keychain_certificates(
    upload_project, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded: list[str] = []

    class Context:
        def load_verify_locations(self, *, cadata: str) -> None:
            loaded.append(cadata)

    monkeypatch.setattr(upload_project.sys, "platform", "darwin")
    monkeypatch.setattr(
        upload_project.shutil, "which", lambda _name: "/usr/bin/security"
    )
    monkeypatch.setattr(upload_project.ssl, "create_default_context", Context)
    monkeypatch.setattr(
        upload_project.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=b"-----BEGIN CERTIFICATE-----\ncert\n-----END CERTIFICATE-----\n",
        ),
    )

    assert isinstance(upload_project.tls_context(), Context)
    assert len(loaded) == 1
    assert loaded[0].count("-----BEGIN CERTIFICATE-----") == 3


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("完善端云接力", "完善端云接力"),
        ("  修复   登录超时  ", "修复 登录超时"),
        ("123456789012", "123456789012"),
    ],
)
def test_agent_name_normalizes_a_concise_task_description(
    upload_project, value: str, expected: str
) -> None:
    assert upload_project.agent_name(value) == expected


@pytest.mark.parametrize("value", ["", "1234567890123", "valid\x00name"])
def test_agent_name_rejects_missing_long_or_unsafe_values(
    upload_project, value: str
) -> None:
    with pytest.raises(upload_project.HandoffError, match="agent-name"):
        upload_project.agent_name(value)


def test_conversation_history_keeps_only_visible_user_and_assistant_text(
    upload_project, tmp_path: Path
) -> None:
    history = tmp_path / "history.json"
    history.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            '<in-app-browser-context source="ambient-ui-state">'
                            "browser state"
                            "</in-app-browser-context>\n\n"
                            "## My request:\n继续修复登录超时"
                        ),
                    },
                    {"role": "assistant", "content": " 已定位重试逻辑。 "},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert upload_project.conversation_history(history) == [
        {"role": "user", "content": "继续修复登录超时"},
        {"role": "assistant", "content": "已定位重试逻辑。"},
    ]


def test_conversation_history_embeds_local_markdown_images_without_leaking_paths(
    upload_project, tmp_path: Path
) -> None:
    image = tmp_path / "handoff.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"visible-image")
    history = tmp_path / "history.json"
    history.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "messages": [
                    {
                        "role": "user",
                        "content": f"请看图片\n\n![端云接力界面]({image})",
                    },
                    {"role": "assistant", "content": "图片已收到。"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    messages = upload_project.conversation_history(history)

    assert messages[0]["content"] == "请看图片"
    assert messages[0]["images"] == [
        {
            "mimeType": "image/png",
            "data": base64.b64encode(image.read_bytes()).decode("ascii"),
            "name": "handoff.png",
            "alt": "端云接力界面",
        }
    ]
    assert str(image) not in json.dumps(messages, ensure_ascii=False)


def test_conversation_history_rejects_symlinked_images(
    upload_project, tmp_path: Path
) -> None:
    target = tmp_path / "target.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\n" + b"visible-image")
    image = tmp_path / "handoff.png"
    image.symlink_to(target)
    history = tmp_path / "history.json"
    history.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "messages": [
                    {
                        "role": "user",
                        "content": "请看图片",
                        "images": [{"path": str(image), "alt": "截图"}],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(upload_project.HandoffError, match="symbolic link"):
        upload_project.conversation_history(history)


def test_conversation_history_rejects_hidden_roles(
    upload_project, tmp_path: Path
) -> None:
    history = tmp_path / "history.json"
    history.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "messages": [{"role": "developer", "content": "hidden instructions"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(upload_project.HandoffError, match="only user and assistant"):
        upload_project.conversation_history(history)


def test_studio_url_and_pairing_code_are_validated_locally(upload_project) -> None:
    assert upload_project.studio_url("https://studio.example/base/") == (
        "https://studio.example/base"
    )
    assert upload_project.pairing_code("abcd-efgh") == "ABCD-EFGH"
    with pytest.raises(upload_project.HandoffError, match="studio-url"):
        upload_project.studio_url("https://token@studio.example")
    with pytest.raises(upload_project.HandoffError, match="pairing code"):
        upload_project.pairing_code("invalid")


def test_upload_retries_while_new_session_data_plane_starts(
    upload_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "bundle.tar.gz"
    source.write_bytes(b"handoff")
    attempts = 0
    sleeps: list[float] = []

    class Response:
        status = 200

        @staticmethod
        def read() -> bytes:
            return b'{"success":true}'

    class Connection:
        def putrequest(self, *_args) -> None:
            pass

        def putheader(self, *_args) -> None:
            pass

        def endheaders(self) -> None:
            pass

        def send(self, _chunk: bytes) -> None:
            pass

        def getresponse(self):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ConnectionResetError("data plane is still starting")
            return Response()

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        upload_project,
        "connection",
        lambda _url: (Connection(), "/v1/file/upload"),
    )
    monkeypatch.setattr(upload_project.time, "sleep", sleeps.append)

    assert upload_project.upload_file(
        "https://sandbox.example?Authorization=secret",
        source,
        "/home/gem/bundle.tar.gz",
    ) == {"success": True}
    assert attempts == 2
    assert sleeps == [5.0]


def test_idempotent_json_post_retries_a_lost_response(
    upload_project, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = 0
    sleeps: list[float] = []

    class Response:
        status = 200

        @staticmethod
        def read() -> bytes:
            return b'{"sessionId":"remote-1"}'

    class Connection:
        def request(self, *_args, **_kwargs) -> None:
            pass

        def getresponse(self):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ConnectionResetError("response was lost")
            return Response()

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        upload_project,
        "connection",
        lambda _url: (Connection(), "/handoff"),
    )
    monkeypatch.setattr(upload_project.time, "sleep", sleeps.append)

    assert upload_project.post_json(
        "https://studio.example/handoff",
        {"handoffId": "a" * 32},
        "Studio session creation",
        attempts=2,
        retry_delay_seconds=0.25,
    ) == {"sessionId": "remote-1"}
    assert attempts == 2
    assert sleeps == [0.25]


def test_event_stream_rejects_failed_completion_without_an_error_event(
    upload_project, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Response:
        status = 200

        def __init__(self) -> None:
            self._lines = iter(
                [
                    b"event: done\n",
                    b'data: {"reason":"failed"}\n',
                    b"\n",
                ]
            )

        def readline(self) -> bytes:
            return next(self._lines, b"")

    class Connection:
        def request(self, *_args, **_kwargs) -> None:
            pass

        def getresponse(self):
            return Response()

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        upload_project,
        "connection",
        lambda _url: (Connection(), "/messages"),
    )

    with pytest.raises(upload_project.HandoffError, match="failed in Studio"):
        upload_project.post_event_stream(
            "https://studio.example/messages", {}, "Studio cloud continuation"
        )


def test_event_stream_reports_progress_and_returns_after_cloud_accepts_task(
    upload_project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Response:
        status = 200

        def __init__(self) -> None:
            self._lines = iter(
                [
                    b"event: progress\n",
                    '{"stage":"connecting-session","message":"正在连接云端 Session"}',
                    b"\n",
                    b"event: progress\n",
                    '{"stage":"task-started","message":"云端 Codex 已接收任务，正在继续执行"}',
                    b"\n",
                    b"event: done\n",
                    b'data: {"reason":"accepted"}\n',
                    b"\n",
                ]
            )

        def readline(self) -> bytes:
            line = next(self._lines, b"")
            if isinstance(line, str):
                return f"data: {line}\n".encode()
            return line

    class Connection:
        def request(self, *_args, **_kwargs) -> None:
            pass

        def getresponse(self):
            return Response()

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        upload_project,
        "connection",
        lambda _url: (Connection(), "/messages"),
    )

    upload_project.post_event_stream(
        "https://studio.example/messages", {}, "Studio cloud continuation"
    )

    output = capsys.readouterr().out
    assert "[handoff] progress: 正在连接云端 Session" in output
    assert "[handoff] progress: 云端 Codex 已接收任务，正在继续执行" in output


def test_cloud_continuation_injects_history_before_exact_user_message(
    upload_project, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[tuple[str, dict[str, object], str]] = []
    history = [
        {"role": "user", "content": "修复登录超时"},
        {"role": "assistant", "content": "已定位重试逻辑。"},
    ]
    monkeypatch.setattr(
        upload_project,
        "post_event_stream",
        lambda url, payload, action: requests.append((url, payload, action)),
    )

    upload_project.continue_in_studio(
        "https://studio.example",
        "remote-1",
        "ABCD-EFGH",
        history,
        "继续",
    )

    assert requests == [
        (
            "https://studio.example/web/sandbox/codex-project-handoff/sessions/remote-1/messages",
            {
                "pairingCode": "ABCD-EFGH",
                "history": history,
                "message": "继续",
            },
            "Studio cloud continuation",
        )
    ]


def test_remote_restore_emits_heartbeat_while_restore_runs(
    upload_project, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[dict[str, object]] = []

    def fake_post_json(_url, payload, _action):
        requests.append(payload)
        return {
            "data": {
                "status": "completed",
                "exit_code": 0,
                "output": '{"restored":true,"fileCount":2}',
            }
        }

    monkeypatch.setattr(upload_project, "post_json", fake_post_json)

    assert upload_project.remote_restore(
        "https://sandbox.example?Authorization=secret",
        "/home/gem/project.tar.gz",
        "/home/gem/.restore",
        "/home/gem/project",
        None,
    ) == {"restored": True, "fileCount": 2}
    command = requests[0]["command"]
    assert isinstance(command, str)
    assert 'while kill -0 "$restore_pid"' in command
    assert "[handoff] restore in progress" in command


def test_sanitize_remote_removes_embedded_credentials(upload_project) -> None:
    assert (
        upload_project.sanitize_remote(
            "https://user:token@github.com/example/demo.git?access_token=secret"
        )
        == "https://github.com/example/demo.git"
    )


def test_main_creates_temporary_session_restores_and_continues(
    upload_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "source"
    repo.mkdir()
    (repo / "app.py").write_text('print("hello")\n', encoding="utf-8")
    history = _history_file(tmp_path)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "add", "app.py")
    created_payloads: list[dict[str, object]] = []
    continuations: list[tuple[str, str, str, list[dict[str, str]], str]] = []
    cleanup_calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_post_json(url, payload, action, **kwargs):
        assert url == (
            "https://studio.example/web/sandbox/codex-project-handoff/sessions"
        )
        assert action == "Studio session creation"
        assert kwargs == {"attempts": upload_project.SESSION_CREATE_ATTEMPTS}
        created_payloads.append(payload)
        return {
            "sessionId": "remote-1",
            "displayName": "修复上传流程",
            "endpoint": "https://sandbox.example/path?Authorization=secret",
            "remoteRepoDir": "/home/gem/source",
        }

    monkeypatch.setattr(upload_project, "post_json", fake_post_json)
    monkeypatch.setattr(upload_project, "upload_file", lambda *_args: {})
    monkeypatch.setattr(
        upload_project,
        "remote_restore",
        lambda *_args: {
            "restored": True,
            "fileCount": 1,
            "gitStatus": "A  app.py",
            "githubAuth": False,
        },
    )
    monkeypatch.setattr(
        upload_project,
        "continue_in_studio",
        lambda studio_url,
        session_id,
        pairing_code,
        messages,
        message: continuations.append(
            (studio_url, session_id, pairing_code, messages, message)
        ),
    )
    monkeypatch.setattr(
        upload_project,
        "cleanup_remote_artifacts",
        lambda endpoint, paths: cleanup_calls.append((endpoint, tuple(paths))),
    )

    result = upload_project.main(
        [
            "--repo",
            str(repo),
            "--studio-url",
            "https://studio.example",
            "--pairing-code",
            "ABCD-EFGH",
            "--agent-name",
            "修复上传流程",
            "--history",
            str(history),
            "--yes",
        ]
    )

    assert result == 0
    assert len(created_payloads) == 1
    assert created_payloads[0]["pairingCode"] == "ABCD-EFGH"
    assert created_payloads[0]["projectName"] == "source"
    assert created_payloads[0]["agentName"] == "修复上传流程"
    assert created_payloads[0]["remoteHome"] == "/home/gem"
    assert isinstance(created_payloads[0]["handoffId"], str)
    assert len(created_payloads[0]["handoffId"]) == 32
    assert continuations == [
        (
            "https://studio.example",
            "remote-1",
            "ABCD-EFGH",
            [
                {"role": "user", "content": "修复登录超时"},
                {"role": "assistant", "content": "已定位重试逻辑。"},
            ],
            "继续",
        )
    ]
    assert cleanup_calls == []
