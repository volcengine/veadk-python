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

"""AgentKit Sandbox backed Skill creator routes for the frontend."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
import re
import stat
import tempfile
import textwrap
import time
import uuid
import zipfile

from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Any
import requests

from agentkit.sdk.skills import types as skills_types
from agentkit.sdk.skills.client import AgentkitSkillsClient
from agentkit.sdk.tools import types as tools_types
from agentkit.sdk.tools.client import AgentkitToolsClient
from agentkit.toolkit.cli.sandbox.env_config import build_exec_session_envs
from agentkit.toolkit.cli.sandbox.sandbox_client import (
    SANDBOX_FILE_DOWNLOAD_ROUTE,
    build_bash_exec_url,
    build_exec_url,
    build_file_url,
)
from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field


_MODELS = (
    ("a", "doubao-seed-2-0-pro-260215", "豆包 Seed 2.0 Pro"),
    ("b", "deepseek-v4-flash-260425", "DeepSeek V4 Flash"),
)
_MODEL_PROVIDER = "model_square"
_MODEL_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
_REGION = "cn-beijing"
_SESSION_TTL_SECONDS = 1800
_SESSION_DISCOVERY_ATTEMPTS = 6
_SESSION_DISCOVERY_INTERVAL_SECONDS = 5.0
_HTTP_TIMEOUT_SECONDS = 300
_JOB_ID_RE = re.compile(r"^sc-[0-9a-f]{12}-[0-9a-f]{24}$")
_SKILL_NAME_RE = re.compile(r"^[a-z0-9-]+$")
_TOOL_ID_ENV = "SANDBOX_SKILL_CREATOR"
_MAX_PROMPT_CHARS = 20_000
_MAX_ARCHIVE_BYTES = 5 * 1024 * 1024
_MAX_ACTIVITY_COUNT = 80
_MAX_ACTIVITY_TEXT_CHARS = 1_200
_MAX_ACTIVITY_TOTAL_CHARS = 24_000
_ACTIVITY_KINDS = {"status", "thinking", "tool", "message"}
_SESSION_CREDENTIAL_ENV_KEYS = {
    "ANTHROPIC_AUTH_TOKEN",
    "CODEX_API_KEY",
    "OPENCODE_API_KEY",
}


class _CreateJobBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=_MAX_PROMPT_CHARS)


class _PublishBody(BaseModel):
    skill_space_ids: list[str] = Field(default_factory=list, alias="skillSpaceIds")
    project_name: str | None = Field(default=None, alias="projectName")
    skill_id: str | None = Field(default=None, alias="skillId")

    model_config = {"populate_by_name": True}


class SkillCreatorError(RuntimeError):
    """A safe error that may be returned to the browser."""


def _validated_activities(value: object) -> list[dict[str, Any]]:
    """Validate the bounded public activity stream returned by a Sandbox."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > _MAX_ACTIVITY_COUNT:
        raise SkillCreatorError("Skill 生成活动记录格式错误")
    activities: list[dict[str, Any]] = []
    total_chars = 0
    for item in value:
        if not isinstance(item, dict):
            raise SkillCreatorError("Skill 生成活动记录格式错误")
        activity_id = item.get("id")
        kind = item.get("kind")
        status = item.get("status")
        if (
            not isinstance(activity_id, str)
            or not activity_id
            or len(activity_id) > 100
            or kind not in _ACTIVITY_KINDS
            or status not in {"running", "done"}
        ):
            raise SkillCreatorError("Skill 生成活动记录格式错误")
        normalized: dict[str, Any] = {
            "id": activity_id,
            "kind": str(kind),
            "status": str(status),
        }
        if kind == "tool":
            name = item.get("name")
            if not isinstance(name, str) or not name or len(name) > 200:
                raise SkillCreatorError("Skill 生成活动记录格式错误")
            normalized["name"] = name
            for source_key, target_key in (("input", "input"), ("output", "output")):
                if source_key not in item:
                    continue
                try:
                    serialized = json.dumps(item[source_key], ensure_ascii=False)
                except (TypeError, ValueError) as error:
                    raise SkillCreatorError("Skill 生成活动记录格式错误") from error
                if len(serialized) > 4_000:
                    raise SkillCreatorError("Skill 生成活动记录过大")
                normalized[target_key] = item[source_key]
        else:
            text = item.get("text")
            if (
                not isinstance(text, str)
                or not text
                or len(text) > _MAX_ACTIVITY_TEXT_CHARS
            ):
                raise SkillCreatorError("Skill 生成活动记录格式错误")
            normalized["text"] = text
        total_chars += len(json.dumps(normalized, ensure_ascii=False))
        if total_chars > _MAX_ACTIVITY_TOTAL_CHARS:
            raise SkillCreatorError("Skill 生成活动记录过大")
        activities.append(normalized)
    return activities


