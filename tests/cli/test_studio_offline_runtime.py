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
import shutil
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from frontend.service.studio_release_server import offline_runtime


def _write_pure_python_wheel(path: Path, *, name: str, version: str) -> None:
    distribution = name.replace("-", "_")
    dist_info = f"{distribution}-{version}.dist-info"
    with ZipFile(path, "w", ZIP_DEFLATED) as wheel:
        wheel.writestr(f"{distribution}/__init__.py", "")
        wheel.writestr(
            f"{dist_info}/METADATA",
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        )
        wheel.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\n"
            "Generator: veadk-test\n"
            "Root-Is-Purelib: true\n"
            "Tag: py3-none-any\n",
        )
        wheel.writestr(f"{dist_info}/RECORD", "")


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


def test_build_offline_requirements_rejects_empty_wheelhouse(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="wheelhouse is empty"):
        offline_runtime.build_studio_offline_requirements(
            tmp_path,
            wheel_prefix="./wheelhouse/",
        )


def test_build_offline_requirements_rejects_duplicate_distribution(
    tmp_path: Path,
) -> None:
    (tmp_path / "example_pkg-1.0-py3-none-any.whl").write_bytes(b"one")
    (tmp_path / "example_pkg-2.0-py3-none-any.whl").write_bytes(b"two")

    with pytest.raises(ValueError, match="duplicate distributions"):
        offline_runtime.build_studio_offline_requirements(
            tmp_path,
            wheel_prefix="./wheelhouse/",
        )


@pytest.mark.parametrize(
    "wheel_prefix",
    (
        "wheelhouse/",
        "../wheelhouse/",
        "./../wheelhouse/",
        "./wheelhouse/\n--index-url https://example.invalid/",
        "./wheelhouse/\r--index-url https://example.invalid/",
    ),
)
def test_build_offline_requirements_rejects_unsafe_prefix(
    tmp_path: Path,
    wheel_prefix: str,
) -> None:
    (tmp_path / "example_pkg-1.0-py3-none-any.whl").write_bytes(b"wheel")

    with pytest.raises(ValueError, match="wheel prefix is invalid"):
        offline_runtime.build_studio_offline_requirements(
            tmp_path,
            wheel_prefix=wheel_prefix,
        )


def test_build_offline_runtime_creates_local_only_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_run = subprocess.run
    uv = shutil.which("uv")
    assert uv is not None
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "uv.lock").write_text("lock", encoding="utf-8")
    package_dir = tmp_path / "package"
    veadk_wheel = tmp_path / "veadk_python-1.0-py3-none-any.whl"
    _write_pure_python_wheel(veadk_wheel, name="veadk-python", version="1.0")
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
            _write_pure_python_wheel(
                output / "tos-1.0-py3-none-any.whl",
                name="tos",
                version="1.0",
            )
        elif "download" in command:
            output = Path(command[command.index("--dest") + 1])
            _write_pure_python_wheel(
                output / "dependency-1-py3-none-any.whl",
                name="dependency",
                version="1",
            )
            _write_pure_python_wheel(
                output / "linux_only-2-py3-none-any.whl",
                name="linux-only",
                version="2",
            )
            _write_pure_python_wheel(
                output / "tos-1-py3-none-any.whl",
                name="tos",
                version="1",
            )
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

    staged_veadk = package_dir / "wheelhouse" / veadk_wheel.name
    expected_wheels = sorted((package_dir / "wheelhouse").glob("*.whl"))
    assert requirements == "--no-index\n--require-hashes\n" + "".join(
        f"./wheelhouse/{wheel.name} --hash=sha256:{offline_runtime._sha256(wheel)}\n"
        for wheel in expected_wheels
    )
    assert "--find-links" not in requirements
    assert "-r " not in requirements
    runtime_lock = (package_dir / "studio-runtime.lock").read_text(encoding="utf-8")
    assert runtime_lock.count("--hash=sha256:") == 3
    assert "dependency==1 --hash=sha256:" in runtime_lock
    assert "linux-only==2 --hash=sha256:" in runtime_lock
    assert "tos==1 --hash=sha256:" in runtime_lock
    assert staged_veadk.is_file()
    assert commands[0][1:] == ["lock", "--check"]
    download = next(command for command in commands if "download" in command)
    assert "--only-binary=:all:" in download
    assert "manylinux_2_17_x86_64" in download
    assert "--no-index" not in download
    verification = commands[-1]
    assert verification[1:3] == ["pip", "install"]
    assert verification[-2:] == ["--requirements", "-"]

    platform_parse = original_run(
        [
            uv,
            "pip",
            "install",
            "--dry-run",
            "--no-deps",
            "--no-python-downloads",
            "--target",
            str(tmp_path / "platform-target"),
            "--requirements",
            "-",
        ],
        cwd=package_dir,
        input=requirements,
        text=True,
        capture_output=True,
        check=False,
    )
    assert platform_parse.returncode == 0, platform_parse.stderr


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
