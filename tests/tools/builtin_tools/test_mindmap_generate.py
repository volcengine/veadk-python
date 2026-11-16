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

import re
from pathlib import Path

import pytest

from veadk.tools.builtin_tools import mindmap_generate as mindmap_module
from veadk.tools.builtin_tools.mindmap_generate import (
    _count_nodes,
    _mermaid_label,
    _parse_markdown,
    _render_mermaid,
    _render_svg,
    _sanitize_stem,
    _xml_escape,
    mindmap_generate,
)


class SaveContext:
    def __init__(self, fail_on: int | None = None) -> None:
        self.artifacts: list[tuple[str, object]] = []
        self.fail_on = fail_on
        self.calls = 0

    async def save_artifact(self, filename: str, artifact: object) -> int:
        self.calls += 1
        if self.fail_on == self.calls:
            raise RuntimeError("storage unavailable")
        self.artifacts.append((filename, artifact))
        return len(self.artifacts)


def _max_depth(node) -> int:
    if not node.children:
        return node.depth
    return max(_max_depth(child) for child in node.children)


# --------------------------------------------------------------------- parse --
def test_parse_headings_and_nested_bullets() -> None:
    markdown = "# A\n## A1\n- b1\n  - b2\n    - b3\n## A2\n# B\n"

    root = _parse_markdown("Root", markdown)

    assert root.label == "Root"
    assert [child.label for child in root.children] == ["A", "B"]
    a = root.children[0]
    assert [child.label for child in a.children] == ["A1", "A2"]
    a1 = a.children[0]
    assert [child.label for child in a1.children] == ["b1"]
    assert [child.label for child in a1.children[0].children] == ["b2"]
    assert [child.label for child in a1.children[0].children[0].children] == ["b3"]
    assert _max_depth(root) == 5


def test_parse_bullets_before_any_heading_attach_to_root() -> None:
    root = _parse_markdown("Root", "- one\n  - two\n    - three")
    assert [child.label for child in root.children] == ["one"]
    assert root.children[0].children[0].label == "two"
    assert root.children[0].children[0].children[0].label == "three"


def test_parse_ignores_blank_plain_and_empty_lines() -> None:
    root = _parse_markdown("Root", "\nplain text\n# \n- \n* \n# Real\n")
    assert [child.label for child in root.children] == ["Real"]


def test_parse_heading_levels_nest() -> None:
    root = _parse_markdown("Root", "### Deep\n# Shallow\n## Mid")
    # A level-3 heading without a level-1 parent still nests under the root.
    assert [child.label for child in root.children] == ["Deep", "Shallow"]
    assert root.children[1].children[0].label == "Mid"


def test_parse_caps_node_count() -> None:
    markdown = "\n".join(f"- node {index}" for index in range(600))
    root = _parse_markdown("Root", markdown)
    assert _count_nodes(root) == 500


def test_parse_caps_depth_at_eight() -> None:
    lines = ["- level 0"]
    for level in range(1, 11):
        lines.append("  " * level + f"- level {level}")
    root = _parse_markdown("Root", "\n".join(lines))
    assert _max_depth(root) <= 8


def test_parse_tabs_count_as_two_spaces() -> None:
    root = _parse_markdown("Root", "- a\n\t- b")
    assert root.children[0].children[0].label == "b"


# ------------------------------------------------------------------- mermaid --
def test_mermaid_labels_escape_structural_characters() -> None:
    root = _parse_markdown('A (B) [C] {D} "E"', "- x(y) [z]\n- " + "long " * 30)
    mermaid = _render_mermaid(root)

    assert mermaid.splitlines()[0] == "mindmap"
    assert mermaid.splitlines()[1] == "  root((A B C D E))"
    assert "(B)" not in mermaid
    assert "[" not in mermaid
    labels = [line.strip() for line in mermaid.splitlines()[2:]]
    assert labels[0] == "x y z"
    assert len(labels[1]) <= 80


def test_mermaid_label_falls_back_to_dash() -> None:
    assert _mermaid_label("()[]{}") == "-"


def test_mermaid_indentation_tracks_depth() -> None:
    root = _parse_markdown("Root", "# A\n## B\n- c")
    lines = _render_mermaid(root).splitlines()
    assert lines == [
        "mindmap",
        "  root((Root))",
        "    A",
        "      B",
        "        c",
    ]


# ----------------------------------------------------------------------- svg --
def test_svg_has_expected_structure_and_escapes_xml() -> None:
    root = _parse_markdown('<Root> & "Quote"', "- a & b\n  - c < d")
    svg = _render_svg(root)

    assert svg.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg
    assert 'fill="#ffffff"' in svg
    assert 'rx="8"' in svg
    assert "<path" in svg
    assert 'font-size="13"' in svg
    assert "&lt;Root&gt;" in svg
    assert "&amp;" in svg
    assert "&quot;" in svg
    assert "<Root>" not in svg
    assert "a &amp; b" in svg
    assert "c &lt; d" in svg
    assert svg.endswith("</svg>")


