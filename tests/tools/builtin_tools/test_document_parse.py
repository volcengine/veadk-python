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

import csv
import io
import json
from pathlib import Path

import pytest

from veadk.tools.builtin_tools import document_parse as document_parse_module
from veadk.tools.builtin_tools.document_parse import document_parse


# --------------------------------------------------------------- PDF helpers --
def _make_pdf(page_texts: list[str]) -> bytes:
    """Build a tiny, valid PDF with one text object per page."""
    font_id = 3
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            "<< /Type /Pages /Kids ["
            + " ".join(f"{4 + 2 * i} 0 R" for i in range(len(page_texts)))
            + f"] /Count {len(page_texts)} >>"
        ).encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for index, text in enumerate(page_texts):
        page_id = 4 + 2 * index
        content_id = 5 + 2 * index
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 24 Tf 72 720 Td ({escaped}) Tj ET".encode()
        objects[content_id] = (
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )

    output = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for object_id in sorted(objects):
        offsets[object_id] = len(output)
        output += f"{object_id} 0 obj\n".encode() + objects[object_id] + b"\nendobj\n"
    xref = len(output)
    size = max(objects) + 1
    output += f"xref\n0 {size}\n".encode()
    output += b"0000000000 65535 f \n"
    for object_id in range(1, size):
        output += f"{offsets[object_id]:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def _write_pdf(path: Path, page_texts: list[str]) -> Path:
    path.write_bytes(_make_pdf(page_texts))
    return path


def _make_docx_bytes(
    paragraphs: list[str], table: list[list[str]] | None = None
) -> bytes:
    import docx

    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    if table:
        created = document.add_table(rows=len(table), cols=len(table[0]))
        for row_index, row in enumerate(table):
            for column_index, value in enumerate(row):
                created.cell(row_index, column_index).text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _make_xlsx_bytes(sheets: list[tuple[str, list[list[object]]]]) -> bytes:
    import openpyxl

    workbook = openpyxl.Workbook()
    default = workbook.active
    for index, (name, rows) in enumerate(sheets):
        worksheet = default if index == 0 else workbook.create_sheet()
        worksheet.title = name
        for row in rows:
            worksheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class FakeResponse:
    def __init__(
        self,
        body: bytes = b"",
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        redirect: bool = False,
        chunks: list[bytes] | None = None,
    ) -> None:
        self._body = body
        self.status_code = status
        self.headers = headers or {}
        self._redirect = redirect
        self._chunks = chunks
        self.closed = False

    @property
    def is_redirect(self) -> bool:
        return self._redirect

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def iter_content(self, chunk_size: int = 16_384):
        if self._chunks is not None:
            yield from self._chunks
            return
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start : start + chunk_size]

    def close(self) -> None:
        self.closed = True


