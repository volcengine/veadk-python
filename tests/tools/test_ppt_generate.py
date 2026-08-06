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

import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from veadk.tools.builtin_tools import ppt_generate as presentation_tool


@pytest.mark.asyncio
async def test_create_pptx_has_no_node_runtime_dependency(tmp_path: Path) -> None:
    output = tmp_path / "deck.pptx"
    preview = tmp_path / "deck.webp"

    await presentation_tool._create_pptx(
        {
            "title": "Runtime independent",
            "subtitle": "Pure Python",
            "theme": "blue",
            "slides": [
                {
                    "title": "Result",
                    "summary": "The deck is valid OOXML.",
                    "bullets": ["No Node.js", "No private npm package"],
                    "sources": [],
                }
            ],
        },
        output,
        preview,
    )

    assert zipfile.is_zipfile(output)
    assert preview.read_bytes().startswith(b"RIFF")


def test_preview_depends_on_real_slide_content(tmp_path: Path) -> None:
    first = tmp_path / "first.webp"
    second = tmp_path / "second.webp"
    theme = presentation_tool._THEMES["blue"]

    presentation_tool._write_preview(
        {"title": "First deck", "subtitle": "Actual preview"},
        [{"title": "Revenue", "summary": "Growth", "bullets": ["Up 20%"]}],
        theme,
        first,
    )
    presentation_tool._write_preview(
        {"title": "Second deck", "subtitle": "Different content"},
        [{"title": "Risk", "summary": "Watchlist", "bullets": ["Churn"]}],
        theme,
        second,
    )

    assert first.read_bytes() != second.read_bytes()


@pytest.mark.asyncio
async def test_ppt_generate_saves_generated_file_as_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def create_pptx(
        spec: dict[str, object],
        output_path: Path,
        preview_path: Path,
    ) -> None:
        captured["spec"] = spec
        output_path.write_bytes(b"valid-pptx-placeholder")
        preview_path.write_bytes(b"valid-preview-placeholder")

    class ToolContext:
        async def save_artifact(self, filename: str, artifact: object) -> int:
            artifacts = captured.setdefault("artifacts", [])
            assert isinstance(artifacts, list)
            artifacts.append((filename, artifact))
            return len(artifacts) + 1

    monkeypatch.setattr(presentation_tool, "_create_pptx", create_pptx)
    result = await presentation_tool.ppt_generate(
        title="季度复盘",
        subtitle="面向管理层",
        theme="dark",
        filename="review",
        deck_markdown=(
            "## 核心结论\n"
            "增长符合预期\n"
            "- 收入增长 20%\n"
            "- 新客占比提升\n"
            "Sources: https://example.com/report"
        ),
        tool_context=ToolContext(),  # type: ignore[arg-type]
    )

    assert result == {
        "status": "created",
        "filename": "review.pptx",
        "version": 3,
        "preview_filename": "review.preview.webp",
        "preview_version": 2,
        "slide_count": 2,
    }
    artifacts = captured["artifacts"]
    assert isinstance(artifacts, list)
    assert [item[0] for item in artifacts] == [
        "review.preview.webp",
        "review.pptx",
    ]
    preview_artifact = artifacts[0][1]
    assert (
        preview_artifact.inline_data.mime_type
        == presentation_tool.PPT_PREVIEW_MIME_TYPE
    )
    assert preview_artifact.inline_data.data == b"valid-preview-placeholder"
    artifact = artifacts[1][1]
    assert isinstance(artifact, SimpleNamespace) is False
    assert artifact.inline_data.mime_type == presentation_tool.PPTX_MIME_TYPE
    assert artifact.inline_data.data == b"valid-pptx-placeholder"
    assert captured["spec"] == {
        "title": "季度复盘",
        "subtitle": "面向管理层",
        "theme": "dark",
        "slides": [
            {
                "title": "核心结论",
                "summary": "增长符合预期",
                "bullets": ["收入增长 20%", "新客占比提升"],
                "sources": ["https://example.com/report"],
            }
        ],
    }


@pytest.mark.asyncio
async def test_ppt_generate_requires_content_slide() -> None:
    with pytest.raises(ValueError, match="at least one"):
        await presentation_tool.ppt_generate(
            title="Empty",
            deck_markdown="",
            tool_context=object(),  # type: ignore[arg-type]
        )


def test_parse_deck_markdown_supports_multiple_slides() -> None:
    assert presentation_tool._parse_deck_markdown(
        "## 第一页\n摘要\n- 要点一\n## 第二页\n- 要点二"
    ) == [
        {
            "title": "第一页",
            "summary": "摘要",
            "bullets": ["要点一"],
            "sources": [],
        },
        {
            "title": "第二页",
            "summary": "",
            "bullets": ["要点二"],
            "sources": [],
        },
    ]
