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

"""The two ADK tools that bracket the sandbox: one imports data, one exports it.

Both demonstrate the rule that matters most when combining ADK tools with
``runtime="codex"``:

    **The workspace is the data plane; tool arguments and results are the
    control plane.**

A tool result does not go into a file — the runtime's shim executes the tool
and feeds its JSON result back to the model *as text in the prompt*. So a tool
that returns 40 CSV rows pays for them in tokens on that request and on every
later request of the turn, and a tool that returns 40 000 rows breaks the turn.
Instead, :func:`fetch_sales_extract` writes the data into the Codex workspace
and returns a *receipt* — a path and a row count. The model then reads the file
with its own sandboxed code, where volume costs nothing.

:func:`publish_report` is the same rule in reverse. Codex runs under
``sandbox="workspace_write"`` with ``network_access=False``, so it can write
only inside its workspace: it cannot email, upload, or copy a file anywhere
else. This tool is the single audited gate through which a finished artifact
leaves — which is why it validates the paths the model hands it rather than
trusting them.

Requires: nothing beyond the standard library. The "internal system" is the
CSV under ``data/``.
"""

from __future__ import annotations

import csv
import hashlib
import re
import shutil
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent

WORKSPACE = _HERE / ".codex_workspace"
"""Codex's working directory for this example.

Pinned via ``CodexRuntimeConfig(workspace_root=..., reuse_workspace=True)`` so
that these tools — which run in the *host* process, not in the sandbox — know
where to put files, and so that you can read what Codex wrote after the run.
See the README for what to do instead in a multi-tenant deployment.
"""

OUTBOX = _HERE / "outbox"
"""Where published artifacts land. Deliberately *outside* the workspace: the
sandbox cannot write here, so every file in it went through ``publish_report``."""

_WAREHOUSE = _HERE / "data"
"""Stands in for an internal reporting system (a warehouse, an ERP export)."""

_QUARTER_RE = re.compile(r"^\d{4}q[1-4]$")

_MAX_PUBLISH_BYTES = 2_000_000

_ALLOWED_SUFFIXES = {".md", ".svg"}


def _resolve_in_workspace(candidate: str) -> Path:
    """Resolve a model-supplied path, refusing anything outside the workspace.

    The argument comes from the model, so it is untrusted input: ``..``
    segments, absolute paths and symlinks pointing out of the workspace are all
    rejected here rather than trusted.

    Args:
        candidate (str): Path as the model wrote it, relative to the workspace.

    Returns:
        Path: The resolved, in-workspace path.

    Raises:
        ValueError: If the path escapes the workspace.
    """
    root = WORKSPACE.resolve()
    resolved = (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"path escapes the workspace: {candidate!r}")
    return resolved


def fetch_sales_extract(quarter: str) -> dict:
    """Export one quarter of raw order data from the internal sales warehouse.

    The rows are written into a file in your working directory. This tool
    returns only a receipt — it never returns the data itself, so read the CSV
    at the returned path with your own code.

    Args:
        quarter (str): Fiscal quarter to export, e.g. ``"2025Q3"``.

    Returns:
        dict: On success, ``status``, ``path`` (relative to your working
        directory), ``rows``, ``columns`` and ``bytes``. On failure,
        ``status="error"`` and a ``message`` saying what to try instead.
    """
    normalized = quarter.strip().lower().replace("-", "").replace(" ", "")
    if not _QUARTER_RE.match(normalized):
        return {
            "status": "error",
            "message": f"{quarter!r} is not a quarter; expected e.g. '2025Q3'.",
        }

    source = _WAREHOUSE / f"sales_{normalized}.csv"
    if not source.is_file():
        available = sorted(
            path.stem.removeprefix("sales_").upper()
            for path in _WAREHOUSE.glob("sales_*.csv")
        )
        return {
            "status": "error",
            "message": f"no extract for {quarter!r}; available: {available}",
        }

    destination = WORKSPACE / "data" / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)

    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
        rows = sum(1 for _ in reader)

    return {
        "status": "ok",
        "path": str(destination.relative_to(WORKSPACE)),
        "rows": rows,
        "columns": header,
        "bytes": destination.stat().st_size,
        "note": "raw warehouse export, exactly as stored upstream",
    }


def publish_report(report_path: str, chart_path: str) -> dict:
    """Publish a finished report and its chart to the reporting outbox.

    This is the only way a file leaves your sandbox: you have no network
    access and cannot write outside your working directory. Call it once the
    report is complete.

    Args:
        report_path (str): The Markdown report, relative to your working
            directory (must end in ``.md``).
        chart_path (str): The SVG chart, relative to your working directory
            (must end in ``.svg``).

    Returns:
        dict: On success, ``status``, ``published`` (one entry per file with
        its destination, size and content digest) and ``published_at``. On
        failure, ``status="error"`` and a ``message`` saying what to fix.
    """
    try:
        sources = [_resolve_in_workspace(p) for p in (report_path, chart_path)]
    except ValueError as error:
        return {"status": "error", "message": str(error)}

    for path, original in zip(sources, (report_path, chart_path)):
        if path.suffix.lower() not in _ALLOWED_SUFFIXES:
            return {
                "status": "error",
                "message": f"{original!r}: only .md and .svg files are published",
            }
        if not path.is_file():
            return {"status": "error", "message": f"{original!r}: no such file"}
        size = path.stat().st_size
        if size == 0:
            return {"status": "error", "message": f"{original!r}: file is empty"}
        if size > _MAX_PUBLISH_BYTES:
            return {
                "status": "error",
                "message": f"{original!r}: {size} bytes exceeds the publish limit",
            }

    published_at = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination_dir = OUTBOX / published_at
    destination_dir.mkdir(parents=True, exist_ok=True)

    published = []
    for path in sources:
        destination = destination_dir / path.name
        shutil.copyfile(path, destination)
        payload = destination.read_bytes()
        published.append(
            {
                "file": str(destination.relative_to(OUTBOX)),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest()[:12],
            }
        )

    return {"status": "ok", "published": published, "published_at": published_at}
