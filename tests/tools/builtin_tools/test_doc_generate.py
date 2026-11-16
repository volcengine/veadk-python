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
from pathlib import Path

import pytest

from veadk.tools.builtin_tools import doc_generate as doc_generate_module
from veadk.tools.builtin_tools.doc_generate import doc_generate


class SaveContext:
    def __init__(self, failures: int = 0) -> None:
        self.artifacts: list[tuple[str, object]] = []
        self.failures = failures

    async def save_artifact(self, filename: str, artifact: object) -> int:
        if self.failures:
            self.failures -= 1
            raise RuntimeError("storage unavailable")
        self.artifacts.append((filename, artifact))
        return len(self.artifacts)


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# --------------------------------------------------------------------- docx --
@pytest.mark.asyncio
async def test_docx_writes_temp_file_with_light_markdown(tmp_path: Path) -> None:
    content = (
        "# Heading One\n"
        "first line\n"
        "second line\n"
        "\n"
        "- **bold** item\n"
        "* star item\n"
        "+ plus item\n"
        "\n"
        "#### raw heading\n"
        "\n"
        "plain __em__ text\n"
        "## Heading Two\n"
        "### Heading Three\n"
    )

    result = await doc_generate(
        "docx",
        "My Title",
        content=content,
        filename="report",
        tool_context=None,
    )

    assert result["filename"] == "report.docx"
    assert result["format"] == "docx"
    assert result["mime_type"] == DOCX_MIME
    assert result["artifact_saved"] is False
    path = Path(result["path"])
    assert path.is_file()
    assert path.stat().st_size == result["size_bytes"]

    import docx

    document = docx.Document(str(path))
    paragraphs = [(p.text, p.style.name) for p in document.paragraphs]
    assert paragraphs == [
        ("My Title", "Title"),
        ("Heading One", "Heading 1"),
        ("first line second line", "Normal"),
        ("bold item", "List Bullet"),
        ("star item", "List Bullet"),
        ("plus item", "List Bullet"),
        ("raw heading", "Normal"),
        ("plain em text", "Normal"),
        ("Heading Two", "Heading 2"),
        ("Heading Three", "Heading 3"),
    ]


@pytest.mark.asyncio
async def test_docx_saves_artifact() -> None:
    context = SaveContext()

    result = await doc_generate(
        " DOCX ",
        "Title",
        content="body **text**",
        filename="notes",
        tool_context=context,  # type: ignore[arg-type]
    )

    assert result["artifact_saved"] is True
    assert result["path"] is None
    assert result["filename"] == "notes.docx"
    assert len(context.artifacts) == 1
    name, artifact = context.artifacts[0]
    assert name == "notes.docx"
    assert artifact.inline_data.mime_type == DOCX_MIME
    assert artifact.inline_data.display_name == "notes.docx"
    assert len(artifact.inline_data.data) == result["size_bytes"]


@pytest.mark.asyncio
async def test_docx_default_filename_and_empty_content() -> None:
    result = await doc_generate("docx", "", tool_context=None)
    assert result["filename"] == "document.docx"
    assert result["size_bytes"] > 0


@pytest.mark.asyncio
async def test_docx_handles_none_content() -> None:
    result = await doc_generate("docx", "Title", content=None, tool_context=None)  # type: ignore[arg-type]
    assert result["artifact_saved"] is False


@pytest.mark.asyncio
async def test_artifact_save_failure_returns_error() -> None:
    result = await doc_generate(
        "docx",
        "Title",
        tool_context=SaveContext(failures=1),  # type: ignore[arg-type]
    )
    assert "error" in result
    assert "failed to save artifact" in result["error"]


