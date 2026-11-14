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

"""Typed, read-only ClickZetta tools exposed to the VeADK Agent."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


DEFAULT_DOMAIN_ID = int(os.getenv("CLICKZETTA_DEFAULT_DOMAIN_ID", "1"))
MAX_SQL_ROWS = 100
COMMAND_TIMEOUT_SECONDS = 120
SENSITIVE_KEY = re.compile(
    r"(authorization|password|passwd|secret|credential|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|refresh[_-]?token|access[_-]?token|(^|_)pat($|_))",
    re.IGNORECASE,
)
FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|alter|drop|truncate|create|replace|merge|grant|"
    r"revoke|call|execute|copy|optimize|vacuum|system|use|set|reset|attach|"
    r"detach|kill|unload|load)\b",
    re.IGNORECASE,
)


class ClickZettaToolError(RuntimeError):
    """Safe, displayable ClickZetta tool error."""


def _trace_tool(name: str, detail: str = "") -> None:
    suffix = f" | {detail}" if detail else ""
    print(f"[VEADK TOOL] {name}{suffix}", file=sys.stderr, flush=True)


def _find_cz_cli() -> str:
    explicit = os.environ.get("CZ_CLI_BIN")
    project_root = Path(__file__).resolve().parents[2]
    candidates = [
        explicit,
        str(Path.home() / ".local" / "bin" / "cz-cli"),
        str(project_root / "node_modules" / ".bin" / "cz-cli"),
        shutil.which("cz-cli"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise ClickZettaToolError(
        "找不到 cz-cli。请安装 CLI，或用 CZ_CLI_BIN 指向可执行文件。"
    )


def _sanitize(value: Any) -> Any:
    """Recursively redact credentials while keeping useful evidence."""
    if isinstance(value, dict):
        return {
            str(key): "***REDACTED***"
            if SENSITIVE_KEY.search(str(key))
            else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        value = re.sub(
            r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1***REDACTED***", value
        )
        value = re.sub(
            r"(?i)((?:password|secret|token|api[_-]?key)\s*[=:]\s*)\S+",
            r"\1***REDACTED***",
            value,
        )
    return value


def _run_cz(args: list[str], timeout: int = COMMAND_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Run cz-cli with argv, never a shell, and return redacted JSON."""
    command = [_find_cz_cli(), *args, "--format", "json"]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[2],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ClickZettaToolError(f"云器命令在 {timeout} 秒后超时。") from exc

    elapsed_ms = round((time.monotonic() - started) * 1000)
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if completed.returncode != 0:
        detail = _sanitize(stderr or stdout or "无错误详情")
        raise ClickZettaToolError(
            f"云器命令执行失败（exit={completed.returncode}）：{detail}"
        )
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ClickZettaToolError("云器 CLI 未返回有效 JSON。") from exc
    result = _sanitize(parsed)
    if isinstance(result, dict) and "client_elapsed_ms" not in result:
        result["client_elapsed_ms"] = elapsed_ms
    return result


def get_clickzetta_status() -> dict[str, Any]:
    """Check the active ClickZetta connection through a read-only CLI call."""
    _trace_tool("get_clickzetta_status")
    raw = _run_cz(["status"])
    data = raw.get("data", {}) if isinstance(raw, dict) else {}
    return {
        "connected": bool(data.get("connected")),
        "workspace": data.get("workspace"),
        "schema": data.get("schema"),
        "cli_version": data.get("cli_version"),
        "elapsed_ms": raw.get("client_elapsed_ms"),
    }


def get_clickzetta_runtime_overview(limit: int = 5) -> dict[str, Any]:
    """Inspect workspace and recent jobs without changing any runtime state.

    Args:
        limit: Number of recent jobs to summarize, from 1 to 10.
    """
    safe_limit = min(max(int(limit), 1), 10)
    _trace_tool("get_clickzetta_runtime_overview", f"limit={safe_limit}")
    workspace_raw = _run_cz(["workspace", "current"])
    jobs_raw = _run_cz(["job", "list", "--limit", str(safe_limit)])
    workspace_data = workspace_raw.get("data", {})
    jobs_data = jobs_raw.get("data", jobs_raw)
    columns = jobs_data.get("columns", []) if isinstance(jobs_data, dict) else []
    rows = jobs_data.get("rows", []) if isinstance(jobs_data, dict) else []
    records = [
        dict(zip(columns, row, strict=False)) for row in rows if isinstance(row, list)
    ]
    allowed_fields = (
        "job_id",
        "status",
        "creator",
        "start_time",
        "end_time",
        "vcluster_name",
    )
    jobs = [{field: row.get(field) for field in allowed_fields} for row in records]
    status_counts: dict[str, int] = {}
    for job in jobs:
        status = str(job.get("status") or "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "workspace": workspace_data.get("workspace"),
        "observed_virtual_clusters": sorted(
            {str(job["vcluster_name"]) for job in jobs if job.get("vcluster_name")}
        ),
        "job_status_counts": status_counts,
        "recent_jobs": jobs,
        "note": "仅做运行态观察；未开放启停任务或修改集群。",
    }


