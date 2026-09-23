"""Model-free detection of an uploaded project.

The detector exists so the facts the analysis depends on - what files are there, and
which DSL family they are - do not come from a probabilistic model.  These tests pin
the two properties that matter: it recognises a real DSL export with real line numbers,
and it reports what it could not read instead of silently finding nothing.
"""

from __future__ import annotations

import io
import json
import zipfile

from frontend.server.migration.contracts import validate_detection_report
from frontend.server.migration.detection import detect_source

_BAILIAN_DSL = """app:
  mode: workflow
  name: test-workflow-agent
  subMode: chat
kind: app
version: 0.1.0
workflow:
  graph:
    edges:
    - id: Start-LLM
      source: Start_Q32E
      target: LLM_BOQl
    nodes:
    - id: Start_Q32E
      type: Start
    - id: LLM_BOQl
      type: LLM
    - id: End_OEI8
      type: End
"""


def _archive(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_a_dify_style_export_is_recognised_with_real_evidence() -> None:
    report = detect_source(_archive({"template.yml": _BAILIAN_DSL, "md5.txt": "abc"}))

    assert validate_detection_report(report) == report
    assert report["files"] == {"count": 2, "listed": ["md5.txt", "template.yml"]}
    assert report["degraded"] is False
    candidate = report["candidates"][0]
    assert candidate["id"] == "dify"
    assert candidate["confidence"] == "high"
    # 行号来自真实文件内容，模型看不到的细节由 Studio 提供。
    assert [item["line"] for item in candidate["evidence"]] == [5, 2, 8]
    assert all(item["path"] == "template.yml" for item in candidate["evidence"])
    assert "3 个节点" in candidate["evidence"][2]["reason"]


def test_a_project_without_a_known_dsl_reports_no_candidate() -> None:
    report = detect_source(
        _archive({"agent.py": "print('hi')\n", "requirements.txt": "veadk\n"})
    )

    assert report["candidates"] == []
    assert report["documents"] == []
    assert report["files"]["count"] == 2


def test_metadata_and_build_directories_are_not_part_of_the_inventory() -> None:
    report = detect_source(
        _archive(
            {
                "__MACOSX/._template.yml": "junk",
                ".DS_Store": "junk",
                "node_modules/pkg/index.js": "junk",
                ".git/config": "junk",
                "src/agent.py": "print('hi')\n",
            }
        )
    )

    assert report["files"] == {"count": 1, "listed": ["src/agent.py"]}


def test_unreadable_documents_are_reported_instead_of_dropped() -> None:
    report = detect_source(
        _archive({"broken.yml": "a: [unclosed\n", "late.yml": "kind: app\n"})
    )

    assert report["candidates"] == []
    document = next(
        item for item in report["documents"] if item["path"] == "broken.yml"
    )
    assert document["status"] == "unparsed"
    assert document["parse_error"] == "yaml_invalid"


def test_a_report_is_valid_json_for_a_missing_archive() -> None:
    report = detect_source(b"not a zip")

    assert report["degraded"] is True
    assert report["unreadable"] == [{"path": "", "reason": "archive_unreadable"}]
    assert validate_detection_report(report) == report
    assert json.dumps(report)