# --------------------------------------------------------------------- xlsx --
@pytest.mark.asyncio
async def test_xlsx_writes_sheets_with_bold_header_and_widths() -> None:
    import openpyxl

    sheets = [
        {"name": "Data", "rows": [["Name", "Age"], ["Alice", 30], ["x" * 100, None]]}
    ]

    result = await doc_generate("xlsx", "Ignored", sheets=sheets, tool_context=None)

    assert result["filename"] == "document.xlsx"
    assert result["mime_type"] == XLSX_MIME
    workbook = openpyxl.load_workbook(result["path"])
    worksheet = workbook["Data"]
    assert worksheet["A1"].value == "Name"
    assert worksheet["A1"].font.bold is True
    assert worksheet["B1"].font.bold is True
    assert worksheet["B2"].value == 30
    assert worksheet["B3"].value is None
    assert 8 <= worksheet.column_dimensions["A"].width <= 60
    assert worksheet.column_dimensions["A"].width == 60


@pytest.mark.asyncio
async def test_xlsx_creates_multiple_unique_sheets() -> None:
    import openpyxl

    sheets = [
        {"name": "Same", "rows": [["a"]]},
        {"name": "Same", "rows": [["b"]]},
        {"name": "Same", "rows": [["c"]]},
        {"name": "Bad/Name:*?[]", "rows": []},
        {"name": "   ", "rows": []},
    ]

    result = await doc_generate("xlsx", "", sheets=sheets, tool_context=None)

    workbook = openpyxl.load_workbook(result["path"])
    assert workbook.sheetnames == [
        "Same",
        "Same_2",
        "Same_3",
        "Bad Name",
        "Sheet5",
    ]


@pytest.mark.asyncio
async def test_xlsx_enforces_sheet_row_and_column_caps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import openpyxl

    monkeypatch.setattr(doc_generate_module, "_MAX_SHEETS", 1)
    monkeypatch.setattr(doc_generate_module, "_MAX_ROWS_PER_SHEET", 1)
    monkeypatch.setattr(doc_generate_module, "_MAX_COLUMNS", 2)
    sheets = [
        {"name": "One", "rows": [["a", "b", "c"], ["d", "e", "f"]]},
        {"name": "Two", "rows": [["g"]]},
    ]

    result = await doc_generate("xlsx", "", sheets=sheets, tool_context=None)

    workbook = openpyxl.load_workbook(result["path"])
    assert workbook.sheetnames == ["One"]
    worksheet = workbook["One"]
    assert worksheet.max_row == 1
    assert worksheet.max_column == 2


@pytest.mark.asyncio
async def test_xlsx_converts_non_basic_cell_values() -> None:
    import openpyxl

    result = await doc_generate(
        "xlsx",
        "",
        sheets=[{"name": "S", "rows": [[{"a": 1}]]}],
        tool_context=None,
    )

    workbook = openpyxl.load_workbook(result["path"])
    assert workbook["S"]["A1"].value == "{'a': 1}"


@pytest.mark.asyncio
async def test_xlsx_writes_formula_like_cells_as_text() -> None:
    import openpyxl

    result = await doc_generate(
        "xlsx",
        "",
        sheets=[
            {
                "name": "S",
                "rows": [
                    ["=1+1", "+1", "-1", "@SUM(A1)", "\r=cmd", "safe"],
                    [1, -2, 3.5, True, None, "x"],
                ],
            }
        ],
        tool_context=None,
    )

    workbook = openpyxl.load_workbook(result["path"], data_only=False)
    worksheet = workbook["S"]
    for column in ("A1", "B1", "C1", "D1", "E1"):
        assert worksheet[column].value.startswith(("=", "+", "-", "@", "\r"))
        assert worksheet[column].data_type == "s"
    assert worksheet["F1"].value == "safe"
    # Numbers and booleans keep their native type.
    assert worksheet["A2"].value == 1
    assert worksheet["B2"].value == -2
    assert worksheet["D2"].value is True


