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

from pathlib import Path
import subprocess

import pytest

from frontend.service.studio_release_server import offline_runtime


def test_lock_check_environment_uses_canonical_pypi() -> None:
    environment = offline_runtime._lock_check_environment(
        {
            "PATH": "/usr/bin",
            "UV_DEFAULT_INDEX": "https://mirror.invalid/simple",
            "UV_INDEX": "private=https://mirror.invalid/simple",
            "UV_INDEX_URL": "https://legacy.invalid/simple",
            "UV_EXTRA_INDEX_URL": "https://extra.invalid/simple",
            "PIP_INDEX_URL": "https://pip.invalid/simple",
            "PIP_EXTRA_INDEX_URL": "https://pip-extra.invalid/simple",
        }
    )

    assert environment == {
        "PATH": "/usr/bin",
        "UV_DEFAULT_INDEX": "https://pypi.org/simple",
    }


def test_linux_runtime_lock_uses_target_markers(tmp_path: Path) -> None:
    exported = tmp_path / "exported.txt"
    exported.write_text(
        "common==1\n"
        "linux-only==2 ; sys_platform == 'linux' and platform_machine == 'x86_64'\n"
        "mac-only==3 ; sys_platform == 'darwin'\n"
        "old-python==4 ; python_version < '3.12'\n",
        encoding="utf-8",
    )
    target = tmp_path / "target.txt"

    offline_runtime._write_linux_runtime_lock(exported, target)

    assert target.read_text(encoding="utf-8") == ("common==1\nlinux-only==2\n")


def test_build_offline_runtime_requires_committed_lock(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    veadk_wheel = tmp_path / "veadk_python-1.0-py3-none-any.whl"
    veadk_wheel.write_bytes(b"veadk")

    with pytest.raises(ValueError, match="requires uv.lock"):
        offline_runtime.build_studio_offline_runtime(
            source_root,
            tmp_path / "package",
            veadk_wheel=veadk_wheel,
            dependency_sources=(),
            environment={"PATH": ""},
        )


def test_build_offline_runtime_rejects_stale_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "uv.lock").write_text("stale", encoding="utf-8")
    veadk_wheel = tmp_path / "veadk_python-1.0-py3-none-any.whl"
    veadk_wheel.write_bytes(b"veadk")
    monkeypatch.setattr(
        offline_runtime.shutil, "which", lambda *_args, **_kwargs: "/usr/bin/uv"
    )

    def reject_lock(command: list[str], **_kwargs: object) -> None:
        assert command[1:] == ["lock", "--check"]
        raise subprocess.CalledProcessError(2, command)

    monkeypatch.setattr(offline_runtime.subprocess, "run", reject_lock)

    with pytest.raises(ValueError, match="Studio runtime lock is stale"):
        offline_runtime.build_studio_offline_runtime(
            source_root,
            tmp_path / "package",
            veadk_wheel=veadk_wheel,
            dependency_sources=(),
            environment={"PATH": "/usr/bin"},
        )
    assert not (tmp_path / "package").exists()


def test_build_offline_runtime_creates_local_only_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "uv.lock").write_text("lock", encoding="utf-8")
    package_dir = tmp_path / "package"
    veadk_wheel = tmp_path / "veadk_python-1.0-py3-none-any.whl"
    veadk_wheel.write_bytes(b"veadk")
    source_archive = tmp_path / "tos-1.0.tar.gz"
    source_archive.write_bytes(b"source")
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        commands.append(command)
        if command[1] == "export":
            output = Path(command[command.index("--output-file") + 1])
            output.write_text(
                "dependency==1\nlinux-only==2 ; sys_platform == 'linux'\ntos==1\n",
                encoding="utf-8",
            )
        elif "wheel" in command:
            output = Path(command[command.index("--wheel-dir") + 1])
            (output / "tos-1.0-py3-none-any.whl").write_bytes(b"pure")
        elif "download" in command:
            output = Path(command[command.index("--dest") + 1])
            (output / "dependency-1-py3-none-any.whl").write_bytes(b"wheel")
            (output / "linux_only-2-py3-none-any.whl").write_bytes(b"wheel")
            (output / "tos-1-py3-none-any.whl").write_bytes(b"pure")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        offline_runtime.shutil, "which", lambda *_args, **_kwargs: "/usr/bin/uv"
    )
    monkeypatch.setattr(offline_runtime.subprocess, "run", fake_run)

    requirements = offline_runtime.build_studio_offline_runtime(
        source_root,
        package_dir,
        veadk_wheel=veadk_wheel,
        dependency_sources=(source_archive,),
        environment={"PATH": "/usr/bin"},
    )

    assert requirements == (
        "--no-index\n"
        "--find-links ./wheelhouse\n"
        "--require-hashes\n"
        "-r ./studio-runtime.lock\n"
        "./wheelhouse/veadk_python-1.0-py3-none-any.whl "
        "--hash=sha256:62ee185cf74a591e7d1b3d2dbe3f389f92c893966e2fd39a3b92c19fc7fcd9c1\n"
    )
    runtime_lock = (package_dir / "studio-runtime.lock").read_text(encoding="utf-8")
    assert runtime_lock.count("--hash=sha256:") == 3
    assert "dependency==1 --hash=sha256:" in runtime_lock
    assert "linux-only==2 --hash=sha256:" in runtime_lock
    assert "tos==1 --hash=sha256:" in runtime_lock
    assert (package_dir / "wheelhouse" / veadk_wheel.name).read_bytes() == b"veadk"
    assert commands[0][1:] == ["lock", "--check"]
    download = next(command for command in commands if "download" in command)
    assert "--only-binary=:all:" in download
    assert "manylinux_2_17_x86_64" in download
    assert "--no-index" not in download
    verification = [command for command in commands if "download" in command][-1]
    assert "--no-index" in verification


def test_build_offline_runtime_rejects_native_source_wheel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "uv.lock").write_text("lock", encoding="utf-8")
    veadk_wheel = tmp_path / "veadk_python-1.0-py3-none-any.whl"
    veadk_wheel.write_bytes(b"veadk")
    source_archive = tmp_path / "crcmod-1.0.tar.gz"
    source_archive.write_bytes(b"source")

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        if command[1] == "export":
            output = Path(command[command.index("--output-file") + 1])
            output.write_text("crcmod==1\n", encoding="utf-8")
        elif "wheel" in command:
            output = Path(command[command.index("--wheel-dir") + 1])
            (output / "crcmod-1-cp312-cp312-linux_x86_64.whl").write_bytes(b"native")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(
        offline_runtime.shutil, "which", lambda *_args, **_kwargs: "/usr/bin/uv"
    )
    monkeypatch.setattr(offline_runtime.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="portable wheels"):
        offline_runtime.build_studio_offline_runtime(
            source_root,
            tmp_path / "package",
            veadk_wheel=veadk_wheel,
            dependency_sources=(source_archive,),
            environment={"PATH": "/usr/bin"},
        )
