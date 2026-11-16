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

"""Turn a Markdown outline into a Mermaid mindmap and a standalone SVG."""

from __future__ import annotations

import html
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from google.adk.tools import ToolContext
from google.genai import types

_MAX_NODES = 500
_MAX_DEPTH = 8
_MAX_LABEL_LENGTH = 80

_MERMAID_MIME_TYPE = "text/plain"
_SVG_MIME_TYPE = "image/svg+xml"
_DEFAULT_STEM = "mindmap"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\-一-鿿]+")

# Mermaid mindmap labels break on these structural characters.
_MERMAID_TRANSLATION = str.maketrans(
    {"(": " ", ")": " ", "[": " ", "]": " ", "{": " ", "}": " ", '"': " "}
)

_NODE_HEIGHT = 36
_NODE_MIN_WIDTH = 80
_NODE_MAX_WIDTH = 260
_HORIZONTAL_GAP = 24
_VERTICAL_GAP = 48
_MARGIN = 32
_FONT_SIZE = 13


@dataclass
class _Node:
    label: str
    depth: int
    children: list["_Node"] = field(default_factory=list)


def _clean_label(value: object) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_MAX_LABEL_LENGTH]


def _parse_markdown(title: str, markdown: str) -> _Node:
    root = _Node(_clean_label(title) or "Mindmap", 0)
    node_count = 1
    heading_stack: list[tuple[int, _Node]] = []
    bullet_stack: list[tuple[int, _Node]] = []

    for raw_line in markdown.splitlines():
        if node_count >= _MAX_NODES:
            break
        line = raw_line.rstrip()
        if not line.strip():
            continue

        heading = _HEADING_RE.match(line.strip())
        if heading:
            level = len(heading.group(1))
            label = _clean_label(heading.group(2))
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            parent = heading_stack[-1][1] if heading_stack else root
            node = _Node(label, parent.depth + 1)
            if node.depth <= _MAX_DEPTH:
                parent.children.append(node)
                node_count += 1
                heading_stack.append((level, node))
            bullet_stack.clear()
            continue

        bullet = _BULLET_RE.match(line)
        if bullet:
            indent = len(bullet.group(1).expandtabs(2)) // 2
            label = _clean_label(bullet.group(2))
            while bullet_stack and bullet_stack[-1][0] >= indent:
                bullet_stack.pop()
            if bullet_stack:
                parent = bullet_stack[-1][1]
            elif heading_stack:
                parent = heading_stack[-1][1]
            else:
                parent = root
            node = _Node(label, parent.depth + 1)
            if node.depth <= _MAX_DEPTH:
                parent.children.append(node)
                node_count += 1
                bullet_stack.append((indent, node))
            continue
        # Plain text lines are not part of the outline.

    return root


def _mermaid_label(value: str) -> str:
    text = value.translate(_MERMAID_TRANSLATION)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_MAX_LABEL_LENGTH] or "-"


def _render_mermaid(root: _Node) -> str:
    lines = ["mindmap", f"  root(({_mermaid_label(root.label)}))"]

    def walk(node: _Node, depth: int) -> None:
        for child in node.children:
            lines.append(f"{'  ' * (depth + 1)}{_mermaid_label(child.label)}")
            walk(child, depth + 1)

    walk(root, 1)
    return "\n".join(lines)


def _display_label(node: _Node) -> str:
    return _mermaid_label(node.label)


def _node_width(node: _Node) -> int:
    text_width = int(len(_display_label(node)) * 7.5) + 24
    return max(_NODE_MIN_WIDTH, min(_NODE_MAX_WIDTH, text_width))


def _subtree_width(node: _Node) -> int:
    if not node.children:
        return _node_width(node)
    children_width = sum(_subtree_width(child) for child in node.children)
    children_width += _HORIZONTAL_GAP * (len(node.children) - 1)
    return max(_node_width(node), children_width)


def _tree_depth(node: _Node) -> int:
    if not node.children:
        return 0
    return 1 + max(_tree_depth(child) for child in node.children)


def _xml_escape(value: str) -> str:
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    return html.escape(cleaned, quote=True)


