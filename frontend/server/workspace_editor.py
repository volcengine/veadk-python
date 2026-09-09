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

"""Keep language-pack requests on the same authenticated cloud session."""

import base64
import inspect
import hashlib
import re
import shlex
import zlib
from pathlib import Path

_NLS_TAG = '<script type="module" src="{{WORKBENCH_NLS_URL}}"></script>'
_ROUTED_NLS = r"""<script>
// studio-session-language-resource
(() => {
  const source = "{{WORKBENCH_NLS_URL}}";
  if (!source) return;
  const url = new URL(source, window.location.href);
  if (url.origin === window.location.origin) {
    for (const [key, value] of new URLSearchParams(window.location.search)) {
      if (key !== "folder" && !url.searchParams.has(key)) url.searchParams.append(key, value);
    }
  }
  // Parser insertion preserves module order: fallback, translation, workbench.
  const escaped = url.href.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
  document.write('<script type="module" src="' + escaped + '"><\/script>');
})();
</script>"""


_RESOURCE_QUERY = "let r=`path=${encodeURIComponent(i.path)}`;return"
_ROUTED_QUERY = r"""let r=`path=${encodeURIComponent(i.path)}`;
/* studio-session-editor-resource */
if(typeof window!=="undefined"){
 const routing=new URLSearchParams(window.location.search);
 for(const key of ["Authorization","faasInstanceName"]){
  const value=routing.get(key);
  if(value!==null)r+="&"+encodeURIComponent(key)+"="+encodeURIComponent(value);
 }
}
return"""


def patch_editor(root: Path) -> None:
    template = root / "lib/vscode/out/vs/code/browser/workbench/workbench.html"
    source = template.read_text()
    if "studio-session-language-resource" not in source:
        if source.count(_NLS_TAG) != 1:
            raise ValueError("Unsupported editor language-resource template")
        template.write_text(source.replace(_NLS_TAG, _ROUTED_NLS))
    refreshed = template.read_text()
    fallback = '<script type="module" src="{{WORKBENCH_NLS_FALLBACK_URL}}"></script>'
    refreshed = refreshed.replace(
        fallback,
        _ROUTED_NLS.replace(
            "studio-session-language-resource", "studio-session-fallback-resource"
        ).replace("{{WORKBENCH_NLS_URL}}", "{{WORKBENCH_NLS_FALLBACK_URL}}"),
    )
    if "studio-session-workbench-resource" not in refreshed:
        pattern = r'<script type="module" src="([^"<>]*/workbench\.js)(?:\?[^"<>]*)?"></script>'

        def route_workbench(match):
            return _ROUTED_NLS.replace(
                "studio-session-language-resource", "studio-session-workbench-resource"
            ).replace(
                "{{WORKBENCH_NLS_URL}}", match.group(1) + "?studio-resource-version=3"
            )

        refreshed = re.sub(pattern, route_workbench, refreshed)
    css_tag = '<link rel="stylesheet" href="{{WORKBENCH_WEB_BASE_URL}}/out/vs/code/browser/workbench/workbench.css">'
    css_loader = _ROUTED_NLS.replace(
        "studio-session-language-resource", "studio-session-style-resource"
    ).replace(
        "{{WORKBENCH_NLS_URL}}",
        "{{WORKBENCH_WEB_BASE_URL}}/out/vs/code/browser/workbench/workbench.css",
    )
    css_loader = css_loader.replace(
        "'<script type=\"module\" src=\"' + escaped + '\"><\\/script>'",
        "'<link rel=\"stylesheet\" href=\"' + escaped + '\">'",
    )
    refreshed = refreshed.replace(css_tag, css_loader)
    template.write_text(refreshed)
    webview = (
        root / "lib/vscode/out/vs/workbench/contrib/webview/browser/pre/index.html"
    )
    if webview.exists():
        content = webview.read_text()
        marker = "navigator.serviceWorker.register(swPath)"
        routed = """navigator.serviceWorker.register((() => {
            // studio-session-webview-worker
            const url = new URL(swPath, window.location.href);
            for (const key of ["Authorization", "faasInstanceName"]) {
                const value = searchParams.get(key);
                if (value !== null) url.searchParams.set(key, value);
            }
            return url.href;
        })())"""
        content = content.replace(routed, marker)
        if "studio-session-webview-path" not in content:
            pattern = r"(const swPath = encodeURI\(`[^`]+`\);)"

            def route_worker(match):
                return (
                    match.group(1).replace("const swPath", "let swPath")
                    + """
            // studio-session-webview-path
            const workerUrl = new URL(swPath, window.location.href);
            for (const key of ["Authorization", "faasInstanceName"]) {
                const value = searchParams.get(key);
                if (value !== null) workerUrl.searchParams.set(key, value);
            }
            swPath = workerUrl.href;
"""
                )

            content = re.sub(pattern, route_worker, content)

        body = re.search(r'<script async type="module">(.*?)</script>', content, re.S)
        if body and "studio-session-webview-path" in body.group(1):
            digest = base64.b64encode(
                hashlib.sha256(body.group(1).encode()).digest()
            ).decode()
            content = re.sub(
                r"sha256-[A-Za-z0-9+/=]+", "sha256-" + digest, content, count=1
            )
        webview.write_text(content)
    bundle = template.with_name("workbench.js")
    script = bundle.read_text()
    if "studio-session-editor-resource" not in script:
        if script.count(_RESOURCE_QUERY) != 1:
            raise ValueError("Unsupported editor resource URL builder")
        bundle.write_text(script.replace(_RESOURCE_QUERY, _ROUTED_QUERY))


def bootstrap_source() -> str:
    """Run before the native entrypoint drops to the restricted user."""
    return (
        "from pathlib import Path\nimport re, base64, hashlib\n"
        + f"_NLS_TAG = {_NLS_TAG!r}\n_ROUTED_NLS = {_ROUTED_NLS!r}\n"
        + f"_RESOURCE_QUERY = {_RESOURCE_QUERY!r}\n_ROUTED_QUERY = {_ROUTED_QUERY!r}\n"
        + inspect.getsource(patch_editor)
        + "\npatch_editor(Path('/opt/studio-sandbox/base-code-server').resolve().parent.parent)\n"
    )


def workspace_bootstrap() -> str:
    return base64.b64encode(zlib.compress(bootstrap_source().encode())).decode()


def workspace_command() -> str:
    patch = "python3 -c " + shlex.quote(
        "import os,base64,zlib; exec(zlib.decompress(base64.b64decode(os.environ['STUDIO_EDITOR_BOOTSTRAP'])))"
    )
    return "/bin/sh -c " + shlex.quote(patch + " && exec /opt/gem/run.sh")
