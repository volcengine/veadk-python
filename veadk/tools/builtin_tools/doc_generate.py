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

"""Generate a Word, Excel, CSV, or Markdown document as an ADK artifact."""

from __future__ import annotations

import csv
import io
import re
import tempfile
from pathlib import Path

from google.adk.tools import ToolContext
from google.genai import types

_SUPPORTED_FORMATS = {"docx", "xlsx", "csv", "md"}

_MIME_TYPES = {
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "md": "text/markdown",
}

_MAX_SHEETS = 20
_MAX_ROWS_PER_SHEET = 5_000
_MAX_COLUMNS = 100
_MAX_CSV_ROWS = 10_000
_MAX_COLUMN_WIDTH = 60
_MAX_FILENAME_LENGTH = 120

_ALLOWED_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\-一-鿿]+")
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_ANY_HEADING_RE = re.compile(r"^\s*#{1,6}(?:\s|$)")


class _DocError(Exception):
    """Internal: converted to ``{"error": ...}`` at the tool boundary."""


# --------------------------------------------------------------------- docx --
def _strip_emphasis(value: str) -> str:
    return re.sub(r"\*\*|__", "", value).strip()


def _build_docx(title: str, content: str) -> bytes:
    import docx

    document = docx.Document()
    if title:
        document.add_heading(title, level=0)

    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            document.add_paragraph(_strip_emphasis(" ".join(buffer)))
            buffer.clear()

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            flush()
            document.add_heading(
                _strip_emphasis(heading.group(2)),
                level=len(heading.group(1)),
            )
            continue
        if line.startswith(("- ", "* ", "+ ")):
            flush()
            document.add_paragraph(_strip_emphasis(line[2:]), style="List Bullet")
            continue
        if line.startswith("#"):
            buffer.append(line.lstrip("#").strip())
            continue
        buffer.append(line)
    flush()

    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


# --------------------------------------------------------------------- xlsx --
def _safe_sheet_name(value: object, fallback: str) -> str:
    if not isinstance(value, str):
        raise _DocError("each sheet needs a string name")
    name = re.sub(r"[\[\]:*?/\\]", " ", value).strip()
    if not name:
        name = fallback
    return name[:31]


def _cell_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _build_xlsx(sheets: list[dict] | None) -> bytes:
    import openpyxl
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    if not isinstance(sheets, list) or not sheets:
        raise _DocError("sheets must be a non-empty list")

    workbook = openpyxl.Workbook()
    used_names: set[str] = set()
    first_sheet = True
    for index, sheet in enumerate(sheets[:_MAX_SHEETS]):
        if not isinstance(sheet, dict):
            raise _DocError("each sheet must be an object")
        name = _safe_sheet_name(sheet.get("name"), f"Sheet{index + 1}")
        rows = sheet.get("rows")
        if not isinstance(rows, list):
            raise _DocError(f"sheet {name!r} must have a rows list")
        if name in used_names:
            suffix = 2
            while f"{name[:28]}_{suffix}" in used_names:
                suffix += 1
            name = f"{name[:28]}_{suffix}"
        used_names.add(name)

        if first_sheet:
            worksheet = workbook.active
            worksheet.title = name
            first_sheet = False
        else:
            worksheet = workbook.create_sheet(title=name)

        widths: dict[int, int] = {}
        for row_index, row in enumerate(rows[:_MAX_ROWS_PER_SHEET], start=1):
            if not isinstance(row, (list, tuple)):
                raise _DocError(f"sheet {name!r} contains a non-list row")
            for column_index, value in enumerate(row[:_MAX_COLUMNS], start=1):
                worksheet.cell(
                    row=row_index,
                    column=column_index,
                    value=_cell_value(value),
                )
                width = len(str(value)) if value is not None else 0
                widths[column_index] = max(widths.get(column_index, 0), width)
        if rows:
            for cell in worksheet[1]:
                cell.font = Font(bold=True)
        for column_index, width in widths.items():
            worksheet.column_dimensions[get_column_letter(column_index)].width = min(
                max(8, width + 2), _MAX_COLUMN_WIDTH
            )

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


# ---------------------------------------------------------------------- csv --
def _build_csv(rows: list[list] | None, content: str) -> bytes:
    if rows is not None:
        if not isinstance(rows, list):
            raise _DocError("rows must be a list")
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        for row in rows[:_MAX_CSV_ROWS]:
            if not isinstance(row, (list, tuple)):
                raise _DocError("each row must be a list")
            writer.writerow(["" if value is None else str(value) for value in row])
        return buffer.getvalue().encode("utf-8")
    if content:
        return content.encode("utf-8")
    raise _DocError("csv requires rows or content")