@pytest.mark.asyncio
async def test_xlsx_truncation_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doc_generate_module, "_MAX_COLUMNS", 1)
    result = await doc_generate(
        "xlsx",
        "",
        sheets=[{"name": "S", "rows": [["a", "b"]]}],
        tool_context=None,
    )
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_docx_and_md_are_never_truncated() -> None:
    docx_result = await doc_generate("docx", "T", content="body", tool_context=None)
    md_result = await doc_generate("md", "T", content="body", tool_context=None)
    assert docx_result["truncated"] is False
    assert md_result["truncated"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sheets",
    [
        None,
        [],
        "not-a-list",
        [object()],
        [{"name": "S"}],
        [{"name": "S", "rows": "nope"}],
        [{"name": 3, "rows": []}],
        [{"name": "S", "rows": ["nope"]}],
    ],
)
async def test_xlsx_invalid_sheets_return_error(sheets: object) -> None:
    result = await doc_generate(
        "xlsx",
        "",
        sheets=sheets,  # type: ignore[arg-type]
        tool_context=None,
    )
    assert "error" in result


# ---------------------------------------------------------------------- csv --
@pytest.mark.asyncio
async def test_csv_rows_are_written_as_utf8() -> None:
    result = await doc_generate(
        "csv",
        "",
        rows=[["name", "note"], [1, None], ["中文", "ok"]],
        filename="export",
        tool_context=None,
    )

    assert result["filename"] == "export.csv"
    assert result["mime_type"] == "text/csv"
    text = Path(result["path"]).read_bytes().decode("utf-8")
    assert text.startswith("name,note")
    assert list(csv.reader(io.StringIO(text))) == [
        ["name", "note"],
        ["1", ""],
        ["中文", "ok"],
    ]


@pytest.mark.asyncio
async def test_csv_content_is_used_when_rows_missing() -> None:
    content = "a,b\n1,2\n"
    result = await doc_generate("csv", "", content=content, tool_context=None)
    assert Path(result["path"]).read_bytes() == content.encode("utf-8")


@pytest.mark.asyncio
async def test_csv_requires_rows_or_content() -> None:
    result = await doc_generate("csv", "", tool_context=None)
    assert "error" in result


@pytest.mark.asyncio
async def test_csv_invalid_rows() -> None:
    result = await doc_generate("csv", "", rows="nope", tool_context=None)  # type: ignore[arg-type]
    assert "error" in result


@pytest.mark.asyncio
async def test_csv_invalid_row_item() -> None:
    result = await doc_generate("csv", "", rows=["nope"], tool_context=None)  # type: ignore[list-item]
    assert "error" in result


@pytest.mark.asyncio
async def test_csv_row_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doc_generate_module, "_MAX_CSV_ROWS", 1)
    result = await doc_generate(
        "csv",
        "",
        rows=[["a"], ["b"], ["c"]],
        tool_context=None,
    )
    assert Path(result["path"]).read_bytes() == b"a\r\n"
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_csv_neutralizes_formula_cells() -> None:
    rows = [
        ["=1+1", "+1", "-1", "@SUM(A1)", "\t=cmd|'/C calc'!A0", "safe", " - note"],
    ]
    result = await doc_generate("csv", "", rows=rows, tool_context=None)

    parsed = list(
        csv.reader(io.StringIO(Path(result["path"]).read_text(encoding="utf-8")))
    )
    assert parsed == [
        [
            "'=1+1",
            "'+1",
            "'-1",
            "'@SUM(A1)",
            "'\t=cmd|'/C calc'!A0",
            "safe",
            " - note",
        ]
    ]


@pytest.mark.asyncio
async def test_csv_without_truncation_sets_flag_false() -> None:
    result = await doc_generate("csv", "", rows=[["a"]], tool_context=None)
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_csv_empty_rows_is_valid() -> None:
    result = await doc_generate("csv", "", rows=[], tool_context=None)
    assert result["size_bytes"] == 0


