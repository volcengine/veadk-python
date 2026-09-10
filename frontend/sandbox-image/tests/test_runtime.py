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

import json
import runpy
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE / "runtime"))

from editor_assets import (  # noqa: E402
    FONT_MARKER,
    FONTS,
    WORKBENCH,
    apply_fonts,
    offline_vsix,
    preserve_editor_settings,
)

create_project = runpy.run_path(str(SOURCE / "runtime/studio-project-create"))[
    "create_project"
]
upgrade = runpy.run_path(str(SOURCE / "runtime/studio-vscode-upgrade"))


class StudioImageTest(unittest.TestCase):
    def test_offline_vsix_does_not_pull_optional_extension_packs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source, target = (
                Path(temporary) / "source.vsix",
                Path(temporary) / "local.vsix",
            )
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(
                    "extension/package.json",
                    json.dumps(
                        {
                            "extensionPack": ["ms-python.vscode-pylance"],
                            "extensionDependencies": ["required.extension"],
                        }
                    ),
                )
                archive.writestr("extension/code.js", "original code")
                archive.writestr(
                    "extension.vsixmanifest",
                    '<Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value="ms-python.vscode-pylance"/>',
                )
            offline_vsix(source, target)
            with zipfile.ZipFile(target) as archive:
                manifest = json.loads(archive.read("extension/package.json"))
                self.assertEqual(manifest["extensionPack"], [])
                self.assertEqual(
                    manifest["extensionDependencies"], ["required.extension"]
                )
                self.assertEqual(archive.read("extension/code.js"), b"original code")
                self.assertNotIn(
                    b"vscode-pylance", archive.read("extension.vsixmanifest")
                )

    def test_font_patch_is_local_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fonts = root / "fonts"
            fonts.mkdir()
            for filename in (*FONTS, "LICENSE.txt"):
                (fonts / filename).write_text("fixture")
            css = root / "code" / WORKBENCH / "workbench.css"
            css.parent.mkdir(parents=True)
            css.write_text(".editor { color: inherit; }\n")
            apply_fonts(root / "code", fonts)
            apply_fonts(root / "code", fonts)
            content = css.read_text()
            self.assertEqual(content.count(FONT_MARKER), 1)
            self.assertEqual(content.count("@font-face"), 4)
            self.assertNotIn("https://", content)
            self.assertIn("font-display:swap", content)

    def test_settings_seed_preserves_existing_user_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / "gem.sh"
            script.write_text(
                "before\ncp -rf /opt/gem/vscode /home/$USER/.config/code-server/vscode\nafter\n"
            )
            preserve_editor_settings(script)
            once = script.read_text()
            preserve_editor_settings(script)
            self.assertEqual(script.read_text(), once)
            self.assertIn(
                'if [ ! -d "/home/$USER/.config/code-server/vscode" ]; then', once
            )
            self.assertTrue(once.startswith("before\n"))
            self.assertTrue(once.endswith("after\n"))

    def test_unexpected_base_script_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / "gem.sh"
            script.write_text("changed upstream script")
            with self.assertRaises(ValueError):
                preserve_editor_settings(script)
            self.assertEqual(script.read_text(), "changed upstream script")

    def test_project_creation_seeds_git_project_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def simulate_uv(command: list[str], **_: object) -> None:
                if command[1] == "venv":
                    (Path(command[-1]) / "bin").mkdir(parents=True)

            with patch("subprocess.run", side_effect=simulate_uv) as run:
                project = create_project("my-agent", root, root / "studio")
            self.assertEqual(
                {path.name for path in project.iterdir()},
                {"main.py", ".venv", ".gitignore", "AGENTS.md", "README.md"},
            )
            self.assertIn('name="my_agent"', (project / "main.py").read_text())
            for call in run.call_args_list[:2]:
                self.assertIn("--offline", call.args[0])
            self.assertIn("copy", run.call_args_list[1].args[0])

    def test_project_rejects_traversal_and_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("../escape", "/tmp/escape", "a/b", ".", "-agent", "a\nagent"):
                with self.assertRaises(ValueError):
                    create_project(name, root, root / "studio")
            existing = root / "existing"
            existing.mkdir()
            (existing / "main.py").write_text("keep me")
            with self.assertRaises(FileExistsError):
                create_project("existing", root, root / "studio")
            self.assertEqual((existing / "main.py").read_text(), "keep me")

    def test_upgrade_switch_keeps_previous_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = root / "first", root / "second"
            first.mkdir()
            second.mkdir()
            (root / "current").symlink_to(first)
            upgrade["activate"](root, second)
            self.assertEqual((root / "current").resolve(), second.resolve())
            self.assertEqual((root / "previous").resolve(), first.resolve())

    def test_upgrade_rejects_insecure_download_urls(self) -> None:
        for url in (
            "http://example.com/archive",
            "file:///tmp/archive",
            "https://user:password@example.com/archive",
        ):
            with self.assertRaises(ValueError):
                upgrade["https_url"](url)

    def test_editor_defaults_cover_python_and_only_editor_fonts(self) -> None:
        settings = json.loads((SOURCE / "settings.json").read_text())
        self.assertEqual(settings["files.associations"]["*.py"], "python")
        self.assertEqual(
            settings["python.defaultInterpreterPath"],
            "${workspaceFolder}/.venv/bin/python",
        )
        self.assertEqual(settings["workbench.colorTheme"], "Default Dark Modern")
        self.assertEqual(settings["editor.fontFamily"], "'Maple Mono', monospace")
        self.assertNotIn("window.fontFamily", settings)


if __name__ == "__main__":
    unittest.main()