def _runner_source() -> str:
    """Return the fixed program executed inside each isolated CodeEnv."""
    return textwrap.dedent(
        r"""
        import json
        import os
        import re
        import selectors
        import subprocess
        import time
        import traceback
        import zipfile
        from pathlib import Path

        job_dir = Path(__file__).resolve().parent
        work_dir = job_dir / "work"
        status_path = job_dir / "status.json"
        started = time.monotonic()
        started_at_ms = int(time.time() * 1000)
        activities = []
        activity_sequence = 0
        current_status_id = None
        secret_values = {
            value.encode("utf-8")
            for name, value in os.environ.items()
            if len(value) >= 8
            and any(marker in name.upper() for marker in ("KEY", "PASSWORD", "SECRET", "TOKEN"))
        }
        sensitive_assignment = re.compile(
            r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password)"
            r"[\"']?\s*[:=]\s*[\"']?)([^\"'\s,;}]+)"
        )
        bearer_token = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]+")
        jwt_token = re.compile(
            r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."
            r"[A-Za-z0-9_-]{10,}\b"
        )
        internal_reference = re.compile(
            r"(?i)(?:/home/gem/)?\.codex(?:/[^\s\"']*)?"
        )

        def redact(value):
            text = str(value)
            for secret in secret_values:
                text = text.replace(secret.decode("utf-8"), "[REDACTED]")
            text = sensitive_assignment.sub(r"\1[REDACTED]", text)
            text = bearer_token.sub(r"\1[REDACTED]", text)
            text = jwt_token.sub("[REDACTED]", text)
            return internal_reference.sub("系统工具", text)

        def write_status(status, stage, **extra):
            payload = {
                "status": status,
                "stage": stage,
                "elapsedMs": int((time.monotonic() - started) * 1000),
                "startedAtMs": started_at_ms,
                "activities": activities,
                **extra,
            }
            temporary = status_path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            temporary.replace(status_path)

        def add_activity(
            kind, text, status="done", activity_id=None, stage="generating"
        ):
            global activity_sequence
            safe_text = redact(text).strip()[:1200]
            if not safe_text:
                return
            item_id = str(activity_id or f"activity-{activity_sequence}")[:100]
            activity_sequence += 1
            upsert_activity(
                {"id": item_id, "kind": kind, "text": safe_text, "status": status}
            )
            write_status("running", stage)

        def safe_value(value, depth=0):
            if depth >= 4:
                return "…"
            if isinstance(value, str):
                return redact(value)[:1200]
            if isinstance(value, dict):
                result = {}
                for key, item in list(value.items())[:30]:
                    safe_key = redact(key)[:100]
                    if any(
                        marker in str(key).upper()
                        for marker in ("KEY", "PASSWORD", "SECRET", "TOKEN")
                    ):
                        result[safe_key] = "[REDACTED]"
                    else:
                        result[safe_key] = safe_value(item, depth + 1)
                return result
            if isinstance(value, list):
                return [safe_value(item, depth + 1) for item in value[:30]]
            if value is None or isinstance(value, (bool, int, float)):
                return value
            return redact(value)[:1200]

        def upsert_activity(activity):
            for index, item in enumerate(activities):
                if item["id"] == activity["id"]:
                    activities[index] = activity
                    break
            else:
                activities.append(activity)
            while len(activities) > 80 or len(
                json.dumps(activities, ensure_ascii=False)
            ) > 24000:
                activities.pop(0)

        def add_tool_activity(
            name,
            tool_input,
            tool_output,
            status="done",
            activity_id=None,
            stage="generating",
        ):
            global activity_sequence
            item_id = str(activity_id or f"activity-{activity_sequence}")[:100]
            activity_sequence += 1
            activity = {
                "id": item_id,
                "kind": "tool",
                "name": redact(name).strip()[:200] or "执行工具",
                "status": status,
            }
            if tool_input is not None:
                activity["input"] = safe_value(tool_input)
            if tool_output is not None:
                activity["output"] = safe_value(tool_output)
            upsert_activity(activity)
            write_status("running", stage)

        def set_stage_activity(text, stage):
            global current_status_id
            if current_status_id:
                for item in activities:
                    if item["id"] == current_status_id:
                        item["status"] = "done"
                        break
            current_status_id = f"stage-{activity_sequence}"
            add_activity("status", text, "running", current_status_id, stage)

        def public_file_changes(item):
            changes = item.get("changes")
            if isinstance(changes, list):
                return [
                    {
                        "path": public_path(change.get("path")),
                        "kind": change.get("kind") or "update",
                    }
                    for change in changes[:8]
                    if isinstance(change, dict) and change.get("path")
                ]
            path = item.get("path")
            return [{"path": public_path(path), "kind": "update"}] if path else []

        def public_path(value):
            path = str(value)
            if "/work/" in path:
                return path.split("/work/", 1)[1]
            if path.startswith("/") or ".codex" in path.lower():
                return Path(path).name or "Skill 文件"
            return path

        def public_command_text(command):
            lowered = command.lower()
            if "apply_patch" in lowered or "cat >" in lowered or "init_skill" in lowered:
                return "生成 Skill 文件"
            if re.search(r"\b(?:cat|sed|head|tail)\s", lowered):
                return "读取文件"
            if re.search(r"\b(?:ls|find|tree)\s", lowered):
                return "检查文件结构"
            if re.search(r"\b(?:rm|mv|mkdir|rmdir)\s", lowered):
                return "整理生成文件"
            if "python" in lowered or "pytest" in lowered:
                return "运行校验脚本"
            return "执行生成命令"

        def command_file_paths(command):
            paths = re.findall(
                r"^\*\*\* (?:Add|Update|Delete) File:\s*(.+)$",
                command,
                flags=re.MULTILINE,
            )
            paths.extend(
                re.findall(r"\bcat\s*>\s*([^\s\"']+)", command, flags=re.IGNORECASE)
            )
            paths.extend(
                re.findall(r"\brm\s+(?:-[^\s]+\s+)*([^\s\"']+)", command)
            )
            return paths[:8]

        def handle_event(event):
            if not isinstance(event, dict):
                return
            event_type = event.get("type")
            item = event.get("item")
            if event_type not in {"item.started", "item.completed"} or not isinstance(
                item, dict
            ):
                return
            item_type = item.get("type")
            item_id = str(item.get("id") or f"item-{activity_sequence}")
            event_status = "running" if event_type == "item.started" else "done"
            if item_type == "reasoning":
                summary = item.get("text") or item.get("summary")
                if isinstance(summary, list):
                    summary = "\n".join(
                        part for part in summary if isinstance(part, str) and part
                    )
                if isinstance(summary, str):
                    add_activity("thinking", summary, event_status, item_id)
            elif item_type == "command_execution":
                command = item.get("command")
                if isinstance(command, str):
                    output = None
                    if event_status == "done":
                        output = {
                            "status": item.get("status") or "completed",
                            "exitCode": item.get("exit_code"),
                            "output": item.get("aggregated_output"),
                        }
                    add_tool_activity(
                        "运行命令",
                        {"command": public_command_text(command)},
                        output,
                        event_status,
                        item_id,
                    )
                    paths = command_file_paths(command)
                    if paths:
                        add_tool_activity(
                            "修改文件",
                            {"paths": [public_path(path) for path in paths]},
                            {"status": item.get("status") or event_status},
                            event_status,
                            f"{item_id}-files",
                        )
            elif item_type in {"file_change", "file_changes"}:
                add_tool_activity(
                    "修改文件",
                    {"changes": public_file_changes(item)},
                    {"status": item.get("status") or event_status},
                    event_status,
                    item_id,
                )
            elif item_type == "mcp_tool_call":
                server = str(item.get("server") or "MCP")
                tool = str(item.get("tool") or item.get("name") or "工具")
                add_tool_activity(
                    f"MCP · {server}/{tool}",
                    item.get("arguments"),
                    item.get("result") or item.get("error"),
                    event_status,
                    item_id,
                )
            elif item_type == "agent_message":
                message = item.get("text")
                if isinstance(message, str):
                    add_activity("message", message, event_status, item_id)
            elif item_type:
                name = item.get("name") or {
                    "web_search": "网络搜索",
                    "web_search_call": "网络搜索",
                }.get(str(item_type), "执行工具")
                tool_input = (
                    item.get("arguments")
                    or item.get("input")
                    or item.get("query")
                )
                tool_output = item.get("result") or item.get("output") or item.get("error")
                add_tool_activity(
                    name, tool_input, tool_output, event_status, item_id
                )

        def metadata(skill_md):
            lines = skill_md.splitlines()
            if not lines or lines[0].strip() != "---":
                raise ValueError("SKILL.md 必须以 YAML frontmatter 开头")
            try:
                end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
            except StopIteration as error:
                raise ValueError("SKILL.md frontmatter 未闭合") from error
            values = {}
            for line in lines[1:end]:
                if ":" not in line or line.lstrip().startswith("#"):
                    continue
                key, value = line.split(":", 1)
                values[key.strip()] = value.strip()
            name = values.get("name", "")
            description = values.get("description", "")
            if not name or len(name) > 64 or not re.fullmatch(r"[a-z0-9-]+", name):
                raise ValueError("Skill name 必须匹配 [a-z0-9-]+ 且不超过 64 个字符")
            if "agentkit" in name:
                raise ValueError("Skill name 不能包含保留词 agentkit")
            if name.startswith(("'", '"')) or description.startswith(("'", '"')):
                raise ValueError("name 和 description 不能使用引号包裹")
            if not description or len(description) > 1024:
                raise ValueError("Skill description 必填且不能超过 1024 个字符")
            if re.search(r"<[^>]+>", description):
                raise ValueError("Skill description 不能包含 XML 标签")
            return name, description

        try:
            work_dir.mkdir(parents=True, exist_ok=True)
            prompt = (job_dir / "prompt.txt").read_text(encoding="utf-8")
            set_stage_activity("正在生成 Skill", "generating")
            process = subprocess.Popen(
                [
                    "codex",
                    "exec",
                    "--ephemeral",
                    "--skip-git-repo-check",
                    "--sandbox",
                    "workspace-write",
                    "--json",
                    "-C",
                    str(work_dir),
                    "-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            try:
                process.stdin.write(prompt.encode("utf-8"))
            except BrokenPipeError:
                pass
            finally:
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            recent_output = []
            output_buffer = b""
            deadline = time.monotonic() + 900
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    process.kill()
                    raise TimeoutError("模型生成超时")
                for key, _ in selector.select(timeout=1):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        continue
                    output_buffer += chunk
                    lines = output_buffer.split(b"\n")
                    output_buffer = lines.pop()
                    for raw_line in lines:
                        line = raw_line.decode("utf-8", errors="replace")
                        recent_output.append(line)
                        recent_output = recent_output[-20:]
                        try:
                            handle_event(json.loads(line))
                        except ValueError:
                            continue
            output_buffer += process.stdout.read()
            for raw_line in output_buffer.splitlines():
                line = raw_line.decode("utf-8", errors="replace")
                recent_output.append(line)
                recent_output = recent_output[-20:]
                try:
                    handle_event(json.loads(line))
                except ValueError:
                    continue
            if process.returncode != 0:
                detail = redact("".join(recent_output)[-900:])
                raise RuntimeError(
                    f"模型生成失败，退出码 {process.returncode}: {detail.strip()}"
                )

            set_stage_activity("正在校验 Skill 结构", "validating")
            entries = [
                path for path in work_dir.iterdir() if not path.name.startswith(".")
            ]
            if any(path.is_symlink() for path in entries):
                raise ValueError("Skill 根目录不允许使用符号链接")
            roots = [path for path in entries if path.is_dir()]
            if len(roots) != 1:
                raise ValueError("生成结果必须只包含一个 Skill 根目录")
            if len(entries) != 1:
                raise ValueError("Skill 根目录之外不能包含其他文件")
            root = roots[0]
            skill_md_path = root / "SKILL.md"
            if not skill_md_path.is_file():
                raise ValueError("生成结果缺少 SKILL.md")
            skill_md = skill_md_path.read_text(encoding="utf-8")
            name, description = metadata(skill_md)
            if root.name != name:
                raise ValueError("Skill 根目录名必须与 frontmatter name 一致")

            files = []
            total_size = 0
            for path in sorted(root.rglob("*")):
                if path.is_symlink():
                    raise ValueError("Skill 中不允许符号链接")
                if not path.is_file():
                    continue
                content = path.read_bytes()
                try:
                    content.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise ValueError("Skill 只能包含 UTF-8 文本文件") from error
                if any(secret in content for secret in secret_values):
                    raise ValueError("生成结果包含敏感凭证，已拒绝")
                size = len(content)
                total_size += size
                files.append({"path": path.relative_to(root).as_posix(), "size": size})
            if not files or len(files) > 100:
                raise ValueError("Skill 文件数必须在 1 到 100 之间")
            if total_size > 2 * 1024 * 1024:
                raise ValueError("Skill 文本文件总大小不能超过 2 MiB")

            set_stage_activity("正在打包 Skill", "packaging")
            archive_path = job_dir / "skill.zip"
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for item in files:
                    source = root / item["path"]
                    archive.write(source, f"{name}/{item['path']}")
            if current_status_id:
                for item in activities:
                    if item["id"] == current_status_id:
                        item["status"] = "done"
                        break
            write_status(
                "succeeded",
                "completed",
                name=name,
                description=description,
                skillMd=skill_md,
                files=files,
                validation={"valid": True, "errors": []},
            )
        except Exception as error:
            safe_error = redact(error)[:1000]
            write_status(
                "failed",
                "failed",
                error=safe_error,
                validation={"valid": False, "errors": [safe_error]},
            )
            (job_dir / "runner-error.log").write_text(
                redact(traceback.format_exc()), encoding="utf-8"
            )
        """
    ).strip()


