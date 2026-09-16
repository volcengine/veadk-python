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

"""Build-time installation only; the original sandbox entrypoint remains intact."""

import hashlib
import json
import os
import pwd
import shutil
import subprocess
import tempfile
import tarfile
import zipfile
from pathlib import Path

from editor_assets import FONTS, apply_fonts, offline_vsix, preserve_editor_settings
from editor_routing import patch_editor

STUDIO = Path("/opt/studio-sandbox")


def run(*command: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, check=True, env=env)


def main() -> None:
    if os.geteuid() != 0:
        raise RuntimeError("Image setup must run as root during the image build")
    try:
        account = pwd.getpwnam("gem")
    except KeyError:
        # The base entrypoint normally creates this account on first startup
        run("groupadd", "--gid", "1000", "gem")
        run(
            "useradd",
            "--uid",
            "1000",
            "--gid",
            "1000",
            "--shell",
            "/bin/bash",
            "--no-create-home",
            "gem",
        )
        account = pwd.getpwnam("gem")
    home = Path(account.pw_dir)
    binary = Path("/usr/bin/code-server")
    base_binary = binary.resolve(strict=True)
    code_server = base_binary.parent.parent
    if not binary.is_symlink() or base_binary.name != "code-server":
        raise RuntimeError(
            "Base image changed: /usr/bin/code-server must be the original symlink"
        )
    for asset in json.loads((STUDIO / "assets.lock.json").read_text()):
        with (STUDIO / "assets" / asset["file"]).open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != asset["sha256"]:
            raise ValueError(f"Asset checksum mismatch: {asset['file']}")

    fonts = STUDIO / "fonts"
    fonts.mkdir()
    with zipfile.ZipFile(STUDIO / "assets" / "MapleMono-Woff2.zip") as archive:
        for filename in (*FONTS, "LICENSE.txt"):
            (fonts / filename).write_bytes(archive.read(filename))
    apply_fonts(code_server, fonts)
    patch_editor(code_server)
    builtin_python = (
        code_server
        / "lib/vscode/extensions/python/syntaxes/MagicPython.tmLanguage.json"
    )
    if not builtin_python.is_file():
        raise RuntimeError("Base image is missing Python syntax highlighting")

    seed = Path("/opt/gem/vscode/User/settings.json")
    defaults = json.loads(seed.read_text()) if seed.exists() else {}
    defaults.update(json.loads((STUDIO / "settings.json").read_text()))
    seed.parent.mkdir(parents=True, exist_ok=True)
    seed.write_text(json.dumps(defaults, ensure_ascii=False, indent=2) + "\n")
    preserve_editor_settings(Path("/opt/gem/gem.sh"))

    user_data = home / ".config/code-server/vscode"
    user_data.mkdir(parents=True, exist_ok=True)
    shutil.copytree(seed.parent.parent, user_data, dirs_exist_ok=True)
    extensions = home / ".local/share/code-server/extensions"
    extensions.mkdir(parents=True, exist_ok=True)
    # Install dependency extensions before dependents, using only pinned local VSIX files
    assets = json.loads((STUDIO / "assets.lock.json").read_text())
    for asset in assets:
        if asset["file"].endswith(".vsix"):
            with tempfile.TemporaryDirectory(prefix="studio-vsix-") as temporary:
                local = Path(temporary) / asset["file"]
                offline_vsix(STUDIO / "assets" / asset["file"], local)
                run(
                    str(code_server / "lib/node"),
                    str(code_server / "lib/vscode/out/server-main.js"),
                    "--user-data-dir",
                    str(user_data),
                    "--extensions-dir",
                    str(extensions),
                    "--install-extension",
                    str(local),
                    "--do-not-include-pack-dependencies",
                    "--force",
                )

    with tempfile.TemporaryDirectory(prefix="studio-welcome-") as temporary:
        welcome = Path(temporary) / "studio-welcome.vsix"
        run(
            "/opt/agentkit-code-env/venv/bin/python",
            str(STUDIO / "runtime/package-welcome.py"),
            str(welcome),
        )
        run(
            str(code_server / "lib/node"),
            str(code_server / "lib/vscode/out/server-main.js"),
            "--user-data-dir",
            str(user_data),
            "--extensions-dir",
            str(extensions),
            "--install-extension",
            str(welcome),
            "--do-not-include-pack-dependencies",
            "--force",
        )
    run(
        "/opt/agentkit-code-env/venv/bin/python",
        str(STUDIO / "runtime/register-language.py"),
    )

    with tempfile.TemporaryDirectory(prefix="studio-blesh-") as temporary:
        with tarfile.open(STUDIO / "assets/blesh-0.4.0-devel3.tar.xz") as archive:
            archive.extractall(temporary, filter="data")
        source = next(Path(temporary).iterdir())
        shutil.copytree(source, STUDIO / "ble/share/blesh", dirs_exist_ok=True)
    run(
        "/opt/agentkit-code-env/venv/bin/python",
        str(STUDIO / "runtime/configure-runtime.py"),
    )

    uv = Path("/opt/agentkit-code-env/venv/bin/uv")
    if not uv.is_file():
        raise RuntimeError("Base image is missing uv")
    uv_link = Path("/usr/local/bin/uv")
    if not uv_link.exists():
        uv_link.symlink_to(uv)
    environment = dict(os.environ, UV_CACHE_DIR=str(STUDIO / "uv-cache"))
    run(
        str(uv),
        "venv",
        "--python",
        "/opt/agentkit-code-env/venv/bin/python",
        str(STUDIO / "venv"),
        env=environment,
    )
    run(
        str(uv),
        "pip",
        "sync",
        "--python",
        str(STUDIO / "venv/bin/python"),
        "--link-mode",
        "copy",
        str(STUDIO / "requirements.lock"),
        env=environment,
    )
    run(
        str(STUDIO / "venv/bin/python"),
        "-c",
        "from veadk import Agent; from agentkit.toolkit.cli.cli import app",
    )
    for name in ("agentkit", "veadk"):
        link = Path("/usr/local/bin") / name
        if link.exists() or link.is_symlink():
            expected = Path("/opt/agentkit-code-env/venv/bin") / name
            if not link.is_symlink() or link.readlink() != expected:
                raise RuntimeError(
                    f"Base image changed the {name} entrypoint; inspect before replacing it"
                )
            link.unlink()
        link.symlink_to(STUDIO / "venv/bin" / name)
    for name in ("studio-project-create", "studio-vscode-upgrade"):
        script = STUDIO / "runtime" / name
        script.chmod(0o755)
        (Path("/usr/local/bin") / name).symlink_to(script)
    wrapper = STUDIO / "runtime/code-server-wrapper"
    wrapper.chmod(0o755)
    (STUDIO / "base-code-server").symlink_to(base_binary)
    binary.unlink()
    binary.symlink_to(wrapper)

    with tarfile.open(STUDIO / "assets/codex-0.139.0-linux-arm64.tgz") as archive:
        member = archive.getmember(
            "package/vendor/aarch64-unknown-linux-musl/bin/codex"
        )
        source = archive.extractfile(member)
        if source is None:
            raise ValueError("Local ARM64 archive is missing the executable")
        with source:
            native = Path("/usr/local/libexec/codex-arm64-local")
            native.write_bytes(source.read())
            native.chmod(0o755)

    (home / "Projects").mkdir(exist_ok=True)
    (home / ".local/share/studio-code-server").mkdir(exist_ok=True)
    for folder in (
        home / ".config",
        home / ".config/code-server",
        home / ".local",
        home / ".local/share",
        home / ".local/share/code-server",
    ):
        shutil.chown(folder, user=account.pw_uid, group=account.pw_gid)
    for folder in (
        user_data,
        extensions,
        home / "Projects",
        home / ".local/share/studio-code-server",
        STUDIO / "uv-cache",
    ):
        shutil.chown(folder, user=account.pw_uid, group=account.pw_gid)
        for path in folder.rglob("*"):
            if not path.is_symlink():
                shutil.chown(path, user=account.pw_uid, group=account.pw_gid)
    # Verify the complete project environment can be recreated without any network access
    run(
        "runuser",
        "-u",
        "gem",
        "--",
        "/usr/local/bin/studio-project-create",
        "StudioBuildCheck",
        "--json",
    )
    check_project = home / "Projects/StudioBuildCheck"
    run(
        str(check_project / ".venv/bin/python"),
        "-c",
        "from veadk import Agent; import agentkit",
    )
    shutil.rmtree(check_project)
    shutil.rmtree(STUDIO / "assets")


if __name__ == "__main__":
    main()
