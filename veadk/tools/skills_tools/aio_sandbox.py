# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
# SPDX-License-Identifier: Apache-2.0

"""Session-bound Skill discovery and tools for the AIO sandbox data plane."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import posixpath
import sys
import uuid
from datetime import datetime, timezone

import httpx
from google.adk.tools import FunctionTool

from veadk.agents._remote_sandbox.client import create_agentkit_client
from veadk.agents._remote_sandbox.session import ensure_agentkit_session_lease
from veadk.agents._remote_sandbox.timeout import timeout as execution_timeout
from veadk.utils.logger import get_logger

logger = get_logger(__name__)
STATE_KEY = "_veadk_aio_sandbox"
_MAX_RESPONSE = 4 * 1024 * 1024
_MAX_OUTPUT = 50_000
_TERMINAL = {"completed", "killed", "timed_out"}


def validate_paths(paths):
    if any(not path.startswith("/") or "\0" in path for path in paths):
        raise ValueError("aio_sandbox skills must be absolute sandbox directory paths")


def _identity(context):
    session = context.session
    return hashlib.sha256(
        json.dumps([session.app_name, session.user_id, session.id]).encode()
    ).hexdigest()


def _bound_session(binding, identity):
    from agentkit.sdk.tools.types import GetSessionRequest

    if (
        not isinstance(binding, dict)
        or binding.get("identity") != identity
        or binding.get("tool_id") != os.environ.get("AGENTKIT_TOOL_ID")
        or not binding.get("session_id")
    ):
        raise RuntimeError("AIO sandbox binding does not match this Session")
    try:
        session = create_agentkit_client().get_session(
            GetSessionRequest(
                ToolId=binding["tool_id"], SessionId=binding["session_id"]
            )
        )
    except Exception:
        raise RuntimeError("Unable to resolve bound AIO sandbox") from None
    if (session.status or "").lower() != "ready":
        raise RuntimeError("Bound AIO sandbox is not Ready")
    expiry = getattr(session, "expire_at", None)
    if expiry:
        try:
            expires = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= datetime.now(timezone.utc):
                raise RuntimeError("Bound AIO sandbox has expired")
        except ValueError:
            raise RuntimeError("Invalid AIO sandbox expiry") from None
    return session


async def prepare_aio_sandbox(callback_context):
    """Bind once before inference; persist identifiers through ADK state deltas."""
    identity = _identity(callback_context)
    binding = callback_context.state.get(STATE_KEY)
    if binding is not None:
        await asyncio.to_thread(_bound_session, binding, identity)
        return None
    tool_id = os.environ.get("AGENTKIT_TOOL_ID")
    if not tool_id:
        raise ValueError("AGENTKIT_TOOL_ID is required for aio_sandbox")
    try:
        lease = await asyncio.to_thread(
            ensure_agentkit_session_lease,
            tool_id=tool_id,
            tool_user_session_id="veadk-aio-" + identity,
        )
    except Exception:
        raise RuntimeError("Unable to bind AIO sandbox Session") from None
    callback_context.state[STATE_KEY] = {
        "tool_id": tool_id,
        "session_id": lease.session_id,
        "identity": identity,
    }
    return None


async def resolve_endpoint(context):
    binding = context.state.get(STATE_KEY)
    if binding is None:
        raise RuntimeError("AIO sandbox Session has not been bound")
    session = await asyncio.to_thread(_bound_session, binding, _identity(context))
    endpoint = session.endpoint or session.internal_endpoint
    if not endpoint:
        raise RuntimeError("Bound AIO sandbox has no endpoint")
    return endpoint


async def _headers(context):
    headers = {}
    key = os.environ.get("SANDBOX_API_KEY")
    if key:
        headers["X-API-Key"] = key
    invocation = getattr(context, "_invocation_context", None)
    if invocation is not None and invocation.credential_service:
        from google.adk.agents.callback_context import CallbackContext
        from veadk.utils.auth import build_auth_config

        credential = await invocation.credential_service.load_credential(
            auth_config=build_auth_config(
                credential_key="inbound_auth",
                auth_method="header",
                header_scheme="bearer",
            ),
            callback_context=CallbackContext(invocation),
        )
        if credential:
            token = credential.api_key
            if not token and credential.http and credential.http.credentials:
                token = credential.http.credentials.token
            if not token and credential.oauth2:
                token = credential.oauth2.access_token
            if token:
                headers["inbound_auth"] = token
    return headers


class Sandbox:
    """No shared connection, filesystem or environment from the Runtime host."""

    def __init__(self, endpoint, headers=None):
        try:
            self.url = httpx.URL(endpoint)
        except Exception:
            raise ValueError("Invalid AIO sandbox endpoint") from None
        if (
            self.url.scheme not in {"https", "http"}
            or not self.url.host
            or self.url.userinfo
            or self.url.fragment
        ):
            raise ValueError("Invalid AIO sandbox endpoint")
        self.headers = headers or {}

    async def call(self, method, path, body=None, *, paths=None):
        url = self.url.copy_with(path=self.url.path.rstrip("/") + path)
        if paths:
            url = url.copy_merge_params([("path", p) for p in paths])
        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=httpx.Timeout(30, connect=10),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                async with client.stream(method, url, json=body) as response:
                    if response.status_code != 200:
                        raise RuntimeError(f"AIO sandbox HTTP {response.status_code}")
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > _MAX_RESPONSE:
                            raise RuntimeError(
                                "AIO sandbox response exceeds size limit"
                            )
        except httpx.HTTPError:
            raise RuntimeError(
                "AIO sandbox transport failure; operation may have completed"
            ) from None
        try:
            envelope = json.loads(raw)
        except (ValueError, UnicodeError):
            raise RuntimeError("Invalid AIO sandbox response") from None
        if not isinstance(envelope, dict) or envelope.get("success") is not True:
            raise RuntimeError("AIO sandbox operation failed")
        data = envelope.get("data")
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise RuntimeError("Invalid AIO sandbox result")
        if data.get("error"):
            raise RuntimeError("AIO sandbox editor failed")
        return data

    async def bash(self, command, timeout):
        if not command:
            raise ValueError("command must not be empty")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        sid = "veadk-" + uuid.uuid4().hex
        terminal = False
        output = ""
        truncated = False

        def append(result):
            nonlocal output, truncated
            chunk = (result.get("stdout") or "") + (result.get("stderr") or "")
            truncated = truncated or len(output) + len(chunk) > _MAX_OUTPUT
            output = (output + chunk)[:_MAX_OUTPUT]

        async def cleanup():
            failed = False
            if not terminal:
                try:
                    await self.call(
                        "POST",
                        "/v1/bash/kill",
                        {"session_id": sid, "signal": "SIGKILL"},
                    )
                except Exception:
                    failed = True
            try:
                await self.call("POST", f"/v1/bash/sessions/{sid}/close", {})
            except Exception:
                failed = True
            if failed:
                raise RuntimeError(
                    "AIO sandbox shell cleanup failed; execution state is unknown"
                )

        try:
            async with execution_timeout(timeout):
                await self.call(
                    "POST",
                    "/v1/bash/sessions/create",
                    {"session_id": sid, "exec_dir": "/workspace"},
                )
                result = await self.call(
                    "POST",
                    "/v1/bash/exec",
                    {
                        "session_id": sid,
                        "command": command,
                        "async_mode": True,
                        "hard_timeout": timeout,
                        "max_output_length": _MAX_OUTPUT,
                    },
                )
                append(result)
                while result.get("status") not in _TERMINAL:
                    if not result.get("command_id"):
                        raise RuntimeError("Invalid AIO bash command response")
                    data = await self.call(
                        "POST",
                        "/v1/bash/output",
                        {
                            "session_id": sid,
                            "command_id": result["command_id"],
                            "offset": result.get("offset", 0),
                            "stderr_offset": result.get("stderr_offset", 0),
                            "wait": True,
                            "wait_timeout": 1,
                        },
                    )
                    append(data)
                    if data.get("stdout_gap") or data.get("stderr_gap"):
                        raise RuntimeError("AIO bash output was lost")
                    info = data.get("command")
                    if not isinstance(info, dict):
                        raise RuntimeError("Invalid AIO bash output response")
                    result.update(info)
                    result.update(
                        offset=data.get("offset", 0),
                        stderr_offset=data.get("stderr_offset", 0),
                    )
                    if result.get("status") not in _TERMINAL:
                        await asyncio.sleep(0.1)
                terminal = True
                if type(result.get("exit_code")) not in {int, type(None)}:
                    raise RuntimeError("Invalid AIO bash exit code")
                if result["status"] != "completed" or result.get("exit_code") != 0:
                    raise RuntimeError(
                        f"AIO bash failed ({result['status']}, exit_code={result.get('exit_code')})"
                    )
                return output + ("\n[output truncated]" if truncated else "")
        finally:
            primary = sys.exc_info()[1]
            task = asyncio.create_task(cleanup())
            try:
                await asyncio.wait_for(asyncio.shield(task), 10)
            except asyncio.CancelledError:
                # A new cancellation can arrive while successful execution is
                # closing its shell. Finish cleanup, then preserve cancellation.
                try:
                    await asyncio.wait_for(asyncio.shield(task), 10)
                except (Exception, asyncio.CancelledError):
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    logger.error(
                        "AIO sandbox shell cleanup failed; execution state is unknown"
                    )
                raise
            except Exception:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                if primary is None:
                    raise RuntimeError(
                        "AIO sandbox shell cleanup failed; execution state is unknown"
                    ) from None
                logger.error(
                    "AIO sandbox shell cleanup failed; execution state is unknown"
                )


def _path(file_path):
    if not file_path or "\0" in file_path:
        raise ValueError("file_path must be nonempty")
    return posixpath.normpath(posixpath.join("/workspace", file_path))


async def build_aio_tools(context, paths):
    sandbox = Sandbox(await resolve_endpoint(context), await _headers(context))
    catalog = await sandbox.call("GET", "/v1/skills", paths=paths)
    skills = catalog.get("skills")
    if not isinstance(skills, list):
        raise RuntimeError("Invalid AIO Skill catalog")
    by_name = {}
    for skill in skills:
        if not isinstance(skill, dict) or any(
            not isinstance(skill.get(k), str) or not skill[k].strip()
            for k in ("name", "description", "path")
        ):
            raise RuntimeError("Invalid AIO Skill metadata")
        if skill["name"] in by_name or not skill["path"].startswith("/"):
            raise RuntimeError("Invalid or duplicate AIO Skill metadata")
        by_name[skill["name"]] = skill

    async def skills_tool(command: str) -> str:
        """Load a Skill by name, then follow its instructions using sandbox tools."""
        if command not in by_name:
            raise ValueError("Unknown sandbox Skill")
        data = await sandbox.call(
            "POST", "/v1/file/read", {"file": by_name[command]["path"]}
        )
        if not isinstance(data.get("content"), str):
            raise RuntimeError("Invalid AIO Skill content")
        return (
            f"Base directory for this skill: {posixpath.dirname(by_name[command]['path'])}\n\n"
            + data["content"]
        )

    async def bash_tool(command: str, description: str, timeout: float = 600.0) -> str:
        """Execute a command inside the bound sandbox, in /workspace. No host environment is forwarded."""
        return await sandbox.bash(command, timeout)

    async def read_file_tool(file_path: str, offset: int, limit: int) -> str:
        """Read a sandbox file with line numbers. Offset is 1-based; zero limit reads all lines."""
        if offset < 0 or limit < 0:
            raise ValueError("offset and limit must be nonnegative")
        # FileRead ranges are zero-based; format the selected text like local tools.
        start = max(offset - 1, 0)
        body = {"file": _path(file_path), "start_line": start}
        if limit:
            body["end_line"] = start + limit
        data = await sandbox.call("POST", "/v1/file/read", body)
        if not isinstance(data.get("content"), str):
            raise RuntimeError("Invalid AIO file content")
        return (
            "\n".join(
                f"{i:6d}|{line[:2000]}"
                for i, line in enumerate(data["content"].splitlines(), start + 1)
            )
            or "File is empty."
        )

    async def write_file_tool(file_path: str, content: str) -> str:
        """Write a file in the bound sandbox, overwriting existing content."""
        await sandbox.call(
            "POST", "/v1/file/write", {"file": _path(file_path), "content": content}
        )
        return f"Successfully wrote to {file_path}"

    async def edit_file_tool(
        file_path: str, old_string: str, new_string: str, replace_all: bool
    ) -> str:
        """Edit a sandbox file by exact match; require a unique match unless replace_all is true."""
        if not old_string or old_string == new_string:
            raise ValueError("old_string must be nonempty and differ from new_string")
        data = await sandbox.call(
            "POST",
            "/v1/file/str_replace_editor",
            {
                "command": "str_replace",
                "path": _path(file_path),
                "old_str": old_string,
                "new_str": new_string,
                "replace_mode": "ALL" if replace_all else None,
            },
        )
        return data.get("output", "File edited successfully")

    skill_tool = FunctionTool(skills_tool)
    skill_tool.description += (
        "\nAvailable Skills (paths are inside the sandbox):\n"
        + json.dumps(skills, ensure_ascii=False)
    )
    return [
        skill_tool,
        *(
            FunctionTool(fn)
            for fn in (bash_tool, read_file_tool, write_file_tool, edit_file_tool)
        ),
    ]