_BOOTSTRAP_COMMAND = textwrap.dedent(
    r"""
    set -euo pipefail
    python3 - <<'PY'
    import base64
    import json
    import os
    from pathlib import Path

    job_dir = Path(os.environ["VEADK_SKILL_JOB_DIR"])
    job_dir.mkdir(parents=True, exist_ok=False)
    (job_dir / "prompt.txt").write_bytes(
        base64.b64decode(os.environ["VEADK_SKILL_PROMPT_B64"])
    )
    (job_dir / "runner.py").write_bytes(
        base64.b64decode(os.environ["VEADK_SKILL_RUNNER_B64"])
    )
    (job_dir / "status.json").write_text(
        json.dumps({"status": "queued", "stage": "provisioning", "elapsedMs": 0}),
        encoding="utf-8",
    )
    PY
    nohup python3 "$VEADK_SKILL_JOB_DIR/runner.py" \
      >"$VEADK_SKILL_JOB_DIR/runner.log" 2>&1 </dev/null &
    """
).strip()


def _skill_prompt(request: str) -> str:
    """Build a deterministic prompt that constrains the generated artifact."""
    return textwrap.dedent(
        f"""
        Create a production-ready Agent Skill for this request:

        {request}

        Work directly in the current directory. Create exactly one root directory
        containing the Skill. The root directory name and SKILL.md frontmatter
        name must match `[a-z0-9-]+`, be at most 64 characters, and must not
        contain the reserved word `agentkit`. SKILL.md must start with unquoted
        `name:` and `description:` fields. Description is required, at most 1024
        characters, and must not contain XML. Include only useful UTF-8 text
        files. Do not create archives, binaries, symlinks, or files outside the
        current directory. Never read, expose, transform, or copy environment
        variables or credentials. Make the instructions concise, concrete, and
        reusable.
        """
    ).strip()