def test_svg_is_deterministic_and_grows_with_content() -> None:
    small = _render_svg(_parse_markdown("Root", ""))
    large = _render_svg(
        _parse_markdown("Root", "\n".join(f"- node {i}" for i in range(20)))
    )
    assert small == _render_svg(_parse_markdown("Root", ""))

    def width(svg: str) -> int:
        return int(re.search(r'width="(\d+)"', svg).group(1))

    assert width(large) > width(small)
    assert 'height="' in large


def test_xml_escape_removes_control_characters() -> None:
    assert _xml_escape("a\x00b\x07c") == "abc"


# ------------------------------------------------------------------- filename --
@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        (None, "mindmap"),
        ("", "mindmap"),
        ("   ", "mindmap"),
        (123, "mindmap"),
        ("../../evil mind", "evil-mind"),
        ("My Chart.mmd", "My-Chart"),
        ("diagram.svg", "diagram"),
        ("报告 final", "报告-final"),
        ("C:\\tmp\\chart", "chart"),
        (".hidden", "hidden"),
    ],
)
def test_sanitize_stem(filename: object, expected: str) -> None:
    assert _sanitize_stem(filename) == expected


# ---------------------------------------------------------------- generation --
@pytest.mark.asyncio
async def test_empty_markdown_creates_root_only_mindmap() -> None:
    result = await mindmap_generate("Root", "", tool_context=None)

    assert result["title"] == "Root"
    assert result["nodes"] == 1
    assert result["mermaid"] == "mindmap\n  root((Root))"
    assert result["artifact_saved"] is False
    assert result["mmd_filename"] == "mindmap.mmd"
    assert result["svg_filename"] == "mindmap.svg"
    assert Path(result["mmd_path"]).read_text(encoding="utf-8") == result["mermaid"]
    assert Path(result["svg_path"]).read_text(encoding="utf-8").startswith("<?xml")


@pytest.mark.asyncio
async def test_empty_title_uses_default_root_label() -> None:
    result = await mindmap_generate("", "- child", tool_context=None)
    assert result["title"] == "Mindmap"
    assert result["nodes"] == 2


@pytest.mark.asyncio
async def test_generation_counts_nodes_and_uses_custom_filename() -> None:
    result = await mindmap_generate(
        "Plan",
        "# Phase 1\n- a\n- b\n# Phase 2",
        filename="../../my plan.mmd",
        tool_context=None,
    )

    assert result["nodes"] == 5
    assert result["mmd_filename"] == "my-plan.mmd"
    assert result["svg_filename"] == "my-plan.svg"
    assert Path(result["mmd_path"]).name == "my-plan.mmd"
    assert Path(result["svg_path"]).name == "my-plan.svg"
    assert "Phase 1" in result["mermaid"]


@pytest.mark.asyncio
async def test_non_string_arguments_are_coerced() -> None:
    result = await mindmap_generate(123, None, tool_context=None)  # type: ignore[arg-type]
    assert result["title"] == "123"
    assert result["nodes"] == 1


@pytest.mark.asyncio
async def test_saves_mmd_and_svg_artifacts() -> None:
    context = SaveContext()

    result = await mindmap_generate(
        "Root",
        "- child",
        filename="map",
        tool_context=context,  # type: ignore[arg-type]
    )

    assert result["artifact_saved"] is True
    assert result["mmd_path"] is None
    assert result["svg_path"] is None
    assert [name for name, _ in context.artifacts] == ["map.mmd", "map.svg"]
    mmd = context.artifacts[0][1]
    svg = context.artifacts[1][1]
    assert mmd.inline_data.mime_type == "text/plain"
    assert mmd.inline_data.display_name == "map.mmd"
    assert mmd.inline_data.data == result["mermaid"].encode("utf-8")
    assert svg.inline_data.mime_type == "image/svg+xml"
    assert svg.inline_data.display_name == "map.svg"
    assert svg.inline_data.data.decode("utf-8").startswith("<?xml")


@pytest.mark.asyncio
async def test_artifact_failure_returns_error() -> None:
    result = await mindmap_generate(
        "Root",
        "- child",
        tool_context=SaveContext(fail_on=1),  # type: ignore[arg-type]
    )
    assert "error" in result
    assert "failed to save artifact" in result["error"]


@pytest.mark.asyncio
async def test_artifact_failure_on_second_save_returns_error() -> None:
    context = SaveContext(fail_on=2)
    result = await mindmap_generate(
        "Root",
        "- child",
        tool_context=context,  # type: ignore[arg-type]
    )
    assert "failed to save artifact" in result["error"]
    assert context.calls == 2
    assert len(context.artifacts) == 1


@pytest.mark.asyncio
async def test_temp_dir_write_failure_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        mindmap_module.tempfile, "mkdtemp", lambda **kwargs: str(blocker)
    )

    result = await mindmap_generate("Root", "- child", tool_context=None)

    assert "error" in result
    assert "failed to write files" in result["error"]


@pytest.mark.asyncio
async def test_mermaid_escapes_title_in_generated_output() -> None:
    result = await mindmap_generate("A (B)", "- c [d]", tool_context=None)
    assert result["mermaid"] == "mindmap\n  root((A B))\n    c d"
    assert "(B)" not in result["mermaid"]
