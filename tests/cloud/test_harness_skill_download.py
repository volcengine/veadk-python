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

"""Offline tests for HarnessApp skill download resolution."""

from __future__ import annotations

import io
import zipfile

import httpx

from veadk.cloud.harness_app import utils


def _skill_zip_bytes(name: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "SKILL.md",
            f"---\nname: {name}\ndescription: Test skill.\n---\n\n# {name}\n",
        )
    return buffer.getvalue()


def test_download_skill_resolves_short_name_to_exact_slug(monkeypatch, tmp_path):
    calls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        calls.append(url)
        request = httpx.Request("GET", url)
        if url.endswith("/download/web-scraper"):
            return httpx.Response(
                200,
                request=request,
                json={
                    "ResponseMetadata": {
                        "Action": "DownloadSkill",
                        "Error": {"Code": "NotFound"},
                    }
                },
            )
        if "/v1/skills?" in url:
            return httpx.Response(
                200,
                request=request,
                json={
                    "Skills": [
                        {
                            "Name": "web-scraper",
                            "Slug": "clawhub/example/web-scraper",
                            "SourceRepo": "clawhub/example",
                        }
                    ]
                },
            )
        if url.endswith("/download/clawhub/example/web-scraper"):
            return httpx.Response(
                200,
                request=request,
                content=_skill_zip_bytes("web-scraper"),
            )
        return httpx.Response(404, request=request)

    monkeypatch.setattr(utils.httpx, "get", fake_get)

    extracted = utils._download_and_extract_skill("web-scraper", tmp_path)

    assert extracted == tmp_path / "web-scraper"
    assert (extracted / "SKILL.md").is_file()
    assert calls == [
        "https://skills.volces.com/v1/skills/download/web-scraper",
        "https://skills.volces.com/v1/skills?query=web-scraper&pageNumber=1&pageSize=10",
        "https://skills.volces.com/v1/skills/download/clawhub/example/web-scraper",
    ]