def _safe_json_response(
    response: requests.Response,
    action: str,
    *,
    allow_running: bool = False,
) -> dict[str, Any]:
    if response.status_code >= 400:
        raise SkillCreatorError(f"{action}失败（HTTP {response.status_code}）")
    try:
        payload = response.json()
    except ValueError as error:
        raise SkillCreatorError(f"{action}返回了非 JSON 响应") from error
    if not isinstance(payload, dict):
        raise SkillCreatorError(f"{action}返回格式错误")
    data = payload.get("data")
    if isinstance(data, dict):
        status = data.get("status")
        accepted_statuses = {"completed", "running"} if allow_running else {"completed"}
        if status and status not in accepted_statuses:
            raise SkillCreatorError(f"{action}未完成")
        if data.get("exit_code") not in (None, 0):
            raise SkillCreatorError(f"{action}执行失败")
    return payload


def _validate_model_base_url(value: str) -> str:
    """Require the Ark model endpoint configured by Studio deployment."""
    normalized = value.rstrip("/")
    if normalized != _MODEL_BASE_URL:
        raise SkillCreatorError("Sandbox 模型服务地址无效")
    return normalized


def ensure_skill_creator_model_credential(
    *,
    tool_id: str,
    access_key: str,
    secret_key: str,
    session_token: str | None = None,
    region: str = _REGION,
) -> None:
    """Resolve an Ark API key and bind it directly to the CodeEnv Tool."""
    from agentkit.auth._openapi import OpenApiClient

    from veadk.auth.veauth.ark_veauth import get_ark_token

    api = OpenApiClient(
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
    )
    response = api.call("agentkit", "GetTool", "2025-10-30", {"ToolId": tool_id})
    tool = response.get("Tool") if isinstance(response.get("Tool"), dict) else response
    if not isinstance(tool, dict):
        raise SkillCreatorError("AgentKit Tool 响应格式错误")
    envs = {
        item.get("Key"): item.get("Value")
        for item in tool.get("Envs", [])
        if item.get("Key")
    }
    model_api_key = get_ark_token(
        region=region,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
    )
    session_envs = build_exec_session_envs(
        model_name=_MODELS[0][1],
        model_api_key=model_api_key,
        model_provider=_MODEL_PROVIDER,
        model_base_url=_MODEL_BASE_URL,
        model_provider_was_provided=True,
        model_base_url_was_provided=True,
        include_codex_config=True,
        disable_websearch_apikey=True,
    )
    if not session_envs:
        raise SkillCreatorError("无法生成 Sandbox 模型环境变量")
    updates = {item.key: item.value for item in session_envs}
    if all(envs.get(key) == value for key, value in updates.items()):
        return
    envs.update(updates)
    api.call(
        "agentkit",
        "UpdateTool",
        "2025-10-30",
        {
            "ToolId": tool_id,
            "Envs": [{"Key": key, "Value": value} for key, value in envs.items()],
        },
    )