# ----------------------------------------------------------------------- md --
@pytest.mark.asyncio
async def test_md_prefixes_title_heading() -> None:
    result = await doc_generate("md", "My Title", content="Body", tool_context=None)
    assert Path(result["path"]).read_text(encoding="utf-8") == "# My Title\n\nBody"
    assert result["mime_type"] == "text/markdown"
    assert result["filename"] == "document.md"


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["# Existing\nbody", "  ## Existing\nbody"])
async def test_md_does_not_prefix_existing_heading(content: str) -> None:
    result = await doc_generate("md", "Title", content=content, tool_context=None)
    assert Path(result["path"]).read_text(encoding="utf-8") == content


@pytest.mark.asyncio
async def test_md_title_only() -> None:
    result = await doc_generate("md", "Title", content="", tool_context=None)
    assert Path(result["path"]).read_text(encoding="utf-8") == "# Title\n"


@pytest.mark.asyncio
async def test_md_empty_document() -> None:
    result = await doc_generate("md", "", content="", tool_context=None)
    assert result["size_bytes"] == 0


@pytest.mark.asyncio
async def test_md_saves_artifact() -> None:
    context = SaveContext()
    result = await doc_generate(
        "md",
        "T",
        content="body",
        filename="notes.txt",
        tool_context=context,  # type: ignore[arg-type]
    )
    assert result["artifact_saved"] is True
    assert result["path"] is None
    assert result["filename"] == "notes.md"
    name, artifact = context.artifacts[0]
    assert name == "notes.md"
    assert artifact.inline_data.mime_type == "text/markdown"


# ---------------------------------------------------------------- validation --
@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["pdf", "html", "", None, 123])
async def test_invalid_format_returns_error(fmt: object) -> None:
    result = await doc_generate(fmt, "t", tool_context=None)  # type: ignore[arg-type]
    assert "error" in result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "fmt", "expected"),
    [
        ("../../evil name!.txt", "docx", "evil-name.docx"),
        ("C:\\tmp\\report.docx", "docx", "report.docx"),
        ("report", "docx", "report.docx"),
        ("报告 final.md", "md", "报告-final.md"),
        ("archive.tar.gz", "csv", "archive.tar.csv"),
        ("   ", "csv", "document.csv"),
        ("!!!", "csv", "document.csv"),
        (None, "csv", "document.csv"),
        (123, "csv", "document.csv"),
    ],
)
async def test_filename_sanitization(filename: object, fmt: str, expected: str) -> None:
    result = await doc_generate(
        fmt,
        "",
        content="x" if fmt != "csv" else "",
        rows=[["x"]] if fmt == "csv" else None,
        filename=filename,  # type: ignore[arg-type]
        tool_context=None,
    )
    assert result["filename"] == expected


@pytest.mark.asyncio
async def test_long_filename_is_capped() -> None:
    result = await doc_generate(
        "md",
        "",
        content="x",
        filename="a" * 300 + ".md",
        tool_context=None,
    )
    assert len(result["filename"]) <= 120
    assert result["filename"].endswith(".md")


@pytest.mark.asyncio
async def test_non_string_title_and_content_are_coerced() -> None:
    result = await doc_generate("md", 123, content=456, tool_context=None)  # type: ignore[arg-type]
    text = Path(result["path"]).read_text(encoding="utf-8")
    assert text == "# 123\n\n456"


@pytest.mark.asyncio
async def test_none_title_is_treated_as_empty() -> None:
    result = await doc_generate("md", None, content="body", tool_context=None)  # type: ignore[arg-type]
    assert Path(result["path"]).read_text(encoding="utf-8") == "body"


@pytest.mark.asyncio
async def test_unexpected_build_failure_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(title: str, content: str) -> bytes:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(doc_generate_module, "_build_md", explode)

    result = await doc_generate("md", "T", content="body", tool_context=None)

    assert "failed to generate md" in result["error"]


@pytest.mark.asyncio
async def test_temp_file_write_failure_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        doc_generate_module.tempfile, "mkdtemp", lambda **kwargs: str(blocker)
    )

    result = await doc_generate("md", "T", content="body", tool_context=None)

    assert "error" in result
    assert "failed to write file" in result["error"]
