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

"""Apply Studio's first-start dashboard and Bash defaults."""

import re
from pathlib import Path

for target in (Path("/opt/aio/index.html"), Path("/opt/aio/index.html.template")):
    if not target.exists():
        continue
    content = target.read_text()
    for name in ("terminal", "vnc"):
        content = re.sub(
            rf"(\{{ id: '{name}'[^\n]*?)open: true",
            r"\1open: false",
            content,
        )
    content = content.replace(
        "url: '/code-server/', enabled: off(cfg.code_server) }",
        "url: '/code-server/', enabled: off(cfg.code_server), open: true }",
    )
    target.write_text(content)

snippet = """
# Studio Bash highlighting uses the upstream ble.sh runtime
if [[ $- == *i* ]] && [[ -f /opt/studio-sandbox/ble/share/blesh/ble.sh ]]; then
  source /opt/studio-sandbox/ble/share/blesh/ble.sh
fi
"""
for target in (Path("/opt/gem/bashrc"), Path("/home/gem/.bashrc")):
    content = target.read_text() if target.exists() else ""
    if "# Studio Bash highlighting" not in content:
        target.write_text(content + snippet)
