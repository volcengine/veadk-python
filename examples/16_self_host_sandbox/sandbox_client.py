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

"""Self-Hosted Sandbox client using official Anthropic Python SDK (client.beta.sessions & events).

Endpoints managed via Anthropic SDK:
1. client.beta.sessions.create:
   Creates a session and enqueues work into the WorkQueue for the worker.
2. client.beta.sessions.events.send:
   Publishes ``agent.tool_use`` and ``session.status_idle`` events.
3. client.beta.sessions.events.list:
   Retrieves session events to wait for ``user.tool_result`` from workers.
"""

import base64
import html
import json
import logging
import os
import re
import shlex
import time
import uuid
from typing import Any, Dict, List, Optional

import anthropic

logger = logging.getLogger("veadk.sandbox")


class SelfHostSandboxClient:
    """Client for Managed Agents Self-Hosted Sandbox backed by official Anthropic SDK."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        environment_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        bearer_token: Optional[str] = None,
        account_id: Optional[str] = None,
        remote_bash_tool_name: Optional[str] = None,
        timeout: int = 120,
    ):
        self.base_url = (
            base_url
            or os.getenv("ANTHROPIC_BASE_URL")
            or os.getenv("SANDBOX_BASE_URL", "")
        ).rstrip("/")
        self.environment_id = (
            environment_id
            or os.getenv("ANTHROPIC_ENVIRONMENT_ID")
            or os.getenv("SANDBOX_ENVIRONMENT_ID", "env_01SLqXHseguCmohifEqeUAYu")
        )
        self.agent_id = agent_id or os.getenv(
            "SANDBOX_AGENT_ID", "agent_011CSd8hFhXGpz33bM1pBw7y"
        )
        self.session_id = session_id or os.getenv("SANDBOX_SESSION_ID")

        raw_token = (
            bearer_token
            or os.getenv("ANTHROPIC_ENVIRONMENT_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("SANDBOX_BEARER_TOKEN")
            or os.getenv("SANDBOX_API_KEY", "")
        )
        if raw_token.startswith("Bearer "):
            raw_token = raw_token[7:].strip()
        self.bearer_token = raw_token
        self.account_id = account_id or os.getenv("X_TOP_ACCOUNT_ID", "")
        self.remote_bash_tool_name = remote_bash_tool_name or os.getenv(
            "SANDBOX_BASH_TOOL_NAME", "bash"
        )
        self.timeout = int(os.getenv("SANDBOX_TIMEOUT_SECONDS", str(timeout)))

        if not self.base_url:
            raise ValueError(
                "ANTHROPIC_BASE_URL (or SANDBOX_BASE_URL) must be configured in .env or arguments."
            )
        if not self.bearer_token:
            raise ValueError(
                "ANTHROPIC_ENVIRONMENT_KEY (or SANDBOX_BEARER_TOKEN) must be configured in .env or arguments."
            )

        # The Runtime gateway needs the Managed Agents beta flag and, when
        # supplied, the Volcengine top-account routing header.
        default_headers = {
            "anthropic-beta": "managed-agents-2026-04-01",
        }
        if self.account_id:
            default_headers["X-Top-Account-Id"] = str(self.account_id)

        self.client = anthropic.Anthropic(
            base_url=self.base_url,
            auth_token=self.bearer_token,
            default_headers=default_headers,
            timeout=float(self.timeout),
        )

    def create_session(
        self,
        title: str = "VeADK Self-Hosted Sandbox Session",
    ) -> Dict[str, Any]:
        """POST /v1/sessions via Anthropic SDK (client.beta.sessions.create).

        Creates a session and enqueues a work item into managed_selfhost_work_items.
        """
        sess = self.client.beta.sessions.create(
            agent=self.agent_id,
            environment_id=self.environment_id,
            title=title,
        )
        self.session_id = sess.id
        logger.info(
            "Session %s created on remote Runtime via Anthropic SDK.", self.session_id
        )
        if hasattr(sess, "model_dump"):
            return sess.model_dump(warnings=False)
        return {
            "id": sess.id,
            "environment_id": self.environment_id,
            "agent": self.agent_id,
        }

    def post_events(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """POST /v1/sessions/{session_id}/events via Anthropic SDK (client.beta.sessions.events.send).

        Dispatches tool calls and tool results into the Session event stream.
        """
        if not self.session_id:
            self.create_session()

        response = self.client.beta.sessions.events.send(
            session_id=self.session_id,
            events=events,
        )
        if hasattr(response, "model_dump"):
            return response.model_dump(warnings=False)
        return {"status": "ok"}

    def send_tool_result(
        self, tool_use_id: str, content: str, is_error: bool = False
    ) -> Dict[str, Any]:
        """Send tool execution result to POST /v1/sessions/{session_id}/events."""
        event = {
            "type": "user.tool_result",
            "tool_use_id": tool_use_id,
            "content": [{"type": "text", "text": content}],
            "is_error": is_error,
        }
        return self.post_events([event])

    def list_events(
        self,
        *,
        limit: int = 100,
        order: str = "asc",
    ) -> List[Dict[str, Any]]:
        """Read and normalize events from GET /v1/sessions/{id}/events via Anthropic SDK."""
        if not self.session_id:
            raise RuntimeError("Cannot read events before a Session is created.")

        page = self.client.beta.sessions.events.list(
            session_id=self.session_id,
            limit=limit,
            order=order,
        )
        events: List[Dict[str, Any]] = []
        for item in page.data:
            if hasattr(item, "model_dump"):
                d = item.model_dump(warnings=False)
            elif isinstance(item, dict):
                d = dict(item)
            else:
                d = {
                    "id": getattr(item, "id", None),
                    "type": getattr(item, "type", None),
                    "name": getattr(item, "name", None),
                    "input": getattr(item, "input", None),
                    "content": getattr(item, "content", None),
                    "is_error": getattr(item, "is_error", False),
                    "tool_use_id": getattr(item, "tool_use_id", None),
                }
            events.append(d)
        return events

    def post_status_idle(self, stop_reason: str = "end_turn") -> None:
        """Publish a ``session.status_idle`` event so workers know the turn ended and can release their lease."""
        if not self.session_id:
            return
        try:
            self.post_events(
                [
                    {
                        "type": "session.status_idle",
                        "stop_reason": {
                            "type": stop_reason,
                        },
                    }
                ]
            )
            logging.info(
                "Session %s marked status_idle (%s).", self.session_id, stop_reason
            )
        except Exception as e:
            logging.warning(
                "Failed to post session.status_idle for %s: %s", self.session_id, e
            )

    def dispatch_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        *,
        dispatch_id: str = "",
    ) -> Dict[str, Any]:
        """Convert a VeADK tool to bash and publish an ``agent.tool_use``."""
        command, timeout = self._tool_to_bash(tool_name, arguments)
        return self.execute_command(
            command,
            timeout=timeout,
            dispatch_id=dispatch_id,
        )

    def _tool_to_bash(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> tuple[str, float]:
        """Translate supported non-MCP tools into one remote bash invocation."""
        timeout = self._positive_timeout(arguments.get("timeout", self.timeout))
        if tool_name == "bash":
            cmd = self._required_string(arguments, "command", tool_name)
            return html.unescape(cmd), timeout

        if tool_name == "read_file":
            file_path = self._required_string(arguments, "file_path", tool_name)
            offset = arguments.get("offset")
            limit = arguments.get("limit")
            quoted_path = shlex.quote(file_path)
            if offset is None and limit is None:
                return f"cat -- {quoted_path}", timeout
            start = self._positive_integer(
                offset if offset is not None else 1, "offset"
            )
            if limit is None:
                condition = f"NR >= {start}"
            else:
                line_limit = self._positive_integer(limit, "limit")
                condition = f"NR >= {start} && NR < {start + line_limit}"
            awk_program = f'{condition} {{printf "%d\\t%s\\n", NR, $0}}'
            return f"awk {shlex.quote(awk_program)} {quoted_path}", timeout

        if tool_name == "write_file":
            file_path = self._required_string(arguments, "file_path", tool_name)
            content = self._required_string(
                arguments, "content", tool_name, allow_empty=True
            )
            encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
            quoted_path = shlex.quote(file_path)
            command = (
                f"mkdir -p $(dirname -- {quoted_path}) && "
                f"printf %s {shlex.quote(encoded)} | base64 -d > {quoted_path}"
            )
            return command, timeout

        if tool_name == "edit_file":
            payload = {
                "file_path": self._required_string(arguments, "file_path", tool_name),
                "old_string": self._required_string(arguments, "old_string", tool_name),
                "new_string": self._required_string(
                    arguments, "new_string", tool_name, allow_empty=True
                ),
                "replace_all": bool(arguments.get("replace_all", False)),
            }
            encoded = base64.b64encode(
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
            ).decode("ascii")
            script = (
                "import base64,json,pathlib,sys;"
                "d=json.loads(base64.b64decode(sys.argv[1]));"
                "p=pathlib.Path(d['file_path']);s=p.read_text();o=d['old_string'];"
                "n=s.count(o);"
                "(_ for _ in ()).throw(ValueError('old_string not found')) if n==0 else None;"
                "(_ for _ in ()).throw(ValueError(f'old_string appears {n} times')) "
                "if n>1 and not d['replace_all'] else None;"
                "p.write_text(s.replace(o,d['new_string'],-1 if d['replace_all'] else 1))"
            )
            return (
                f"python3 -c {shlex.quote(script)} {shlex.quote(encoded)}",
                timeout,
            )

        if tool_name == "list_files":
            path = str(arguments.get("path") or "/workspace")
            depth = self._positive_integer(arguments.get("max_depth", 4), "max_depth")
            return (
                f"find {shlex.quote(path)} -maxdepth {depth} -type f | sort | head -n 500",
                timeout,
            )

        if tool_name == "search_files":
            pattern = self._required_string(arguments, "pattern", tool_name)
            path = str(arguments.get("path") or "/workspace")
            glob = arguments.get("glob")
            rg_flags = "-n --no-heading"
            grep_flags = "-RIn"
            if arguments.get("case_insensitive"):
                rg_flags += " -i"
                grep_flags += " -i"
            if glob:
                rg_flags += f" --glob {shlex.quote(str(glob))}"
                grep_flags += f" --include {shlex.quote(str(glob))}"
            quoted_pattern = shlex.quote(pattern)
            quoted_path = shlex.quote(path)
            return (
                "if command -v rg >/dev/null 2>&1; then "
                f"rg {rg_flags} -- {quoted_pattern} {quoted_path}; "
                "else "
                f"grep {grep_flags} -- {quoted_pattern} {quoted_path}; fi",
                timeout,
            )

        if tool_name == "python":
            code = self._required_string(arguments, "code", tool_name, allow_empty=True)
            workdir = str(arguments.get("workdir") or "/workspace")
            return (
                f"cd {shlex.quote(workdir)} && python3 -c {shlex.quote(code)}",
                timeout,
            )

        raise ValueError(
            f"Unsupported non-MCP tool {tool_name!r}; add an explicit bash adapter"
        )

    def execute_command(
        self,
        command: str,
        *,
        timeout: float | None = None,
        dispatch_id: str = "",
    ) -> Dict[str, Any]:
        """Publish ``agent.tool_use`` and wait for the Worker's tool result."""
        if not self.session_id:
            self.create_session()

        timeout_seconds = timeout or float(self.timeout)
        command = html.unescape(command)
        tool_use_id = dispatch_id or f"toolu_{uuid.uuid4().hex}"
        self.post_events(
            [
                {
                    "type": "agent.tool_use",
                    "id": tool_use_id,
                    "name": self.remote_bash_tool_name,
                    "input": {
                        "command": command,
                        "timeout_ms": int(timeout_seconds * 1000),
                        "timeout": int(timeout_seconds * 1000),
                    },
                }
            ]
        )
        return self._wait_for_tool_result(
            timeout=timeout_seconds,
            tool_use_id=tool_use_id,
            dispatch_id=dispatch_id or tool_use_id,
        )

    def _wait_for_tool_result(
        self,
        *,
        timeout: float,
        tool_use_id: str,
        dispatch_id: str,
    ) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            events = self.list_events(limit=100, order="asc")
            for event in events:
                event_type = str(event.get("type") or "")
                if event_type not in {"agent.tool_result", "user.tool_result"}:
                    continue
                result_tool_use_id = str(event.get("tool_use_id") or "")
                if result_tool_use_id == tool_use_id:
                    return self._normalize_bash_result(
                        event,
                        tool_use_id=tool_use_id,
                        dispatch_id=dispatch_id,
                    )
            time.sleep(0.5)

        raise TimeoutError(
            f"Timed out after {timeout:g}s waiting for tool result {tool_use_id}."
        )

    @staticmethod
    def _required_string(
        arguments: Dict[str, Any],
        key: str,
        tool_name: str,
        *,
        allow_empty: bool = False,
    ) -> str:
        value = arguments.get(key)
        if not isinstance(value, str) or (not allow_empty and not value.strip()):
            raise ValueError(f"{tool_name} requires a valid {key}")
        return value

    @staticmethod
    def _positive_integer(value: Any, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
        return value

    @staticmethod
    def _positive_timeout(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError("timeout must be greater than zero")
        return float(value)

    def _normalize_bash_result(
        self,
        event: Dict[str, Any],
        *,
        tool_use_id: str,
        dispatch_id: str,
    ) -> Dict[str, Any]:
        content = self._content_text(event.get("content"))
        match = re.match(r"^exit=(-?\d+)\n([\s\S]*)$", content)
        if match:
            exit_code = int(match.group(1))
            stdout = match.group(2)
        else:
            exit_code = 1 if event.get("is_error") else 0
            stdout = content
        return {
            "dispatch_id": dispatch_id,
            "tool_use_id": tool_use_id,
            "environment_id": self.environment_id,
            "session_id": self.session_id,
            "status": "failed" if exit_code else "completed",
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": "",
        }

    @staticmethod
    def _event_seq(event: Dict[str, Any]) -> int:
        try:
            return int(event.get("_seq", 0) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _content_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                elif isinstance(block, str):
                    parts.append(block)
            return "\n".join(part for part in parts if part)
        if content is None:
            return ""
        return json.dumps(content, ensure_ascii=False)
