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

"""Update editor assets in an existing Studio image during a Docker build."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from editor_routing import patch_editor

studio = Path("/opt/studio-sandbox")
editor = (studio / "base-code-server").resolve(strict=True).parent.parent
patch_editor(editor)
seed = Path("/opt/gem/vscode/User/settings.json")
settings = json.loads(seed.read_text())
settings.update(json.loads((studio / "settings.json").read_text()))
seed.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
user_data = Path("/home/gem/.config/code-server/vscode")
shutil.copyfile(seed, user_data / "User/settings.json")
extensions = Path("/home/gem/.local/share/code-server/extensions")
with tempfile.TemporaryDirectory(prefix="studio-welcome-") as temporary:
    package = Path(temporary) / "studio-welcome.vsix"
    subprocess.run(
        ["python3", str(studio / "runtime/package-welcome.py"), str(package)],
        check=True,
    )
    subprocess.run(
        [
            str(editor / "lib/node"),
            str(editor / "lib/vscode/out/server-main.js"),
            "--user-data-dir",
            str(user_data),
            "--extensions-dir",
            str(extensions),
            "--install-extension",
            str(package),
            "--do-not-include-pack-dependencies",
            "--force",
        ],
        check=True,
    )
for folder in (user_data, extensions):
    for path in (folder, *folder.rglob("*")):
        if not path.is_symlink():
            shutil.chown(path, user="gem", group="gem")
for name in (
    "code-server-wrapper",
    "studio-project-create",
    "studio-vscode-upgrade",
    "local-arm64-entrypoint",
):
    (studio / "runtime" / name).chmod(0o755)