def list_clickzetta_assets() -> dict[str, Any]:
    """List visible tables/views and Analytics Agent domains, read-only."""
    _trace_tool("list_clickzetta_assets")
    tables_raw = _run_cz(["sql", "SHOW TABLES"])
    domains_raw = _run_cz(["analytics-agent", "domain", "list"])
    tables_data = tables_raw.get("data", tables_raw)
    domains_data = domains_raw.get("data", [])
    columns = tables_data.get("columns", []) if isinstance(tables_data, dict) else []
    rows = tables_data.get("rows", []) if isinstance(tables_data, dict) else []
    return {
        "tables": [
            dict(zip(columns, row, strict=False))
            for row in rows
            if isinstance(row, list)
        ],
        "analytics_domains": [
            {
                "domain_id": item.get("domainId"),
                "name": item.get("name"),
                "description": item.get("description"),
                "asset_counts": item.get("targetCounts"),
            }
            for item in domains_data
            if isinstance(item, dict)
        ],
    }


def get_semantic_catalog(domain_id: int = DEFAULT_DOMAIN_ID) -> dict[str, Any]:
    """Read a domain's datasets and governed metric definitions.

    Args:
        domain_id: ClickZetta Analytics Agent domain identifier.
    """
    _trace_tool("get_semantic_catalog", f"domain_id={domain_id}")
    detail_raw = _run_cz(["analytics-agent", "domain", "detail", str(domain_id)])
    metrics_raw = _run_cz(
        ["analytics-agent", "metric", "list", "--domain-id", str(domain_id)]
    )
    detail = detail_raw.get("data", {})
    metrics = metrics_raw.get("data", [])
    return {
        "domain": {
            "id": detail.get("domainId"),
            "name": detail.get("name"),
            "description": detail.get("description"),
            "asset_counts": detail.get("targetCounts"),
        },
        "datasets": [
            {
                "dataset_id": table.get("datasetId"),
                "display_name": table.get("displayName"),
                "table_name": table.get("tableName"),
                "description": table.get("description"),
            }
            for table in detail.get("tables", [])
            if isinstance(table, dict)
        ],
        "metrics": [
            {
                "id": metric.get("id"),
                "name": (metric.get("names") or [metric.get("colName")])[0],
                "description": metric.get("description"),
                "expression": metric.get("aggExpr"),
                "aliases": metric.get("alias") or [],
                "status": metric.get("status"),
            }
            for metric in metrics
            if isinstance(metric, dict)
        ],
    }


def ask_clickzetta_analytics(
    question: str, domain_id: int = DEFAULT_DOMAIN_ID
) -> dict[str, Any]:
    """Ask ClickZetta Analytics Agent a business question over a semantic domain.

    Args:
        question: A concrete business-data question in natural language.
        domain_id: ClickZetta Analytics Agent domain identifier.

    Calls in one Analytics Agent session must be sequential.
    """
    question = question.strip()
    if not question:
        return {"ok": False, "error": "问题不能为空。"}
    if len(question) > 500:
        return {"ok": False, "error": "问题过长；现场演示限制为 500 个字符。"}
    _trace_tool(
        "ask_clickzetta_analytics",
        f"domain_id={domain_id}, question_chars={len(question)}",
    )
    raw = _run_cz(
        [
            "analytics-agent",
            "session",
            "run",
            "--domain-id",
            str(domain_id),
            "--msg",
            question,
            "--summary",
        ],
        timeout=180,
    )
    return {
        "ok": True,
        "answer": raw.get("data"),
        "domain_id": domain_id,
        "source": "ClickZetta Analytics Agent",
        "server_time_ms": raw.get("time_ms"),
        "client_elapsed_ms": raw.get("client_elapsed_ms"),
        "execution_note": "同一 Analytics Agent session 内的问题必须串行执行。",
    }


def run_readonly_sql(sql: str, max_rows: int = MAX_SQL_ROWS) -> dict[str, Any]:
    """Run one allowlisted read-only SQL statement with a 100-row ceiling.

    Args:
        sql: One SELECT, WITH...SELECT, SHOW, DESC, DESCRIBE, or EXPLAIN query.
        max_rows: Maximum rows returned; values above 100 are reduced to 100.
    """
    _trace_tool("run_readonly_sql")
    statement = sql.strip().rstrip(";").strip()
    denial: str | None = None
    if not statement:
        denial = "SQL 不能为空。"
    elif (
        ";" in statement or "--" in statement or "/*" in statement or "*/" in statement
    ):
        denial = "只允许单条且不含注释的只读 SQL。"
    elif not re.match(r"^(select|with|show|desc|describe|explain)\b", statement, re.I):
        denial = "只允许 SELECT/WITH/SHOW/DESC/DESCRIBE/EXPLAIN。"
    elif FORBIDDEN_SQL.search(statement):
        denial = "SQL 命中禁止的写入或管理关键字。"
    if denial:
        return {
            "ok": False,
            "allowed": False,
            "query": statement,
            "reason": denial,
            "sent_to_clickzetta": False,
        }

    safe_limit = min(max(int(max_rows), 1), MAX_SQL_ROWS)
    if re.match(r"^(select|with)\b", statement, re.I) and not re.search(
        r"\blimit\s+\d+\b", statement, re.I
    ):
        statement = f"{statement} LIMIT {safe_limit}"
    raw = _run_cz(["sql", statement])
    data = raw.get("data", raw)
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        data["rows"] = data["rows"][:safe_limit]
        data["count"] = min(int(data.get("count", len(data["rows"]))), safe_limit)
    return {
        "ok": True,
        "allowed": True,
        "query": statement,
        "result": data,
        "sent_to_clickzetta": True,
    }
