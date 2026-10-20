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

"""Seed the native language-pack cache for an offline code-server image."""

import hashlib
import json
from pathlib import Path

extensions = Path("/home/gem/.local/share/code-server/extensions")
target = Path("/home/gem/.config/code-server/vscode/languagepacks.json")
packs = {}
for folder in extensions.glob("ms-ceintl.vscode-language-pack-*"):
    manifest = json.loads((folder / "package.json").read_text())
    for locale in manifest.get("contributes", {}).get("localizations", []):
        translations = {
            item["id"]: str((folder / item["path"]).resolve(strict=True))
            for item in locale["translations"]
        }
        packs[locale["languageId"]] = {
            "hash": hashlib.sha256((folder / "package.json").read_bytes()).hexdigest(),
            "extensions": [
                {
                    "extensionIdentifier": {
                        "id": f"{manifest['publisher']}.{manifest['name']}".lower()
                    },
                    "version": manifest["version"],
                }
            ],
            "translations": translations,
            "label": locale.get("localizedLanguageName", locale["languageName"]),
        }
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(packs, ensure_ascii=False, indent=2) + "\n")
