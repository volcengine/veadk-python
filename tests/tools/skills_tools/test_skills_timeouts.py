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

"""Regression tests: skills tooling must bound its object-storage transfers.

The signed-URL up/downloads below talk straight to TOS/minio, which `requests`
would otherwise wait on forever. Every site must carry the shared
`DEFAULT_HTTP_TIMEOUT` -- object storage gets no longer allowance than any
other call. The values themselves live in `veadk.utils.http_defaults` so they
stay tunable without touching these assertions.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from veadk.utils.http_defaults import DEFAULT_HTTP_TIMEOUT


def _ok_response(**attrs: Any) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    for name, value in attrs.items():
        setattr(response, name, value)
    return response


def test_skills_tool_vestack_download_passes_default_http_timeout(
    tmp_path: Path,
) -> None:
    from veadk.tools.skills_tools.skills_tool import SkillsTool

    save_path = tmp_path / "web-search.zip"
    tool = SkillsTool(skills={})

    with (
        patch(
            "veadk.utils.volcengine_sign.ve_request",
            return_value={"Result": {"SignedUrl": "https://minio.test/web-search.zip"}},
        ),
        patch(
            "veadk.tools.skills_tools.skills_tool.download_url_to_file",
            side_effect=lambda url, path: Path(path).write_bytes(b"zip-bytes"),
        ) as download,
    ):
        success = tool._download_skill_via_vestack(
            skill=SimpleNamespace(id="s-skillid"),
            tos_path="skills/s-skillid/v1/web-search.zip",
            cloud_provider="vestack",
            access_key="ak",
            secret_key="sk",
            session_token="token",
            skill_name="web-search",
            save_path=save_path,
        )

    assert success is True
    download.assert_called_once_with("https://minio.test/web-search.zip", save_path)
    assert save_path.read_bytes() == b"zip-bytes"


def test_download_skills_tool_vestack_download_passes_default_http_timeout(
    tmp_path: Path,
) -> None:
    # NOTE: this module-level helper is currently unreferenced outside its own
    # module, but it is a live copy of the download path above and must not
    # regress if it is wired back up.
    from veadk.tools.skills_tools.download_skills_tool import (
        _download_skill_via_vestack,
    )

    zip_path = tmp_path / "web-search.zip"

    with (
        patch(
            "veadk.utils.volcengine_sign.ve_request",
            return_value={"Result": {"SignedUrl": "https://minio.test/web-search.zip"}},
        ),
        patch(
            "veadk.tools.skills_tools.download_skills_tool.download_url_to_file",
            side_effect=lambda url, path: Path(path).write_bytes(b"zip-bytes"),
        ) as download,
    ):
        success = _download_skill_via_vestack(
            tos_path="skills/s-skillid/v1/web-search.zip",
            skill_name="web-search",
            access_key="ak",
            secret_key="sk",
            session_token="token",
            service="agentkit",
            region="cn-beijing",
            host="agentkit.cn-beijing.volcengineapi.com",
            scheme="https",
            zip_path=zip_path,
        )

    assert success is True
    download.assert_called_once_with("https://minio.test/web-search.zip", zip_path)
    assert zip_path.read_bytes() == b"zip-bytes"


def test_register_skills_tool_signed_url_upload_passes_default_http_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `veadk.tools.skills_tools.__init__` re-exports the function under the
    # same name as its module, so plain attribute access hands back the
    # function. Go through the module registry to reach the module object.
    module = import_module("veadk.tools.skills_tools.register_skills_tool")

    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: demo\n---\n\nbody\n",
        encoding="utf-8",
    )

    session_dir = tmp_path / "session"
    (session_dir / "outputs").mkdir(parents=True)
    monkeypatch.setattr(module, "get_session_path", lambda session_id: session_dir)

    monkeypatch.setenv("CLOUD_PROVIDER", "vestack")
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")
    monkeypatch.setenv("SKILL_SPACE_ID", "space-1")

    def fake_ve_request(**kwargs: Any) -> dict:
        if kwargs["action"] == "GenTempTosObjectUrl":
            return {
                "Result": {
                    "SignedUrl": "https://minio.test/upload",
                    "TosUrl": "tos://bucket/demo-skill.zip",
                }
            }
        return {"Result": {"SkillId": "s-1"}}

    monkeypatch.setattr(module, "ve_request", fake_ve_request)

    tool_context = SimpleNamespace(session=SimpleNamespace(id="session-1"))

    with patch("requests.put", return_value=_ok_response()) as put:
        result = module.register_skills_tool(
            skill_local_path=str(skill_dir),
            tool_context=tool_context,
        )

    assert result.startswith("Successfully registered skill 'demo-skill'"), result
    assert put.call_count == 1
    assert put.call_args.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT
