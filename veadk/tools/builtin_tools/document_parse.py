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

"""Convert a local document or a public URL into bounded plain text.

The tool intentionally returns a dictionary instead of raising: malformed input,
missing files, SSRF-rejected URLs, and corrupt documents all surface as
``{"error": "..."}`` so an agent receives a tool result rather than an
exception. Remote downloads reuse the ``web_fetch`` public-URL guard and follow
redirects manually (re-validating every hop) with a hard size cap.
"""

from __future__ import annotations

import csv
import html as _html
import io
import json
import re
from pathlib import Path
from urllib.parse import urlparse, urljoin

import filetype
import requests

from veadk.tools.builtin_tools.web_fetch import assert_public_url

_DEFAULT_MAX_CHARS = 200_000
_MIN_MAX_CHARS = 1_000
_MAX_MAX_CHARS = 1_000_000

_MAX_DOWNLOAD_BYTES = 20_000_000
_MAX_REDIRECTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 30

_MAX_XLSX_SHEETS = 50
_MAX_XLSX_ROWS_PER_SHEET = 1_000
_MAX_CSV_ROWS = 5_000

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_SUPPORTED_FORMATS = {"pdf", "docx", "xlsx", "csv", "txt", "md", "json", "html"}
_FORMAT_ALIASES = {"markdown": "md", "htm": "html"}
_EXTENSION_FORMATS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".csv": "csv",
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
    ".json": "json",
    ".html": "html",
    ".htm": "html",
}

# Server-provided ``Content-Type`` fallback for URLs without a useful suffix,
# e.g. ``https://example.com/document`` serving HTML or JSON.
_CONTENT_TYPE_FORMATS = {
    "text/html": "html",
    "application/xhtml+xml": "html",
    "application/json": "json",
    "text/csv": "csv",
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}


class _ParseError(Exception):
    """Internal: converted to ``{"error": ...}`` at the tool boundary."""


