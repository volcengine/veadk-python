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

"""Code-server font assets and first-start defaults shared by build and upgrades."""

import shutil
import json
import re
import zipfile
from pathlib import Path

FONT_MARKER = "/* studio-maple-mono */"
WORKBENCH = Path("lib/vscode/out/vs/code/browser/workbench")
FONTS = {
    "MapleMono-Regular.ttf.woff2": ("normal", 400),
    "MapleMono-Italic.ttf.woff2": ("italic", 400),
    "MapleMono-Bold.ttf.woff2": ("normal", 700),
    "MapleMono-BoldItalic.ttf.woff2": ("italic", 700),
}


def offline_vsix(source: Path, target: Path) -> None:
    """Remove optional extension-pack downloads, keeping code and required dependencies."""
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w") as output:
        for entry in original.infolist():
            data = original.read(entry.filename)
            if entry.filename == "extension/package.json":
                manifest = json.loads(data)
                if manifest.get("extensionPack"):
                    manifest["extensionPack"] = []
                    data = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
            elif entry.filename == "extension.vsixmanifest":
                data = re.sub(
                    rb'<Property\s+Id="Microsoft\.VisualStudio\.Code\.ExtensionPack"\s+Value="[^"]*"\s*/>',
                    b"",
                    data,
                )
            output.writestr(entry, data)


def apply_fonts(code_server: Path, fonts: Path) -> None:
    workbench = code_server / WORKBENCH
    stylesheet = workbench / "workbench.css"
    if not stylesheet.is_file():
        raise ValueError("Unsupported code-server layout: workbench.css is missing")
    content = stylesheet.read_text()
    if FONT_MARKER in content:
        content = content.split(FONT_MARKER, 1)[0].rstrip()
    target = workbench / "studio-fonts"
    target.mkdir(exist_ok=True)
    rules = []
    for filename, (style, weight) in FONTS.items():
        shutil.copyfile(fonts / filename, target / filename)
        rules.append(
            "@font-face{font-family:'Maple Mono';"
            f"src:url('./studio-fonts/{filename}') format('woff2');"
            f"font-style:{style};font-weight:{weight};font-display:swap;}}"
        )
    shutil.copyfile(fonts / "LICENSE.txt", target / "LICENSE.txt")
    stylesheet.write_text(content + "\n" + FONT_MARKER + "\n" + "\n".join(rules) + "\n")


def preserve_editor_settings(script: Path) -> None:
    old = "cp -rf /opt/gem/vscode /home/$USER/.config/code-server/vscode"
    new = f'if [ ! -d "/home/$USER/.config/code-server/vscode" ]; then\n  {old}\nfi'
    content = script.read_text()
    if new in content:
        return
    if content.splitlines().count(old) != 1:
        raise ValueError(
            "Base image changed: expected one editor settings seed command"
        )
    script.write_text(content.replace(old, new, 1))