# ----------------------------------------------------------------------- md --
def _build_md(title: str, content: str) -> bytes:
    if title and not _ANY_HEADING_RE.match(content):
        content = f"# {title}\n\n{content}" if content else f"# {title}\n"
    return content.encode("utf-8")


# ----------------------------------------------------------------- filename --
def _sanitize_filename(filename: str | None, fmt: str) -> str:
    default = f"document.{fmt}"
    if not isinstance(filename, str) or not filename.strip():
        return default
    name = filename.strip().replace("\\", "/").rsplit("/", 1)[-1]
    name = _ALLOWED_FILENAME_RE.sub("-", name).strip(".-")
    if not name:
        return default
    suffix = f".{fmt}"
    if name.lower().endswith(suffix):
        stem = name[: -len(suffix)].strip(".-")
    else:
        stem = name.rsplit(".", 1)[0] if "." in name else name
        stem = stem.strip(".-")
    stem = stem[: _MAX_FILENAME_LENGTH - len(suffix)] or "document"
    return f"{stem}{suffix}"


# --------------------------------------------------------------------- tool --
async def doc_generate(
    format: str,
    title: str,
    content: str = "",
    sheets: list[dict] | None = None,
    rows: list[list] | None = None,
    filename: str | None = None,
    tool_context: ToolContext | None = None,
) -> dict:
    """Generate a document and attach it to the current conversation.

    Args:
        format: One of ``docx``, ``xlsx``, ``csv``, or ``md`` (case-insensitive).
        title: Document title. Rendered as the Word title and the Markdown
            heading; ignored for CSV.
        content: Markdown-ish body for ``docx``/``md``; raw CSV text fallback
            for ``csv``. Supports ``#``-``###`` headings and ``-``/``*``/``+``
            bullets for Word.
        sheets: For ``xlsx``, a list of ``{"name": str, "rows": list[list]}``.
        rows: For ``csv``, a list of rows. CSV output is plain UTF-8 without a
            byte-order mark.
        filename: Optional output filename; the correct extension is forced.
        tool_context: Current ADK tool context used to save the artifact. When
            omitted, the file is written to a temporary directory instead.

    Returns:
        ``{"filename", "format", "size_bytes", "mime_type",
        "artifact_saved", "path"}`` on success, or ``{"error"}`` on failure.
    """
    fmt = format.strip().lower() if isinstance(format, str) else ""
    if fmt not in _SUPPORTED_FORMATS:
        return {"error": "format must be one of docx, xlsx, csv, md"}

    title_text = (
        title if isinstance(title, str) else ("" if title is None else str(title))
    )
    content_text = (
        content
        if isinstance(content, str)
        else ("" if content is None else str(content))
    )

    try:
        if fmt == "docx":
            data = _build_docx(title_text.strip(), content_text)
        elif fmt == "xlsx":
            data = _build_xlsx(sheets)
        elif fmt == "csv":
            data = _build_csv(rows, content_text)
        else:
            data = _build_md(title_text.strip(), content_text)
    except _DocError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - never raise out of the tool
        return {"error": f"failed to generate {fmt}: {exc}"}

    name = _sanitize_filename(filename, fmt)
    mime_type = _MIME_TYPES[fmt]
    result = {
        "filename": name,
        "format": fmt,
        "size_bytes": len(data),
        "mime_type": mime_type,
        "artifact_saved": False,
        "path": None,
    }

    if tool_context is None:
        directory = tempfile.mkdtemp(prefix="veadk-doc-")
        path = Path(directory) / name
        try:
            path.write_bytes(data)
        except OSError as exc:
            return {"error": f"failed to write file: {exc}"}
        result["path"] = str(path)
        return result

    try:
        artifact = types.Part.from_bytes(data=data, mime_type=mime_type)
        if artifact.inline_data is not None:
            artifact.inline_data.display_name = name
        await tool_context.save_artifact(name, artifact)
    except Exception as exc:  # noqa: BLE001 - artifact storage failure
        return {"error": f"failed to save artifact: {exc}"}

    result["artifact_saved"] = True
    return result


__all__ = ["doc_generate"]
