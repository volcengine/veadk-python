"""Exercise the public build and installed-package delivery boundaries."""

import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_image_builder_defaults_to_local_build_without_adjacent_sdk(tmp_path):
    commands = tmp_path / "commands"
    executable = tmp_path / "docker"
    executable.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$BUILD_TEST_COMMANDS"\n')
    executable.chmod(0o755)
    env = dict(os.environ, BUILD_TEST_COMMANDS=str(commands))
    env["PATH"] = str(tmp_path) + os.pathsep + env["PATH"]
    result = subprocess.run(
        ["bash", str(ROOT / "docker/managed-agents/build.sh"), "test-worker:local"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    command = commands.read_text()
    assert "--load" in command
    assert "--push" not in command
    assert "Dockerfile.worker" in command
    assert "test-worker:local" in command
    assert "SDK" not in result.stdout + result.stderr


def test_image_builder_keeps_explicit_indexes_and_publication_choice(tmp_path):
    commands = tmp_path / "commands"
    executable = tmp_path / "docker"
    executable.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$BUILD_TEST_COMMANDS"\n')
    executable.chmod(0o755)
    env = dict(
        os.environ,
        BUILD_TEST_COMMANDS=str(commands),
        PIP_INDEX_URL="https://packages.example.com/simple",
        UV_DEFAULT_INDEX="https://uv.example.com/simple",
    )
    env["PATH"] = str(tmp_path) + os.pathsep + env["PATH"]
    subprocess.run(
        [
            "bash",
            str(ROOT / "docker/managed-agents/build.sh"),
            "test-worker:local",
            "--push",
        ],
        env=env,
        check=True,
        capture_output=True,
    )
    command = commands.read_text()
    assert "--push" in command
    assert "--load" not in command
    assert "PIP_INDEX_URL=https://packages.example.com/simple" in command
    assert "UV_DEFAULT_INDEX=https://uv.example.com/simple" in command


def test_worker_build_context_excludes_ui_credentials_and_local_evidence():
    context = (
        ROOT / "docker/managed-agents/Dockerfile.worker.dockerignore"
    ).read_text()
    assert "**/.env" in context
    assert "frontend" in context
    assert "veadk/webui" in context
    assert "deploy_records" in context
    source = (ROOT / "docker/managed-agents/Dockerfile.worker").read_text()
    assert "--require-hashes" in source
    assert ".docker-dist" not in source
    assert "anthropic-*.whl" not in source
    assert "veadk.runtime.managed_agents" in source


@pytest.mark.parametrize(
    "index",
    [
        "https://user:private-test-marker@packages.example.com/simple",
        "https://packages.example.com/simple?token=private-test-marker",
        "https://packages.example.com/simple#private-test-marker",
    ],
)
def test_image_builder_rejects_credentials_before_invoking_docker(tmp_path, index):
    commands = tmp_path / "commands"
    executable = tmp_path / "docker"
    executable.write_text('#!/bin/sh\nprintf called > "$BUILD_TEST_COMMANDS"\n')
    executable.chmod(0o755)
    env = dict(
        os.environ,
        BUILD_TEST_COMMANDS=str(commands),
        PIP_INDEX_URL=index,
        UV_DEFAULT_INDEX="https://pypi.org/simple",
    )
    env["PATH"] = str(tmp_path) + os.pathsep + env["PATH"]
    result = subprocess.run(
        ["bash", str(ROOT / "docker/managed-agents/build.sh"), "test-worker:local"],
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert not commands.exists()
    assert "private-test-marker" not in result.stdout + result.stderr
