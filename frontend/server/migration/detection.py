"""Deterministic, model-free detection of an uploaded migration source.

Studio runs this inside its own process, on the archived bytes, before Codex ever
sees the project.  Two things depend on it:

* the analysis prompt receives the file inventory and the DSL families that were
  recognised on disk, so Codex does not have to rediscover them by running shell
  commands, and
* the destructive ``unsupported`` verdict is checked against a file inventory that
  no model produced.

It is deliberately coarse.  It recognises the DSL families the migration CLI can
replay, reports the file inventory verbatim, and records everything it could not
read instead of dropping it silently.  When a parser is unavailable the report says
so, so a missing dependency can never look like "the project contains nothing".
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

SCHEMA_VERSION = 1

# A report is an input to a prompt and to a verdict check, never a data transfer, so
# the inventory is capped while ``count`` stays exact.
_MAX_LISTED_FILES = 200
_MAX_INSPECTED_FILES = 200
_MAX_INSPECT_BYTES = 256 * 1024
_INSPECT_SUFFIXES = (".yml", ".yaml")
_SKIP_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
}
_METADATA_PREFIXES = ("__MACOSX/",)
_METADATA_NAMES = (".DS_Store",)

_DIFY_DSL = "dify"


def detect_source(content: bytes) -> dict[str, object]:
    """Return the detection report for one validated source archive."""
    unreadable: list[dict[str, str]] = []
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        # Upload validation runs first, so this is an internal inconsistency rather
        # than user input; report it instead of raising so analysis can continue.
        return _report(
            count=0,
            listed=[],
            documents=[],
            candidates=[],
            unreadable=[{"path": "", "reason": "archive_unreadable"}],
            degraded_reason="archive_unreadable",
        )
    with archive:
        names = _file_names(archive)
        count = len(names)
        listed = names[:_MAX_LISTED_FILES]
        documents: list[dict[str, object]] = []
        candidates: list[dict[str, object]] = []
        for name in names[:_MAX_INSPECTED_FILES]:
            if not name.lower().endswith(_INSPECT_SUFFIXES):
                continue
            try:
                info = archive.getinfo(name)
            except KeyError:
                continue
            if info.file_size > _MAX_INSPECT_BYTES:
                unreadable.append({"path": name, "reason": "too_large"})
                continue
            try:
                text = archive.read(name).decode("utf-8-sig")
            except (UnicodeDecodeError, OSError, zipfile.BadZipFile):
                unreadable.append({"path": name, "reason": "decode_failed"})
                continue
            document = _inspect_document(name, text)
            documents.append(document)
            candidate = _candidate(document)
            if candidate is not None:
                candidates.append(candidate)
    return _report(
        count=count,
        listed=listed,
        documents=documents,
        candidates=candidates,
        unreadable=unreadable,
        degraded_reason="",
    )


def _report(
    *,
    count: int,
    listed: list[str],
    documents: list[dict[str, object]],
    candidates: list[dict[str, object]],
    unreadable: list[dict[str, str]],
    degraded_reason: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "files": {"count": count, "listed": listed},
        "documents": documents,
        "candidates": candidates,
        "unreadable": unreadable,
        "degraded": bool(degraded_reason),
        "degraded_reason": degraded_reason,
    }


def _file_names(archive: zipfile.ZipFile) -> list[str]:
    names: list[str] = []
    for info in archive.infolist():
        name = info.filename
        if info.is_dir() or not name:
            continue
        if (
            name.startswith(_METADATA_PREFIXES)
            or name.rsplit("/", 1)[-1] in _METADATA_NAMES
        ):
            continue
        parts = name.split("/")
        if any(part in _SKIP_DIRECTORIES for part in parts[:-1]):
            continue
        names.append(name)
    names.sort()
    return names


def _inspect_document(path: str, text: str) -> dict[str, object]:
    document: dict[str, object] = {
        "path": path,
        "format": "yaml",
        "status": "parsed",
        "dsl": "",
        "signals": [],
    }
    payload: Any = None
    parse_error = ""
    try:
        import yaml
    except ImportError:
        document["status"] = "unparsed"
        document["parse_error"] = "yaml_unavailable"
        return document
    try:
        payload = yaml.safe_load(text)
    except Exception:  # noqa: BLE001 - any parser failure is a report fact, never fatal
        parse_error = "yaml_invalid"
    if parse_error or not isinstance(payload, dict):
        document["status"] = "unparsed"
        document["parse_error"] = parse_error or "not_a_mapping"
        return document
    signals = _dsl_signals(payload, text)
    if signals:
        document["dsl"] = _DIFY_DSL
        document["signals"] = signals
    return document


def _dsl_signals(payload: dict[object, object], text: str) -> list[dict[str, object]]:
    """Recognise the Dify/Bailian DSL export the migration CLI can replay."""
    if str(payload.get("kind") or "").strip().lower() != "app":
        return []
    app = payload.get("app")
    workflow = payload.get("workflow")
    if not isinstance(app, dict) or not isinstance(workflow, dict):
        return []
    mode = str(app.get("mode") or "").strip()
    graph = workflow.get("graph")
    if not mode or not isinstance(graph, dict):
        return []
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return []
    return [
        {
            "path": "",
            "line": _line_of(text, "kind:"),
            "reason": "顶层 kind: app",
        },
        {
            "path": "",
            "line": _line_of(text, "mode:"),
            "reason": f"app.mode: {mode}",
        },
        {
            "path": "",
            "line": _line_of(text, "graph:"),
            "reason": f"workflow.graph 含 {len(nodes)} 个节点、{len(edges)} 条边",
        },
    ]


def _candidate(document: dict[str, object]) -> dict[str, object] | None:
    if document.get("dsl") != _DIFY_DSL:
        return None
    path = str(document.get("path") or "")
    signals = document.get("signals")
    evidence = [
        {
            "path": path,
            "line": int(signal.get("line") or 1),
            "reason": str(signal.get("reason") or ""),
        }
        for signal in signals
        if isinstance(signal, dict)
    ]
    return {"id": _DIFY_DSL, "confidence": "high", "evidence": evidence}


def _line_of(text: str, token: str) -> int:
    for index, line in enumerate(text.splitlines(), start=1):
        if token in line:
            return index
    return 1


__all__ = ["SCHEMA_VERSION", "detect_source"]