# --------------------------------------------------------------- local files --
def test_parse_txt_file_metadata(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_text("hello world", encoding="utf-8")

    result = document_parse(str(path))

    assert result["format"] == "txt"
    assert result["text"] == "hello world"
    assert result["truncated"] is False
    metadata = result["metadata"]
    assert metadata["source_kind"] == "file"
    assert metadata["path"] == str(path)
    assert metadata["size_bytes"] == 11
    assert metadata["format"] == "txt"


def test_parse_md_by_extension(tmp_path: Path) -> None:
    path = tmp_path / "readme.md"
    path.write_text("# Title\n\nBody", encoding="utf-8")
    result = document_parse(str(path))
    assert result["format"] == "md"
    assert "# Title" in result["text"]


@pytest.mark.parametrize("suffix", [".md", ".markdown", ".txt"])
def test_text_formats_by_extension(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / f"doc{suffix}"
    path.write_text("content", encoding="utf-8")
    assert document_parse(str(path))["format"] in {"md", "txt"}


def test_parse_json_valid_is_pretty_printed(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_text('{"b": 1, "a": "\\u4e2d"}', encoding="utf-8")

    result = document_parse(str(path))

    assert result["format"] == "json"
    assert result["text"] == json.dumps(
        {"b": 1, "a": "中"}, ensure_ascii=False, indent=2
    )
    assert result["metadata"]["valid_json"] is True


def test_parse_invalid_json_falls_back_to_text(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    result = document_parse(str(path))
    assert result["format"] == "json"
    assert result["text"] == "{not json"
    assert result["metadata"]["valid_json"] is False


def test_parse_csv_sniffs_semicolon_delimiter(tmp_path: Path) -> None:
    path = tmp_path / "table.csv"
    path.write_text("a;b\n1;2\n", encoding="utf-8")

    result = document_parse(str(path))

    assert result["format"] == "csv"
    assert result["text"] == "a\tb\n1\t2"
    assert result["metadata"]["delimiter"] == ";"
    assert result["metadata"]["rows"] == 2


def test_parse_csv_falls_back_to_comma(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_error(self, sample):
        raise csv.Error("cannot sniff")

    monkeypatch.setattr(csv.Sniffer, "sniff", raise_error)
    path = tmp_path / "table.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")

    result = document_parse(str(path))

    assert result["text"] == "a\tb\n1\t2"
    assert result["metadata"]["delimiter"] == ","


def test_parse_csv_row_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(document_parse_module, "_MAX_CSV_ROWS", 1)
    path = tmp_path / "table.csv"
    path.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    result = document_parse(str(path))
    assert result["text"] == "a\tb"
    assert result["metadata"]["rows"] == 1


def test_parse_html_uses_trafilatura(tmp_path: Path) -> None:
    path = tmp_path / "page.html"
    path.write_text(
        "<html><body><article><p>Readable body content.</p></article></body></html>",
        encoding="utf-8",
    )
    result = document_parse(str(path))
    assert result["format"] == "html"
    assert "Readable body content." in result["text"]
    assert result["metadata"]["extraction"] in {"trafilatura", "fallback"}


def test_parse_html_fallback_strips_tags_and_scripts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import trafilatura

    monkeypatch.setattr(trafilatura, "extract", lambda text: None)
    path = tmp_path / "page.html"
    path.write_text(
        "<html><head><style>.x{}</style></head><body>"
        "<script>secret()</script><p>Hello &amp; bye</p></body></html>",
        encoding="utf-8",
    )

    result = document_parse(str(path))

    assert result["metadata"]["extraction"] == "fallback"
    assert "Hello & bye" in result["text"]
    assert "secret" not in result["text"]
    assert ".x{}" not in result["text"]


def test_parse_html_fallback_when_extractor_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import trafilatura

    def explode(text):
        raise RuntimeError("boom")

    monkeypatch.setattr(trafilatura, "extract", explode)
    path = tmp_path / "page.html"
    path.write_text("<html><body><p>Fallback</p></body></html>", encoding="utf-8")

    result = document_parse(str(path))

    assert result["text"] == "Fallback"
    assert result["metadata"]["extraction"] == "fallback"


def test_parse_empty_text_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_bytes(b"")
    result = document_parse(str(path))
    assert result == {
        "format": "txt",
        "text": "",
        "truncated": False,
        "metadata": {
            "source_kind": "file",
            "path": str(path),
            "size_bytes": 0,
            "format": "txt",
        },
    }


def test_truncation_sets_flag_and_caps_length(tmp_path: Path) -> None:
    path = tmp_path / "long.txt"
    path.write_text("a" * 1_500, encoding="utf-8")

    result = document_parse(str(path), max_chars=1_000)

    assert result["truncated"] is True
    assert len(result["text"]) == 1_000


def test_exact_length_is_not_truncated(tmp_path: Path) -> None:
    path = tmp_path / "exact.txt"
    path.write_text("b" * 1_000, encoding="utf-8")
    assert document_parse(str(path), max_chars=1_000)["truncated"] is False


@pytest.mark.parametrize("max_chars", [999, 1_000_001, True, "1000", None, 1.5])
def test_invalid_max_chars_returns_error(max_chars: object) -> None:
    result = document_parse("anything", max_chars=max_chars)  # type: ignore[arg-type]
    assert "error" in result


def test_missing_file_returns_error(tmp_path: Path) -> None:
    result = document_parse(str(tmp_path / "nope.txt"))
    assert "error" in result
    assert "not found" in result["error"]


@pytest.mark.parametrize("source", ["", "   ", None, 123])
def test_invalid_source_returns_error(source: object) -> None:
    result = document_parse(source)  # type: ignore[arg-type]
    assert "error" in result


def test_unsupported_explicit_format_returns_error(tmp_path: Path) -> None:
    path = tmp_path / "x.txt"
    path.write_text("x", encoding="utf-8")
    result = document_parse(str(path), format="xml")
    assert "error" in result
    assert "unsupported format" in result["error"]


def test_non_string_explicit_format_returns_error(tmp_path: Path) -> None:
    path = tmp_path / "x.txt"
    path.write_text("x", encoding="utf-8")
    result = document_parse(str(path), format=123)  # type: ignore[arg-type]
    assert "unsupported format" in result["error"]


def test_format_override_wins_over_extension(tmp_path: Path) -> None:
    path = tmp_path / "data.txt"
    path.write_text('{"a": 1}', encoding="utf-8")
    result = document_parse(str(path), format="json")
    assert result["format"] == "json"
    assert result["metadata"]["valid_json"] is True


def test_format_alias_is_normalized(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"
    path.write_text("body", encoding="utf-8")
    result = document_parse(str(path), format="markdown")
    assert result["format"] == "md"


def test_filetype_detects_format_without_extension(tmp_path: Path) -> None:
    path = tmp_path / "blob.bin"
    path.write_bytes(_make_docx_bytes(["hello"]))

    result = document_parse(str(path))

    assert result["format"] == "docx"
    assert result["text"] == "hello"


def test_unknown_bytes_fall_back_to_text(tmp_path: Path) -> None:
    path = tmp_path / "blob.bin"
    path.write_bytes(b"\x00\x01random bytes")
    result = document_parse(str(path))
    assert result["format"] == "txt"


def test_detected_but_unsupported_binary_falls_back_to_text(tmp_path: Path) -> None:
    import base64

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    path = tmp_path / "image.bin"
    path.write_bytes(png)
    assert document_parse(str(path))["format"] == "txt"


def test_read_failure_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "denied.txt"
    path.write_text("x", encoding="utf-8")

    def explode(self):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_bytes", explode)

    result = document_parse(str(path))

    assert "failed to read file" in result["error"]


def test_filetype_error_falls_back_to_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(data):
        raise RuntimeError("detector failed")

    monkeypatch.setattr(document_parse_module.filetype, "guess", explode)
    path = tmp_path / "blob.bin"
    path.write_bytes(b"plain text")
    result = document_parse(str(path))
    assert result["format"] == "txt"


def test_detection_failure_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(document_parse_module, "_detect_format", explode)
    path = tmp_path / "blob.txt"
    path.write_text("x", encoding="utf-8")
    result = document_parse(str(path))
    assert result["error"].startswith("failed to parse document")


# --------------------------------------------------------------------- docx --
def test_parse_docx_paragraphs_and_tables(tmp_path: Path) -> None:
    import docx

    document = docx.Document()
    document.add_paragraph("First")
    table = document.add_table(rows=2, cols=2)
    for row_index, row in enumerate([["a", "b"], ["c", "d"]]):
        for column_index, value in enumerate(row):
            table.cell(row_index, column_index).text = value
    document.add_paragraph("After")
    buffer = io.BytesIO()
    document.save(buffer)

    path = tmp_path / "report.docx"
    path.write_bytes(buffer.getvalue())

    result = document_parse(str(path))

    assert result["format"] == "docx"
    assert result["text"] == "First\n\na | b\nc | d\n\nAfter"
    assert result["metadata"]["paragraphs"] == 2
    assert result["metadata"]["tables"] == 1


def test_corrupt_docx_returns_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not a zip archive")
    result = document_parse(str(path))
    assert result["error"].startswith("failed to parse docx")


# --------------------------------------------------------------------- xlsx --
def test_parse_xlsx_sheets_and_rows(tmp_path: Path) -> None:
    path = tmp_path / "book.xlsx"
    path.write_bytes(
        _make_xlsx_bytes(
            [
                ("Alpha", [["a", "b"], [1, 2]]),
                ("Beta", [["c"]]),
            ]
        )
    )

    result = document_parse(str(path))

    assert result["format"] == "xlsx"
    assert result["text"] == "## Alpha\na\tb\n1\t2\n## Beta\nc"
    assert result["metadata"]["sheets"] == ["Alpha", "Beta"]
    assert result["metadata"]["total_rows"] == 3


def test_parse_xlsx_caps_sheets_and_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(document_parse_module, "_MAX_XLSX_SHEETS", 1)
    monkeypatch.setattr(document_parse_module, "_MAX_XLSX_ROWS_PER_SHEET", 1)
    path = tmp_path / "book.xlsx"
    path.write_bytes(
        _make_xlsx_bytes(
            [
                ("Alpha", [["a"], ["b"]]),
                ("Beta", [["c"]]),
            ]
        )
    )

    result = document_parse(str(path))

    assert result["text"] == "## Alpha\na"
    assert result["metadata"]["sheets"] == ["Alpha"]
    assert result["metadata"]["total_rows"] == 1


def test_corrupt_xlsx_returns_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.xlsx"
    path.write_bytes(b"not a workbook")
    result = document_parse(str(path))
    assert result["error"].startswith("failed to parse xlsx")


# ---------------------------------------------------------------------- pdf --
def test_parse_pdf_multiple_pages(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path / "doc.pdf", ["First page", "Second page"])

    result = document_parse(str(path))

    assert result["format"] == "pdf"
    assert result["text"] == "First page\n\nSecond page"
    assert result["metadata"]["pages"] == 2
    assert result["metadata"]["needs_ocr"] is False


def test_parse_pdf_without_text_sets_needs_ocr(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path / "scan.pdf", [""])

    result = document_parse(str(path))

    assert result["text"] == ""
    assert result["metadata"]["pages"] == 1
    assert result["metadata"]["needs_ocr"] is True


def test_parse_pdf_blank_pages_do_not_set_needs_ocr_when_text_exists(
    tmp_path: Path,
) -> None:
    path = _write_pdf(tmp_path / "mixed.pdf", ["text", ""])
    result = document_parse(str(path))
    assert result["metadata"]["needs_ocr"] is False


def test_corrupt_pdf_returns_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4 definitely broken")
    result = document_parse(str(path))
    assert result["error"].startswith("failed to parse pdf")


# --------------------------------------------------------------------- URLs --
def test_url_download_success(monkeypatch: pytest.MonkeyPatch) -> None:
    checked: list[str] = []
    response = FakeResponse(b"remote text")

    monkeypatch.setattr(
        document_parse_module, "assert_public_url", lambda url: checked.append(url)
    )
    monkeypatch.setattr(document_parse_module.requests, "get", lambda *a, **k: response)

    result = document_parse("https://example.com/file", format="txt")

    assert result["format"] == "txt"
    assert result["text"] == "remote text"
    assert result["metadata"]["source_kind"] == "url"
    assert result["metadata"]["url"] == "https://example.com/file"
    assert result["metadata"]["requested_url"] == "https://example.com/file"
    assert result["metadata"]["size_bytes"] == 11
    assert checked == ["https://example.com/file"]
    assert response.closed is True


def test_url_redirect_is_revalidated_and_detected_by_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[str] = []
    responses = [
        FakeResponse(redirect=True, headers={"location": "/next.csv"}),
        FakeResponse(b"a,b\n1,2\n"),
    ]

    def fake_get(*args, **kwargs):
        assert kwargs["allow_redirects"] is False
        return responses.pop(0)

    monkeypatch.setattr(
        document_parse_module, "assert_public_url", lambda url: checked.append(url)
    )
    monkeypatch.setattr(document_parse_module.requests, "get", fake_get)

    result = document_parse("https://example.com/start")

    assert checked == [
        "https://example.com/start",
        "https://example.com/next.csv",
    ]
    assert result["format"] == "csv"
    assert result["text"] == "a\tb\n1\t2"
    assert result["metadata"]["url"] == "https://example.com/next.csv"


def test_url_redirect_to_private_host_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = FakeResponse(redirect=True, headers={"location": "http://127.0.0.1/x"})

    def guard(url: str) -> str:
        if "127.0.0.1" in url:
            raise ValueError("Blocked non-public address")
        return "example.com"

    monkeypatch.setattr(document_parse_module, "assert_public_url", guard)
    monkeypatch.setattr(document_parse_module.requests, "get", lambda *a, **k: response)

    result = document_parse("https://example.com/start")

    assert result == {"error": "Blocked non-public address"}


def test_url_too_many_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        FakeResponse(redirect=True, headers={"location": f"/hop{i}"}) for i in range(4)
    ]
    monkeypatch.setattr(
        document_parse_module, "assert_public_url", lambda url: "example.com"
    )
    monkeypatch.setattr(
        document_parse_module.requests, "get", lambda *a, **k: responses.pop(0)
    )

    result = document_parse("https://example.com/start")

    assert "too many redirects" in result["error"]


def test_url_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    response = FakeResponse(status=404)
    monkeypatch.setattr(
        document_parse_module, "assert_public_url", lambda url: "example.com"
    )
    monkeypatch.setattr(document_parse_module.requests, "get", lambda *a, **k: response)

    result = document_parse("https://example.com/missing")

    assert result == {"error": "HTTP 404"}
    assert response.closed is True


def test_url_request_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    def explode(*args, **kwargs):
        raise requests.RequestException("connection reset")

    monkeypatch.setattr(
        document_parse_module, "assert_public_url", lambda url: "example.com"
    )
    monkeypatch.setattr(document_parse_module.requests, "get", explode)

    result = document_parse("https://example.com/start")

    assert "download failed" in result["error"]


def test_url_download_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(document_parse_module, "_MAX_DOWNLOAD_BYTES", 10)
    response = FakeResponse(chunks=[b"", b"x" * 8, b"y" * 8])
    monkeypatch.setattr(
        document_parse_module, "assert_public_url", lambda url: "example.com"
    )
    monkeypatch.setattr(document_parse_module.requests, "get", lambda *a, **k: response)

    result = document_parse("https://example.com/big", format="txt")

    assert result["text"] == "xxxxxxxxyy"
    assert result["metadata"]["size_bytes"] == 10


def test_url_private_address_is_rejected_before_request() -> None:
    result = document_parse("http://127.0.0.1/secret.txt")
    assert "error" in result
    assert result["error"]


def test_url_unsupported_explicit_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        document_parse_module, "assert_public_url", lambda url: "example.com"
    )
    monkeypatch.setattr(
        document_parse_module.requests,
        "get",
        lambda *a, **k: FakeResponse(b"data"),
    )
    result = document_parse("https://example.com/x", format="xml")
    assert "unsupported format" in result["error"]


# ------------------------------------------------- URL format detection --
def test_url_content_type_detects_html_without_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b"<!doctype html><html><body><p>Hello page</p></body></html>"
    response = FakeResponse(body, headers={"content-type": "text/html; charset=utf-8"})
    monkeypatch.setattr(
        document_parse_module, "assert_public_url", lambda url: "example.com"
    )
    monkeypatch.setattr(document_parse_module.requests, "get", lambda *a, **k: response)

    result = document_parse("https://example.com/page")

    assert result["format"] == "html"
    assert "Hello page" in result["text"]
    assert "<p>" not in result["text"]
    assert result["metadata"]["content_type"] == "text/html; charset=utf-8"


def test_url_content_type_detects_json(monkeypatch: pytest.MonkeyPatch) -> None:
    response = FakeResponse(b'{"a": 1}', headers={"content-type": "application/json"})
    monkeypatch.setattr(
        document_parse_module, "assert_public_url", lambda url: "example.com"
    )
    monkeypatch.setattr(document_parse_module.requests, "get", lambda *a, **k: response)

    result = document_parse("https://example.com/api/data")

    assert result["format"] == "json"
    assert result["metadata"]["valid_json"] is True
    assert json.loads(result["text"]) == {"a": 1}


def test_url_html_is_sniffed_without_content_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = FakeResponse(b"<!DOCTYPE html>\n<html><body>plain</body></html>")
    monkeypatch.setattr(
        document_parse_module, "assert_public_url", lambda url: "example.com"
    )
    monkeypatch.setattr(document_parse_module.requests, "get", lambda *a, **k: response)

    result = document_parse("https://example.com/")

    assert result["format"] == "html"
    assert "plain" in result["text"]
    assert "content_type" not in result["metadata"]


def test_url_explicit_format_wins_over_content_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = FakeResponse(
        b"<html><body>raw</body></html>",
        headers={"content-type": "text/html"},
    )
    monkeypatch.setattr(
        document_parse_module, "assert_public_url", lambda url: "example.com"
    )
    monkeypatch.setattr(document_parse_module.requests, "get", lambda *a, **k: response)

    result = document_parse("https://example.com/page", format="txt")

    assert result["format"] == "txt"
    assert result["text"] == "<html><body>raw</body></html>"


def test_url_suffix_wins_over_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    response = FakeResponse(b"a,b\n1,2\n", headers={"content-type": "text/html"})
    monkeypatch.setattr(
        document_parse_module, "assert_public_url", lambda url: "example.com"
    )
    monkeypatch.setattr(document_parse_module.requests, "get", lambda *a, **k: response)

    result = document_parse("https://example.com/table.csv")

    assert result["format"] == "csv"
    assert result["text"] == "a\tb\n1\t2"


def test_url_unknown_content_type_falls_back_to_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = FakeResponse(
        b"plain words", headers={"content-type": "application/octet-stream"}
    )
    monkeypatch.setattr(
        document_parse_module, "assert_public_url", lambda url: "example.com"
    )
    monkeypatch.setattr(document_parse_module.requests, "get", lambda *a, **k: response)

    result = document_parse("https://example.com/blob")

    assert result["format"] == "txt"
    assert result["text"] == "plain words"
