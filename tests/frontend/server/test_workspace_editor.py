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

import pytest

from frontend.server.workspace_editor import patch_editor, workspace_command


def template(root: Path) -> Path:
    path = root / "lib/vscode/out/vs/code/browser/workbench/workbench.html"
    path.parent.mkdir(parents=True)
    path.with_name("workbench.js").write_text(
        "function rewrite(i){let r=`path=${encodeURIComponent(i.path)}`;return r;}"
    )
    return path


def test_language_patch_preserves_module_order_and_is_idempotent(tmp_path):
    path = template(tmp_path)
    path.write_text(
        '<script src="fallback"></script><script type="module" src="{{WORKBENCH_NLS_URL}}"></script><script src="workbench"></script>'
    )
    patch_editor(tmp_path)
    result = path.read_text()
    assert (
        result.index("fallback")
        < result.index("studio-session-language-resource")
        < result.index('src="workbench"')
    )
    assert "url.origin === window.location.origin" in result
    patch_editor(tmp_path)
    assert path.read_text() == result
    assert "exec /opt/gem/run.sh" in workspace_command()
    assert "\n" not in workspace_command()


def test_unknown_editor_template_fails_without_changing_it(tmp_path):
    path = template(tmp_path)
    path.write_text("new unsupported template")
    with pytest.raises(ValueError, match="Unsupported"):
        patch_editor(tmp_path)
    assert path.read_text() == "new unsupported template"


def test_resource_urls_keep_routing_for_theme_and_grammar(tmp_path):
    import json
    import subprocess

    path = template(tmp_path)
    path.write_text('<script type="module" src="{{WORKBENCH_NLS_URL}}"></script>')
    patch_editor(tmp_path)
    source = path.with_name("workbench.js").read_text()
    script = (
        "globalThis.window={location:{search:'?Authorization=test%2Bkey&faasInstanceName=session-1&folder=ignored'}};"
        + source
        + "console.log(JSON.stringify(rewrite({path:'/themes/dark.json'})));"
    )
    query = json.loads(subprocess.check_output(["node", "-e", script], text=True))
    from urllib.parse import parse_qs

    assert parse_qs(query) == {
        "path": ["/themes/dark.json"],
        "Authorization": ["test+key"],
        "faasInstanceName": ["session-1"],
    }
    patch_editor(tmp_path)
    assert path.with_name("workbench.js").read_text() == source


def test_workbench_entry_is_signed_and_cache_busted(tmp_path):
    path = template(tmp_path)
    path.write_text(
        '<script type="module" src="{{WORKBENCH_NLS_URL}}"></script><script type="module" src="{{WORKBENCH_WEB_BASE_URL}}/out/vs/code/browser/workbench/workbench.js?studio-resource-version=2"></script>'
    )
    patch_editor(tmp_path)
    result = path.read_text()
    assert "studio-session-workbench-resource" in result
    assert "/workbench.js?studio-resource-version=3" in result
    assert result.index("studio-session-language-resource") < result.index(
        "studio-session-workbench-resource"
    )
    patch_editor(tmp_path)
    assert path.read_text() == result


def test_webview_worker_path_and_csp_remain_consistent(tmp_path):
    import base64
    import hashlib
    import re

    path = template(tmp_path)
    path.write_text('<script type="module" src="{{WORKBENCH_NLS_URL}}"></script>')
    webview = (
        tmp_path / "lib/vscode/out/vs/workbench/contrib/webview/browser/pre/index.html"
    )
    webview.parent.mkdir(parents=True)
    webview.write_text(
        '<meta content="script-src \'sha256-old=\'"><script async type="module">const swPath = encodeURI(`service-worker.js?v=${version}`); navigator.serviceWorker.register(swPath); currentController.scriptURL.endsWith(swPath)</script>'
    )
    patch_editor(tmp_path)
    content = webview.read_text()
    body = re.search(
        r'<script async type="module">(.*?)</script>', content, re.S
    ).group(1)
    digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
    assert "sha256-" + digest in content
    assert "swPath = workerUrl.href" in content
    assert "register(swPath)" in content
    assert "endsWith(swPath)" in content
    patch_editor(tmp_path)
    assert webview.read_text() == content
