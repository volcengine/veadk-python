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

"""Generate a PowerPoint deck and save it as an ADK artifact."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from google.adk.tools import ToolContext
from google.genai import types

PPTX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)
PPT_PREVIEW_MIME_TYPE = "image/webp"
_MAX_SLIDES = 20
_MAX_BULLETS = 7
_MAX_SOURCES = 12


def _clean_text(value: object, max_length: int) -> str:
    return " ".join(str(value or "").split())[:max_length]


def _string_list(value: object, *, limit: int, max_length: int) -> list[str]:
    if isinstance(value, str):
        values = value.splitlines()
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return [text for item in values[:limit] if (text := _clean_text(item, max_length))]


def _normalize_slides(slides: list[dict[str, Any]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for index, slide in enumerate(slides[:_MAX_SLIDES]):
        if not isinstance(slide, dict):
            continue
        title = _clean_text(slide.get("title"), 120) or f"第 {index + 1} 页"
        normalized.append(
            {
                "title": title,
                "summary": _clean_text(slide.get("summary"), 240),
                "bullets": _string_list(
                    slide.get("bullets"), limit=_MAX_BULLETS, max_length=220
                ),
                "sources": _string_list(
                    slide.get("sources"), limit=_MAX_SOURCES, max_length=500
                ),
            }
        )
    return normalized


def _parse_deck_markdown(deck_markdown: str) -> list[dict[str, object]]:
    slides: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in deck_markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            if current is not None:
                slides.append(current)
            current = {
                "title": line.removeprefix("## ").strip(),
                "summary": "",
                "bullets": [],
                "sources": [],
            }
            continue
        if current is None:
            continue
        lowered = line.lower()
        if lowered.startswith("sources:") or line.startswith("来源："):
            value = line.split(":" if ":" in line else "：", 1)[1]
            current["sources"].extend(
                source.strip() for source in value.split("|") if source.strip()
            )
        elif line.startswith(("- ", "* ", "• ")):
            current["bullets"].append(line[2:].strip())
        elif not current["summary"]:
            current["summary"] = line
        else:
            current["bullets"].append(line)
    if current is not None:
        slides.append(current)
    return _normalize_slides(slides)


def _safe_filename(filename: str, title: str) -> str:
    value = Path(filename.strip()).name if filename.strip() else ""
    if not value:
        value = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", title).strip("-")
    value = value[:100] or "presentation"
    if not value.lower().endswith(".pptx"):
        value += ".pptx"
    return value


async def _create_pptx(
    spec: dict[str, object],
    output_path: Path,
    preview_path: Path,
) -> None:
    node = os.getenv("VEADK_PRESENTATION_NODE") or shutil.which("node")
    if not node:
        raise RuntimeError(
            "PPT generation requires Node.js. Configure VEADK_PRESENTATION_NODE."
        )
    runner = Path(__file__).with_name("ppt_generate.mjs")
    input_path = output_path.with_suffix(".json")
    input_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    process = await asyncio.create_subprocess_exec(
        node,
        str(runner),
        str(input_path),
        str(output_path),
        str(preview_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise RuntimeError("PPT generation timed out after 120 seconds.") from None
    if process.returncode != 0:
        detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"PPT generation failed: {detail[-2000:]}")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("PPT generation completed without producing a file.")
    if not preview_path.is_file() or preview_path.stat().st_size == 0:
        raise RuntimeError("PPT generation completed without producing a preview.")


async def ppt_generate(
    title: str,
    deck_markdown: str,
    tool_context: ToolContext,
    subtitle: str = "",
    theme: str = "blue",
    filename: str = "presentation.pptx",
) -> dict[str, object]:
    """Create a real PPTX file and attach it to the current conversation.

    Plan the complete deck before calling this tool. ``deck_markdown`` uses a
    simple flat format to avoid complex nested arguments: start every content
    slide with ``## Slide title``; add one plain-text summary line followed by
    3-7 ``- bullet`` lines. Add an optional ``Sources: URL | URL`` line when
    external claims or assets are used. The title slide is added automatically.

    Args:
        title: Audience-facing deck title.
        deck_markdown: Ordered content slides in the flat Markdown format.
        tool_context: Current ADK tool context used to save the result.
        subtitle: Optional title-slide subtitle.
        theme: Visual theme: blue, dark, warm, or green.
        filename: Download filename ending in .pptx.

    Returns:
        Metadata for the saved PowerPoint artifact.
    """
    deck_title = _clean_text(title, 160)
    if not deck_title:
        raise ValueError("title is required")
    normalized_slides = _parse_deck_markdown(deck_markdown)
    if not normalized_slides:
        raise ValueError(
            "deck_markdown must contain at least one content slide starting with ##"
        )
    artifact_name = _safe_filename(filename, deck_title)
    spec: dict[str, object] = {
        "title": deck_title,
        "subtitle": _clean_text(subtitle, 240),
        "theme": theme if theme in {"blue", "dark", "warm", "green"} else "blue",
        "slides": normalized_slides,
    }

    with tempfile.TemporaryDirectory(prefix="veadk-ppt-") as temp_dir:
        output_path = Path(temp_dir) / artifact_name
        preview_name = f"{Path(artifact_name).stem}.preview.webp"
        preview_path = Path(temp_dir) / preview_name
        await _create_pptx(spec, output_path, preview_path)
        preview_artifact = types.Part.from_bytes(
            data=preview_path.read_bytes(),
            mime_type=PPT_PREVIEW_MIME_TYPE,
        )
        if preview_artifact.inline_data is not None:
            preview_artifact.inline_data.display_name = preview_name
        preview_version = await tool_context.save_artifact(
            preview_name,
            preview_artifact,
        )
        artifact = types.Part.from_bytes(
            data=output_path.read_bytes(),
            mime_type=PPTX_MIME_TYPE,
        )
        if artifact.inline_data is not None:
            artifact.inline_data.display_name = artifact_name
        version = await tool_context.save_artifact(artifact_name, artifact)

    return {
        "status": "created",
        "filename": artifact_name,
        "version": version,
        "preview_filename": preview_name,
        "preview_version": preview_version,
        "slide_count": len(normalized_slides) + 1,
    }


__all__ = ["ppt_generate"]