# --------------------------------------------------------------- validation --
def _validate_max_chars(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _ParseError("max_chars must be an integer")
    if not _MIN_MAX_CHARS <= value <= _MAX_MAX_CHARS:
        raise _ParseError(
            f"max_chars must be between {_MIN_MAX_CHARS} and {_MAX_MAX_CHARS}"
        )
    return value


def _is_url(source: str) -> bool:
    return source.lower().startswith(("http://", "https://"))


def _normalize_format(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    normalized = _FORMAT_ALIASES.get(normalized, normalized)
    return normalized if normalized in _SUPPORTED_FORMATS else None


def _format_from_content_type(value: str | None) -> str | None:
    if not value:
        return None
    media_type = value.split(";", 1)[0].strip().lower()
    return _CONTENT_TYPE_FORMATS.get(media_type)


def _looks_like_html(data: bytes) -> bool:
    head = data[:512].decode("utf-8", errors="ignore").lstrip().lower()
    return head.startswith(("<!doctype html", "<html", "<head", "<body"))


def _detect_format(
    source: str,
    data: bytes,
    explicit: object,
    content_type: str | None = None,
) -> str | None:
    if explicit is not None:
        return _normalize_format(explicit)

    if _is_url(source):
        suffix = Path(urlparse(source).path).suffix.lower()
    else:
        suffix = Path(source).suffix.lower()
    if suffix in _EXTENSION_FORMATS:
        return _EXTENSION_FORMATS[suffix]

    by_content_type = _format_from_content_type(content_type)
    if by_content_type is not None:
        return by_content_type

    try:
        kind = filetype.guess(data)
    except Exception:  # noqa: BLE001 - detection is best-effort
        kind = None
    if kind is not None:
        detected = _EXTENSION_FORMATS.get(f".{kind.extension.lower()}")
        if detected is not None:
            return detected
    if _looks_like_html(data):
        return "html"
    return "txt"


# ----------------------------------------------------------------- download --
def _read_capped(response: requests.Response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=16_384):
        if not chunk:
            continue
        chunks.append(chunk)
        total += len(chunk)
        if total >= _MAX_DOWNLOAD_BYTES:
            break
    return b"".join(chunks)[:_MAX_DOWNLOAD_BYTES]


def _download_url(url: str) -> tuple[bytes, str, str | None]:
    """Download *url*, re-validating each redirect hop and capping the size.

    Returns the body, the final URL after redirects, and the response
    ``Content-Type`` (if any) so format detection can use it.
    """
    current = url
    hops = 0
    while True:
        # Raises ValueError for non-http(s) schemes or non-public hosts.
        assert_public_url(current)
        response = requests.get(
            current,
            headers={"User-Agent": _USER_AGENT},
            timeout=_DOWNLOAD_TIMEOUT_SECONDS,
            allow_redirects=False,
            stream=True,
        )
        try:
            location = response.headers.get("location")
            if response.is_redirect and location:
                hops += 1
                if hops > _MAX_REDIRECTS:
                    raise _ParseError(f"too many redirects (>{_MAX_REDIRECTS})")
                current = urljoin(current, location)
                continue
            if not response.ok:
                raise _ParseError(f"HTTP {response.status_code}")
            return (
                _read_capped(response),
                current,
                response.headers.get("content-type"),
            )
        finally:
            response.close()


# ------------------------------------------------------------------ parsers --
def _extract_pdf(data: bytes) -> tuple[str, dict]:
    import pypdfium2 as pdfium

    with pdfium.PdfDocument(io.BytesIO(data)) as document:
        page_count = len(document)
        parts: list[str] = []
        for index in range(page_count):
            page = document[index]
            try:
                textpage = page.get_textpage()
                try:
                    parts.append(textpage.get_text_range())
                finally:
                    textpage.close()
            finally:
                page.close()
    text = "\n\n".join(parts)
    return text, {"pages": page_count, "needs_ocr": page_count > 0 and not text.strip()}


def _extract_docx(data: bytes) -> tuple[str, dict]:
    import docx
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(io.BytesIO(data))
    blocks: list[str] = []
    paragraph_count = 0
    table_count = 0
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            blocks.append(Paragraph(child, document).text)
            paragraph_count += 1
        elif child.tag == qn("w:tbl"):
            table = Table(child, document)
            rows = [
                " | ".join(cell.text.strip() for cell in row.cells)
                for row in table.rows
            ]
            blocks.append("\n".join(rows))
            table_count += 1
    text = "\n\n".join(block for block in blocks if block.strip())
    return text, {"paragraphs": paragraph_count, "tables": table_count}


def _extract_xlsx(data: bytes) -> tuple[str, dict]:
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        sheet_names = list(workbook.sheetnames)[:_MAX_XLSX_SHEETS]
        lines: list[str] = []
        total_rows = 0
        for name in sheet_names:
            lines.append(f"## {name}")
            emitted = 0
            for row in workbook[name].iter_rows(values_only=True):
                if emitted >= _MAX_XLSX_ROWS_PER_SHEET:
                    break
                lines.append(
                    "\t".join("" if value is None else str(value) for value in row)
                )
                emitted += 1
            total_rows += emitted
    finally:
        workbook.close()
    text = "\n".join(lines)
    return text, {"sheets": sheet_names, "total_rows": total_rows}


def _extract_csv(data: bytes) -> tuple[str, dict]:
    decoded = data.decode("utf-8", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(decoded[:4096])
    except csv.Error:
        dialect = csv.excel
    delimiter = getattr(dialect, "delimiter", ",")
    lines: list[str] = []
    for index, row in enumerate(csv.reader(io.StringIO(decoded), dialect)):
        if index >= _MAX_CSV_ROWS:
            break
        lines.append("\t".join(row))
    return "\n".join(lines), {"delimiter": delimiter, "rows": len(lines)}


def _strip_html_tags(value: str) -> str:
    value = re.sub(
        r"<(script|style)[\s\S]*?</\1(?:\s+[^>]*)?>",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    value = _html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", value).strip()


def _extract_html(data: bytes) -> tuple[str, dict]:
    import trafilatura

    decoded = data.decode("utf-8", errors="replace")
    try:
        extracted = trafilatura.extract(decoded)
    except Exception:  # noqa: BLE001 - fall back to a coarse strip
        extracted = None
    if extracted and extracted.strip():
        return extracted.strip(), {"extraction": "trafilatura"}
    return _strip_html_tags(decoded), {"extraction": "fallback"}


def _extract_json(data: bytes) -> tuple[str, dict]:
    decoded = data.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(decoded)
    except (TypeError, ValueError):
        return decoded, {"valid_json": False}
    return json.dumps(parsed, ensure_ascii=False, indent=2), {"valid_json": True}


def _extract_text(data: bytes) -> tuple[str, dict]:
    return data.decode("utf-8", errors="replace"), {}


def _parse_bytes(fmt: str, data: bytes) -> tuple[str, dict]:
    if fmt == "pdf":
        return _extract_pdf(data)
    if fmt == "docx":
        return _extract_docx(data)
    if fmt == "xlsx":
        return _extract_xlsx(data)
    if fmt == "csv":
        return _extract_csv(data)
    if fmt == "html":
        return _extract_html(data)
    if fmt == "json":
        return _extract_json(data)
    return _extract_text(data)


# --------------------------------------------------------------------- tool --
def document_parse(
    source: str,
    format: str | None = None,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> dict:
    """Parse a document into bounded plain text.

    Accepts a local file path or a public http(s) URL. The format is taken from
    ``format`` when supplied, otherwise inferred from the file extension, then
    from the response ``Content-Type``, then from the file's magic bytes, then
    from an HTML sniff, and finally treated as UTF-8 text.

    Args:
        source: Local path or public http(s) URL.
        format: Optional override: pdf, docx, xlsx, csv, txt, md, json, or html.
        max_chars: Maximum characters returned (1,000-1,000,000).

    Returns:
        ``{"format", "text", "truncated", "metadata"}`` on success, or
        ``{"error"}`` on failure.
    """
    try:
        limit = _validate_max_chars(max_chars)
    except _ParseError as exc:
        return {"error": str(exc)}

    if not isinstance(source, str) or not source.strip():
        return {"error": "source is required"}
    source = source.strip()

    metadata: dict[str, object] = {}
    detection_source = source
    content_type: str | None = None
    try:
        if _is_url(source):
            try:
                data, final_url, content_type = _download_url(source)
            except ValueError as exc:
                return {"error": str(exc)}
            except _ParseError as exc:
                return {"error": str(exc)}
            except requests.RequestException as exc:
                return {"error": f"download failed: {exc}"}
            metadata.update(
                {
                    "source_kind": "url",
                    "url": final_url,
                    "requested_url": source,
                }
            )
            if content_type:
                metadata["content_type"] = content_type
            detection_source = final_url
        else:
            path = Path(source)
            if not path.is_file():
                return {"error": f"file not found: {source}"}
            try:
                data = path.read_bytes()
            except OSError as exc:
                return {"error": f"failed to read file: {exc}"}
            metadata.update({"source_kind": "file", "path": str(path)})

        metadata["size_bytes"] = len(data)
        detected = _detect_format(detection_source, data, format, content_type)
        if detected is None:
            return {"error": f"unsupported format: {format}"}
        fmt = detected
        metadata["format"] = fmt

        try:
            text, extra = _parse_bytes(fmt, data)
        except Exception as exc:  # noqa: BLE001 - corrupt input is a tool error
            return {"error": f"failed to parse {fmt}: {exc}"}
        metadata.update(extra)
    except Exception as exc:  # noqa: BLE001 - never raise out of the tool
        return {"error": f"failed to parse document: {exc}"}

    truncated = len(text) > limit
    if truncated:
        text = text[:limit]
    return {
        "format": fmt,
        "text": text,
        "truncated": truncated,
        "metadata": metadata,
    }


__all__ = ["document_parse"]
