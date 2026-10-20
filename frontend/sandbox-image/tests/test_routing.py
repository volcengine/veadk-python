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

import base64
import hashlib
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
from editor_routing import patch_editor


class EditorRoutingTest(unittest.TestCase):
    def test_cloud_resources_and_webview_keep_routing_after_repeated_patch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workbench = root / "lib/vscode/out/vs/code/browser/workbench"
            workbench.mkdir(parents=True)
            template = workbench / "workbench.html"
            template.write_text("""<head>
<link rel="stylesheet" href="{{WORKBENCH_WEB_BASE_URL}}/out/vs/code/browser/workbench/workbench.css">
</head>
<script type="module" src="{{WORKBENCH_NLS_FALLBACK_URL}}"></script>
<script type="module" src="{{WORKBENCH_NLS_URL}}"></script>
<script type="module" src="{{WORKBENCH_WEB_BASE_URL}}/out/vs/code/browser/workbench/workbench.js"></script>""")
            bundle = workbench / "workbench.js"
            bundle.write_text(
                "let r=`path=${encodeURIComponent(i.path)}`;return result"
            )
            webview = (
                root
                / "lib/vscode/out/vs/workbench/contrib/webview/browser/pre/index.html"
            )
            webview.parent.mkdir(parents=True)
            webview.write_text("""<meta content="script-src 'sha256-oldhash'">
<script async type="module">const swPath = encodeURI(`service-worker.js`);
navigator.serviceWorker.register(swPath);</script>""")
            patch_editor(root)
            first = [path.read_text() for path in (template, bundle, webview)]
            patch_editor(root)
            self.assertEqual(
                first, [path.read_text() for path in (template, bundle, webview)]
            )
            for resource in ("language", "fallback", "workbench", "style", "font"):
                self.assertIn(f"studio-session-{resource}-resource", first[0])
            self.assertIn("routing.get(key)", first[1])
            self.assertIn("swPath = workerUrl.href", first[2])
            match = re.search(
                r'<script async type="module">(.*?)</script>', first[2], re.S
            )
            assert match is not None
            body = match.group(1)
            digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
            self.assertIn(f"sha256-{digest}", first[2])

    def test_unknown_editor_layout_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "lib/vscode/out/vs/code/browser/workbench/workbench.html"
            template.parent.mkdir(parents=True)
            template.write_text("unknown release")
            with self.assertRaises(ValueError):
                patch_editor(root)
            self.assertEqual(template.read_text(), "unknown release")


if __name__ == "__main__":
    unittest.main()