def _render_svg(root: _Node) -> str:
    positions: dict[int, tuple[float, float]] = {}

    def assign(node: _Node, left: float, depth: int) -> None:
        subtree = float(_subtree_width(node))
        center_y = _MARGIN + depth * (_NODE_HEIGHT + _VERTICAL_GAP) + _NODE_HEIGHT / 2
        if not node.children:
            positions[id(node)] = (left + subtree / 2, center_y)
            return
        cursor = left
        for child in node.children:
            assign(child, cursor, depth + 1)
            cursor += _subtree_width(child) + _HORIZONTAL_GAP
        first = positions[id(node.children[0])][0]
        last = positions[id(node.children[-1])][0]
        own_width = float(_node_width(node))
        center_x = (first + last) / 2
        center_x = max(
            left + own_width / 2, min(center_x, left + subtree - own_width / 2)
        )
        positions[id(node)] = (center_x, center_y)

    assign(root, _MARGIN, 0)

    width = _subtree_width(root) + 2 * _MARGIN
    depth = _tree_depth(root)
    height = 2 * _MARGIN + (depth + 1) * _NODE_HEIGHT + depth * _VERTICAL_GAP

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" '
            f'role="img" aria-label="{_xml_escape(root.label)}">'
        ),
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
    ]

    def edges(node: _Node) -> None:
        parent_x, parent_y = positions[id(node)]
        start_y = parent_y + _NODE_HEIGHT / 2
        for child in node.children:
            child_x, child_y = positions[id(child)]
            end_y = child_y - _NODE_HEIGHT / 2
            middle_y = (start_y + end_y) / 2
            parts.append(
                (
                    f'<path d="M {parent_x:.1f} {start_y:.1f} C '
                    f"{parent_x:.1f} {middle_y:.1f}, "
                    f"{child_x:.1f} {middle_y:.1f}, "
                    f'{child_x:.1f} {end_y:.1f}" fill="none" '
                    'stroke="#94a3b8" stroke-width="1.5"/>'
                )
            )
            edges(child)

    edges(root)

    def boxes(node: _Node) -> None:
        center_x, center_y = positions[id(node)]
        node_width = _node_width(node)
        x = center_x - node_width / 2
        y = center_y - _NODE_HEIGHT / 2
        parts.append(
            (
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{node_width}" '
                f'height="{_NODE_HEIGHT}" rx="8" ry="8" fill="#eef2ff" '
                'stroke="#6366f1" stroke-width="1.5"/>'
            )
        )
        parts.append(
            (
                f'<text x="{center_x:.1f}" y="{center_y:.1f}" '
                'text-anchor="middle" dominant-baseline="middle" '
                'font-family="Helvetica, Arial, sans-serif" '
                f'font-size="{_FONT_SIZE}" fill="#1e293b">'
                f"{_xml_escape(_display_label(node))}</text>"
            )
        )
        for child in node.children:
            boxes(child)

    boxes(root)
    parts.append("</svg>")
    return "\n".join(parts)


def _sanitize_stem(filename: str | None) -> str:
    if not isinstance(filename, str) or not filename.strip():
        return _DEFAULT_STEM
    name = filename.strip().replace("\\", "/").rsplit("/", 1)[-1]
    name = _FILENAME_RE.sub("-", name).strip(".-")
    stem = name.rsplit(".", 1)[0] if "." in name else name
    stem = stem.strip(".-")
    return (stem or _DEFAULT_STEM)[:100]


def _count_nodes(node: _Node) -> int:
    return 1 + sum(_count_nodes(child) for child in node.children)


async def mindmap_generate(
    title: str,
    markdown: str,
    filename: str | None = None,
    tool_context: ToolContext | None = None,
) -> dict:
    """Build a Mermaid mindmap and a deterministic SVG from a Markdown outline.

    Headings (``#`` through ``######``) nest by level; ``-``/``*``/``+`` bullets
    nest by two-space indentation. Blank lines and plain text are ignored.

    Args:
        title: Root node label.
        markdown: Outline using headings and/or indented bullets.
        filename: Optional base filename; ``.mmd`` and ``.svg`` are generated.
        tool_context: Current ADK tool context. When omitted, both files are
            written to a temporary directory instead.

    Returns:
        ``{"title", "mermaid", "mmd_filename", "svg_filename", "nodes",
        "artifact_saved", "mmd_path", "svg_path"}`` on success, or
        ``{"error"}`` on failure.
    """
    title_text = (
        title if isinstance(title, str) else ("" if title is None else str(title))
    )
    markdown_text = (
        markdown
        if isinstance(markdown, str)
        else ("" if markdown is None else str(markdown))
    )
    root = _parse_markdown(title_text, markdown_text)
    mermaid = _render_mermaid(root)
    svg = _render_svg(root)

    stem = _sanitize_stem(filename)
    mmd_name = f"{stem}.mmd"
    svg_name = f"{stem}.svg"
    mmd_bytes = mermaid.encode("utf-8")
    svg_bytes = svg.encode("utf-8")

    result = {
        "title": root.label,
        "mermaid": mermaid,
        "mmd_filename": mmd_name,
        "svg_filename": svg_name,
        "nodes": _count_nodes(root),
        "artifact_saved": False,
        "mmd_path": None,
        "svg_path": None,
    }

    if tool_context is None:
        directory = tempfile.mkdtemp(prefix="veadk-mindmap-")
        mmd_path = Path(directory) / mmd_name
        svg_path = Path(directory) / svg_name
        try:
            mmd_path.write_bytes(mmd_bytes)
            svg_path.write_bytes(svg_bytes)
        except OSError as exc:
            return {"error": f"failed to write files: {exc}"}
        result["mmd_path"] = str(mmd_path)
        result["svg_path"] = str(svg_path)
        return result

    try:
        for name, data, mime_type in (
            (mmd_name, mmd_bytes, _MERMAID_MIME_TYPE),
            (svg_name, svg_bytes, _SVG_MIME_TYPE),
        ):
            artifact = types.Part.from_bytes(data=data, mime_type=mime_type)
            if artifact.inline_data is not None:
                artifact.inline_data.display_name = name
            await tool_context.save_artifact(name, artifact)
    except Exception as exc:  # noqa: BLE001 - artifact storage failure
        return {"error": f"failed to save artifact: {exc}"}

    result["artifact_saved"] = True
    return result


__all__ = ["mindmap_generate"]