class SkillCreatorService:
    """Coordinate A/B Skill generation in independent AgentKit sandboxes."""

    def __init__(self, tool_id: str | None = None, region: str | None = None) -> None:
        self._configured_tool_id = (tool_id or "").strip()
        self._region = (
            region or os.getenv("AGENTKIT_SANDBOX_REGION") or _REGION
        ).strip()

    def capabilities(self) -> dict[str, Any]:
        """Return fixed model capabilities without exposing server credentials."""
        tool_id = self._tool_id(required=False)
        enabled = False
        reason = "管理员未配置"
        if tool_id:
            try:
                tool = AgentkitToolsClient(region=self._region).get_tool(
                    tools_types.GetToolRequest(ToolId=tool_id)
                )
                envs = {item.key: item.value for item in tool.envs or []}
                credential_ready = bool(
                    envs.get("CODEX_API_KEY") and envs.get("CODEX_BASE_URL")
                )
                if credential_ready:
                    _validate_model_base_url(str(envs["CODEX_BASE_URL"]))
                tool_ready = tool.tool_type == "CodeEnv" and tool.status == "Ready"
                enabled = tool_ready and credential_ready
                if not tool_ready:
                    reason = "配置的 Sandbox 必须是 Ready CodeEnv"
                elif not credential_ready:
                    reason = "Sandbox 尚未绑定模型凭证"
                else:
                    reason = ""
            except Exception:
                reason = "无法访问配置的 AgentKit Sandbox"
        return {
            "enabled": enabled,
            "reason": reason,
            "models": [
                {"candidateId": candidate_id, "id": model, "label": label}
                for candidate_id, model, label in _MODELS
            ],
            "publishEnabled": enabled,
        }

    def create_job(
        self,
        request: str,
        owner_id: str,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Create two isolated sessions and launch both generators."""
        prompt = request.strip()
        if not prompt:
            raise SkillCreatorError("请描述要创建的 Skill")
        if len(prompt) > _MAX_PROMPT_CHARS:
            raise SkillCreatorError("Skill 描述不能超过 20000 个字符")
        tool_id = self._tool_id()
        model_base_url = self._validate_tool(tool_id)
        job_id = self._new_job_id(owner_id)
        created: list[tuple[str, str]] = []
        candidates = [
            {
                "id": candidate_id,
                "model": model,
                "modelLabel": label,
                "status": "queued",
                "stage": "provisioning",
                "activities": [
                    {
                        "id": "provisioning",
                        "kind": "status",
                        "text": "正在拉起 Sandbox",
                        "status": "running",
                    }
                ],
            }
            for candidate_id, model, label in _MODELS
        ]
        failures: list[Exception] = []

        def job_payload(status: str) -> dict[str, Any]:
            return {
                "jobId": job_id,
                "prompt": prompt,
                "status": status,
                "candidates": [dict(candidate) for candidate in candidates],
            }

        if on_progress:
            on_progress(job_payload("provisioning"))
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {
                    executor.submit(
                        self._create_candidate,
                        tool_id,
                        job_id,
                        candidate_id,
                        model,
                        label,
                        model_base_url,
                        prompt,
                    ): (candidate_id, model, label)
                    for candidate_id, model, label in _MODELS
                }
                for future in as_completed(futures):
                    candidate_id, model, label = futures[future]
                    try:
                        result = future.result()
                    except Exception as error:
                        failures.append(error)
                        continue
                    created.append((tool_id, result["instanceId"]))
                    candidate = next(
                        item for item in candidates if item["id"] == candidate_id
                    )
                    candidate["status"] = "running"
                    candidate["stage"] = "generating"
                    candidate["activities"] = [
                        {
                            "id": "provisioning",
                            "kind": "status",
                            "text": "Sandbox 已就绪，正在启动生成",
                            "status": "done",
                        }
                    ]
                    if on_progress:
                        on_progress(job_payload("provisioning"))
                if failures:
                    raise failures[0]
        except Exception as error:
            self._delete_instances(created)
            if isinstance(error, SkillCreatorError):
                raise
            raise SkillCreatorError("创建 AgentKit Sandbox 会话失败") from error

        return job_payload("running")

    def get_job(self, job_id: str, owner_id: str) -> dict[str, Any]:
        """Read candidate status from Sandbox, making jobs instance-independent."""
        self._validate_job_owner(job_id, owner_id)
        tool_id = self._tool_id()
        candidates = [
            self._candidate_status(tool_id, job_id, candidate_id, model, label)
            for candidate_id, model, label in _MODELS
        ]
        terminal = all(item["status"] in {"succeeded", "failed"} for item in candidates)
        return {
            "jobId": job_id,
            "status": "completed" if terminal else "running",
            "candidates": candidates,
        }

    def download(
        self, job_id: str, candidate_id: str, owner_id: str
    ) -> tuple[bytes, str]:
        """Download a completed candidate archive from its Sandbox session."""
        self._validate_job_owner(job_id, owner_id)
        model_info = self._model(candidate_id)
        tool_id = self._tool_id()
        status = self._candidate_status(tool_id, job_id, *model_info)
        if status["status"] != "succeeded":
            raise SkillCreatorError("该方案尚未生成完成")
        session = self._find_session(tool_id, self._session_id(job_id, candidate_id))
        response = requests.get(
            build_file_url(session["endpoint"], SANDBOX_FILE_DOWNLOAD_ROUTE),
            params={
                "path": self._remote_path(job_id, candidate_id, "skill.zip"),
                "change_policy": "abort",
            },
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            raise SkillCreatorError("下载 Skill 压缩包失败")
        if len(response.content) > _MAX_ARCHIVE_BYTES:
            raise SkillCreatorError("生成的 Skill 压缩包超过 5 MiB")
        return response.content, f"{status['name']}.zip"

    def publish(
        self,
        job_id: str,
        candidate_id: str,
        owner_id: str,
        *,
        skill_space_ids: list[str],
        project_name: str | None = None,
        skill_id: str | None = None,
    ) -> dict[str, Any]:
        """Upload a candidate to TOS and create/update it in AgentKit."""
        archive, _ = self.download(job_id, candidate_id, owner_id)
        name, description = self._archive_metadata(archive)
        from agentkit.toolkit.cli.cli_skills_workflow import (
            _ensure_bucket_ready,
            _make_content_hashed_zip_copy,
            _tos_upload,
            _wait_for_running_version,
        )
        from agentkit.toolkit.config import GlobalConfigManager
        from agentkit.toolkit.volcengine.services.tos_service import TOSService

        config = GlobalConfigManager().load()
        configured_bucket = (
            os.getenv("VEADK_SKILL_CREATOR_TOS_BUCKET") or config.tos.bucket or ""
        ).strip()
        bucket = configured_bucket or TOSService.generate_bucket_name()
        prefix = (
            os.getenv("VEADK_SKILL_CREATOR_TOS_PREFIX")
            or config.tos.prefix
            or "agentkit/skills"
        ).strip()
        _ensure_bucket_ready(
            bucket_name=bucket,
            prefix=prefix,
            region=self._region,
            auto_bucket=not bool(configured_bucket),
            assume_yes=True,
            assume_no=False,
        )

        with tempfile.TemporaryDirectory(prefix="veadk-skill-publish-") as temp_dir:
            archive_path = Path(temp_dir) / f"{name}.zip"
            archive_path.write_bytes(archive)
            hashed_path = _make_content_hashed_zip_copy(
                str(archive_path), name, temp_dir
            )
            tos_url = _tos_upload(
                hashed_path, bucket, prefix, self._region, verify_bucket=False
            )

        client = AgentkitSkillsClient(region=self._region)
        effective_project = (
            project_name or os.getenv("VEADK_SKILL_CREATOR_PROJECT_NAME") or None
        )
        effective_skill_id = (skill_id or "").strip() or None
        if not effective_skill_id:
            response = client.list_skills(
                skills_types.ListSkillsRequest(
                    PageNumber=1,
                    PageSize=50,
                    Filter=skills_types.SkillFilter(Name=name),
                    ProjectName=effective_project,
                )
            )
            matches = response.items or []
            if len(matches) > 1:
                raise SkillCreatorError("存在多个同名 Skill，请指定 Skill ID")
            if matches:
                effective_skill_id = matches[0].id

        if effective_skill_id:
            client.update_skill(
                skills_types.UpdateSkillRequest(
                    Id=effective_skill_id,
                    Name=name,
                    Description=description,
                    TosUrl=tos_url,
                    SkillSpaces=skill_space_ids or None,
                    BucketName=bucket,
                )
            )
        else:
            created = client.create_skill(
                skills_types.CreateSkillRequest(
                    Name=name,
                    Description=description,
                    TosUrl=tos_url,
                    SkillSpaces=skill_space_ids or None,
                    BucketName=bucket,
                    ProjectName=effective_project,
                )
            )
            effective_skill_id = created.id
        if not effective_skill_id:
            raise SkillCreatorError("AgentKit 未返回 Skill ID")

        latest = _wait_for_running_version(
            client=client,
            skill_id=effective_skill_id,
            timeout_seconds=300,
            poll_interval_seconds=5,
        )
        version = latest.version or ""
        if skill_space_ids:
            client.publish_skill_to_skill_space(
                skills_types.PublishSkillToSkillSpaceRequest(
                    SkillSpaces=skill_space_ids,
                    Skills=[
                        skills_types.SkillBasicInfo(
                            SkillId=effective_skill_id, Version=version
                        )
                    ],
                )
            )
        return {
            "skillId": effective_skill_id,
            "version": version,
            "skillSpaceIds": skill_space_ids,
        }

    def delete_job(self, job_id: str, owner_id: str) -> None:
        """Delete both candidate Sandbox sessions when a job is discarded."""
        self._validate_job_owner(job_id, owner_id)
        tool_id = self._tool_id()
        instances = []
        for candidate_id, _, _ in _MODELS:
            try:
                session = self._find_session(
                    tool_id, self._session_id(job_id, candidate_id)
                )
            except SkillCreatorError:
                continue
            instances.append((tool_id, session["instanceId"]))
        self._delete_instances(instances, strict=True)

    def _create_candidate(
        self,
        tool_id: str,
        job_id: str,
        candidate_id: str,
        model: str,
        label: str,
        model_base_url: str,
        request: str,
    ) -> dict[str, str]:
        del label
        client = AgentkitToolsClient(region=self._region)
        session_id = self._session_id(job_id, candidate_id)
        session_envs = build_exec_session_envs(
            model_name=model,
            model_provider=_MODEL_PROVIDER,
            model_base_url=model_base_url,
            model_provider_was_provided=True,
            model_base_url_was_provided=True,
            include_codex_config=True,
            disable_websearch_apikey=True,
        )
        safe_session_envs = [
            item
            for item in session_envs or []
            if item.key not in _SESSION_CREDENTIAL_ENV_KEYS
        ]
        response = client.create_session(
            tools_types.CreateSessionRequest(
                ToolId=tool_id,
                Ttl=_SESSION_TTL_SECONDS,
                TtlUnit="second",
                UserSessionId=session_id,
                Envs=safe_session_envs,
            )
        )
        if not response.session_id:
            raise SkillCreatorError("AgentKit 未返回 Sandbox Session")
        try:
            if not response.endpoint:
                raise SkillCreatorError("AgentKit 未返回 Sandbox Session Endpoint")
            remote_dir = self._remote_path(job_id, candidate_id)
            launch = requests.post(
                build_bash_exec_url(response.endpoint),
                json={
                    "timeout": 30,
                    "hard_timeout": 1200,
                    "env": {
                        "VEADK_SKILL_JOB_DIR": remote_dir,
                        "VEADK_SKILL_PROMPT_B64": base64.b64encode(
                            _skill_prompt(request).encode("utf-8")
                        ).decode("ascii"),
                        "VEADK_SKILL_RUNNER_B64": base64.b64encode(
                            _runner_source().encode("utf-8")
                        ).decode("ascii"),
                    },
                    "command": _BOOTSTRAP_COMMAND,
                },
                timeout=90,
            )
            _safe_json_response(launch, "启动 Skill 生成任务", allow_running=True)
            self._wait_for_session_visibility(tool_id, session_id)
        except Exception:
            try:
                client.delete_session(
                    tools_types.DeleteSessionRequest(
                        ToolId=tool_id, SessionId=response.session_id
                    )
                )
            except Exception:
                pass
            raise
        return {"instanceId": response.session_id, "endpoint": response.endpoint}

    def _wait_for_session_visibility(self, tool_id: str, user_session_id: str) -> None:
        """Wait until a newly created Session is visible to ListSessions."""
        for attempt in range(_SESSION_DISCOVERY_ATTEMPTS):
            try:
                self._find_session(tool_id, user_session_id)
                return
            except SkillCreatorError:
                if attempt == _SESSION_DISCOVERY_ATTEMPTS - 1:
                    raise
                time.sleep(_SESSION_DISCOVERY_INTERVAL_SECONDS)

    def _candidate_status(
        self,
        tool_id: str,
        job_id: str,
        candidate_id: str,
        model: str,
        label: str,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": candidate_id,
            "model": model,
            "modelLabel": label,
            "status": "queued",
            "stage": "provisioning",
            "activities": [],
        }
        session = self._find_session(tool_id, self._session_id(job_id, candidate_id))
        response = requests.post(
            build_exec_url(session["endpoint"]),
            json={
                "id": "",
                "exec_dir": "/home/gem",
                "command": "cat "
                + self._remote_path(job_id, candidate_id, "status.json"),
            },
            timeout=30,
        )
        payload = _safe_json_response(response, "读取 Skill 生成状态")
        data = payload.get("data")
        output = data.get("output") if isinstance(data, dict) else None
        if not isinstance(output, str):
            return result
        try:
            remote_status = json.loads(output)
        except ValueError as error:
            raise SkillCreatorError("Skill 生成状态格式错误") from error
        if not isinstance(remote_status, dict):
            raise SkillCreatorError("Skill 生成状态格式错误")
        remote_status["activities"] = _validated_activities(
            remote_status.get("activities")
        )
        result.update(remote_status)
        started_at_ms = result.pop("startedAtMs", None)
        if result.get("status") == "running" and isinstance(started_at_ms, int):
            result["elapsedMs"] = max(0, int(time.time() * 1000) - started_at_ms)
        return result

    def _find_session(self, tool_id: str, user_session_id: str) -> dict[str, str]:
        response = AgentkitToolsClient(region=self._region).list_sessions(
            tools_types.ListSessionsRequest(
                ToolId=tool_id,
                MaxResults=10,
                Filters=[
                    tools_types.FiltersItemForListSessions(
                        Name="UserSessionId", Values=[user_session_id]
                    )
                ],
            )
        )
        for session in response.session_infos or []:
            if (
                session.user_session_id == user_session_id
                and session.session_id
                and session.endpoint
            ):
                return {
                    "instanceId": session.session_id,
                    "endpoint": session.endpoint,
                }
        raise SkillCreatorError("Skill 创建任务不存在或已过期")

    def _delete_instances(
        self, instances: list[tuple[str, str]], *, strict: bool = False
    ) -> None:
        failed = 0
        for tool_id, instance_id in instances:
            try:
                AgentkitToolsClient(region=self._region).delete_session(
                    tools_types.DeleteSessionRequest(
                        ToolId=tool_id, SessionId=instance_id
                    )
                )
            except Exception:
                failed += 1
        if strict and failed:
            raise SkillCreatorError("部分 AgentKit Sandbox 会话清理失败，请稍后重试")

    def _validate_tool(self, tool_id: str) -> str:
        try:
            tool = AgentkitToolsClient(region=self._region).get_tool(
                tools_types.GetToolRequest(ToolId=tool_id)
            )
        except Exception as error:
            raise SkillCreatorError("无法访问配置的 AgentKit Sandbox") from error
        if tool.tool_type != "CodeEnv" or tool.status != "Ready":
            raise SkillCreatorError("配置的 Sandbox 必须是 Ready CodeEnv")
        envs = {item.key: item.value for item in tool.envs or []}
        if not (envs.get("CODEX_API_KEY") and envs.get("CODEX_BASE_URL")):
            raise SkillCreatorError("Sandbox 尚未绑定模型凭证")
        return _validate_model_base_url(str(envs["CODEX_BASE_URL"]))

    def _tool_id(self, *, required: bool = True) -> str:
        if self._configured_tool_id:
            return self._configured_tool_id
        value = (os.getenv(_TOOL_ID_ENV) or "").strip()
        if value:
            return value
        if required:
            raise SkillCreatorError("管理员未配置")
        return ""

    def _new_job_id(self, owner_id: str) -> str:
        owner = hashlib.sha256(owner_id.encode("utf-8")).hexdigest()[:12]
        return f"sc-{owner}-{uuid.uuid4().hex[:24]}"

    def _validate_job_owner(self, job_id: str, owner_id: str) -> None:
        if not _JOB_ID_RE.fullmatch(job_id):
            raise SkillCreatorError("Skill 创建任务 ID 无效")
        expected = hashlib.sha256(owner_id.encode("utf-8")).hexdigest()[:12]
        if job_id.split("-")[1] != expected:
            raise SkillCreatorError("无权访问该 Skill 创建任务")

    def _model(self, candidate_id: str) -> tuple[str, str, str]:
        for item in _MODELS:
            if item[0] == candidate_id:
                return item
        raise SkillCreatorError("Skill 候选方案无效")

    def _session_id(self, job_id: str, candidate_id: str) -> str:
        self._model(candidate_id)
        return f"{job_id}-{candidate_id}"

    def _remote_path(
        self, job_id: str, candidate_id: str, filename: str | None = None
    ) -> str:
        base = f"/home/gem/.veadk-skill-creator/{job_id}/{candidate_id}"
        return f"{base}/{filename}" if filename else base

    def _archive_metadata(self, archive: bytes) -> tuple[str, str]:
        if len(archive) > _MAX_ARCHIVE_BYTES:
            raise SkillCreatorError("生成的 Skill 压缩包超过 5 MiB")
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as source:
                infos = source.infolist()
                if not infos:
                    raise SkillCreatorError("Skill 压缩包为空")
                names: set[str] = set()
                file_infos: list[zipfile.ZipInfo] = []
                total_size = 0
                for info in infos:
                    name = info.filename
                    path = PurePosixPath(name)
                    if (
                        not path.parts
                        or path.is_absolute()
                        or "\\" in name
                        or ".." in path.parts
                    ):
                        raise SkillCreatorError("Skill 压缩包包含不安全路径")
                    if name in names:
                        raise SkillCreatorError("Skill 压缩包包含重复路径")
                    names.add(name)
                    mode = info.external_attr >> 16
                    if stat.S_IFMT(mode) == stat.S_IFLNK:
                        raise SkillCreatorError("Skill 压缩包不允许符号链接")
                    if info.is_dir():
                        continue
                    file_infos.append(info)
                    total_size += info.file_size
                if not file_infos or len(file_infos) > 100:
                    raise SkillCreatorError("Skill 文件数必须在 1 到 100 之间")
                if total_size > 2 * 1024 * 1024:
                    raise SkillCreatorError("Skill 文本文件总大小不能超过 2 MiB")
                roots = {PurePosixPath(name).parts[0] for name in names}
                if len(roots) != 1:
                    raise SkillCreatorError("Skill 压缩包必须只有一个根目录")
                root = next(iter(roots))
                skill_md = source.read(f"{root}/SKILL.md").decode("utf-8")
        except (KeyError, UnicodeDecodeError, zipfile.BadZipFile) as error:
            raise SkillCreatorError("Skill 压缩包格式无效") from error
        metadata: dict[str, str] = {}
        lines = skill_md.splitlines()
        if not lines or lines[0].strip() != "---":
            raise SkillCreatorError("SKILL.md frontmatter 无效")
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()
        name = metadata.get("name", "")
        description = metadata.get("description", "")
        if root != name or not _SKILL_NAME_RE.fullmatch(name):
            raise SkillCreatorError("Skill name 或根目录名无效")
        if not description:
            raise SkillCreatorError("Skill description 不能为空")
        return name, description


def mount_skill_creator_routes(
    app: Any,
    owner_resolver: Callable[[Any], str],
) -> SkillCreatorService:
    """Mount the frontend Skill creator API and return its service."""
    service = SkillCreatorService()

    def _http_error(error: SkillCreatorError) -> HTTPException:
        text = str(error)
        status = 404 if "不存在或已过期" in text else 400
        if "无权访问" in text:
            status = 403
        return HTTPException(status_code=status, detail=text)

    @app.get("/web/skill-creator/capabilities")
    async def _skill_creator_capabilities(request: Request) -> dict[str, Any]:
        owner_resolver(request)
        return await run_in_threadpool(service.capabilities)

    @app.post("/web/skill-creator/jobs")
    async def _create_skill_job(
        body: _CreateJobBody, request: Request
    ) -> StreamingResponse:
        owner_id = owner_resolver(request)
        progress_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def report_progress(job: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(
                progress_queue.put_nowait, {"type": "progress", "job": job}
            )

        async def run_job() -> None:
            try:
                result = await run_in_threadpool(
                    service.create_job, body.prompt, owner_id, report_progress
                )
                await progress_queue.put({"type": "complete", "job": result})
            except SkillCreatorError as error:
                await progress_queue.put({"type": "error", "error": str(error)})
            except Exception:
                await progress_queue.put(
                    {"type": "error", "error": "创建 AgentKit Sandbox 会话失败"}
                )
            finally:
                await progress_queue.put(None)

        task = asyncio.create_task(run_job())

        async def stream_events() -> AsyncIterator[str]:
            try:
                while True:
                    event = await progress_queue.get()
                    if event is None:
                        break
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            finally:
                await task

        return StreamingResponse(stream_events(), media_type="application/x-ndjson")

    @app.get("/web/skill-creator/jobs/{job_id}")
    async def _get_skill_job(job_id: str, request: Request) -> dict[str, Any]:
        try:
            return await run_in_threadpool(
                service.get_job, job_id, owner_resolver(request)
            )
        except SkillCreatorError as error:
            raise _http_error(error) from error

    @app.get("/web/skill-creator/jobs/{job_id}/candidates/{candidate_id}/download")
    async def _download_skill_candidate(
        job_id: str, candidate_id: str, request: Request
    ) -> Response:
        try:
            content, filename = await run_in_threadpool(
                service.download,
                job_id,
                candidate_id,
                owner_resolver(request),
            )
        except SkillCreatorError as error:
            raise _http_error(error) from error
        return Response(
            content=content,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/web/skill-creator/jobs/{job_id}/candidates/{candidate_id}/publish")
    async def _publish_skill_candidate(
        job_id: str,
        candidate_id: str,
        body: _PublishBody,
        request: Request,
    ) -> dict[str, Any]:
        try:
            return await run_in_threadpool(
                service.publish,
                job_id,
                candidate_id,
                owner_resolver(request),
                skill_space_ids=body.skill_space_ids,
                project_name=body.project_name,
                skill_id=body.skill_id,
            )
        except SkillCreatorError as error:
            raise _http_error(error) from error

    @app.delete("/web/skill-creator/jobs/{job_id}")
    async def _delete_skill_job(job_id: str, request: Request) -> dict[str, bool]:
        try:
            await run_in_threadpool(service.delete_job, job_id, owner_resolver(request))
        except SkillCreatorError as error:
            raise _http_error(error) from error
        return {"deleted": True}

    return service
