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

"""Async JSONL RPC client for ``pi --mode rpc``."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections import deque
from typing import Any, AsyncIterator

from veadk.runtime.piagent.config import PiAgentConfig
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class PiAgentRpcError(RuntimeError):
    """Raised when the Pi RPC process or protocol fails."""


class PiAgentRpcClient:
    """Drive a local Pi RPC subprocess."""

    def __init__(self, config: PiAgentConfig):
        self.config = config
        self._proc: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_tail: deque[str] = deque(maxlen=50)

    async def __aenter__(self) -> "PiAgentRpcClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._proc is not None:
            return

        args = [
            self.config.binary_path,
            "--mode",
            "rpc",
            "--no-session",
            "--provider",
            self.config.model.provider_id,
            "--model",
            self.config.model.model,
        ]
        if self.config.disable_tools:
            args.append("--no-tools")
        else:
            if self.config.disable_builtin_tools:
                args.append("--no-builtin-tools")
            if self.config.tool_allowlist:
                args.extend(["--tools", ",".join(self.config.tool_allowlist)])
            if self.config.exclude_tools:
                args.extend(["--exclude-tools", ",".join(self.config.exclude_tools)])
        if self.config.disable_extension_discovery:
            args.append("--no-extensions")
        for extension in self.config.extensions:
            args.extend(["--extension", extension])
        if self.config.project_trust == "deny":
            args.append("--no-approve")
        elif self.config.project_trust == "approve":
            args.append("--approve")
        if self.config.disable_skill_discovery:
            args.append("--no-skills")
        for skill_path in self.config.skill_paths:
            args.extend(["--skill", skill_path])

        env = os.environ.copy()
        env["PI_CODING_AGENT_DIR"] = str(self.config.agent_dir)
        env[self.config.model.api_key_env] = self.config.model.api_key
        env.setdefault("PI_SKIP_VERSION_CHECK", "1")

        logger.info(
            "piagent runtime: starting pi rpc "
            f"provider={self.config.model.provider_id} "
            f"model={self.config.model.model} "
            f"skills={len(self.config.skill_paths)}"
        )
        self._proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.config.workdir),
            env=env,
        )
        self._stderr_task = asyncio.create_task(self._collect_stderr())

    async def prompt(self, message: str) -> AsyncIterator[dict[str, Any]]:
        request_id = f"veadk-{uuid.uuid4().hex}"
        await self._write(
            {
                "id": request_id,
                "type": "prompt",
                "message": message,
            }
        )

        response_seen = False
        saw_agent_end = False
        while True:
            timeout = 1.0 if saw_agent_end else self.config.timeout_seconds
            try:
                item = await self._read(timeout=timeout)
            except TimeoutError:
                if saw_agent_end:
                    return
                await self.abort()
                raise

            if item.get("type") == "response" and item.get("id") == request_id:
                response_seen = True
                if not item.get("success", False):
                    raise PiAgentRpcError(
                        f"Pi rejected prompt: {item.get('error') or item}"
                    )
                continue

            yield item

            event_type = item.get("type")
            if event_type == "agent_settled":
                return
            if event_type == "agent_end":
                saw_agent_end = True
            if (
                event_type == "response"
                and not response_seen
                and not item.get("success", False)
            ):
                raise PiAgentRpcError(f"Pi command failed: {item.get('error') or item}")

    async def abort(self) -> None:
        if self._proc is None or self._proc.stdin is None:
            return
        try:
            await self._write({"type": "abort"})
        except Exception as e:  # noqa: BLE001
            logger.debug(f"piagent runtime: abort failed: {e}")

    async def close(self) -> None:
        proc = self._proc
        if proc is None:
            return
        self._proc = None

        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except TimeoutError:
                proc.kill()
                await proc.wait()

        if self._stderr_task is not None:
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass
            self._stderr_task = None

    async def _write(self, payload: dict[str, Any]) -> None:
        proc = self._require_proc()
        if proc.stdin is None:
            raise PiAgentRpcError("Pi RPC stdin is not available.")
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        proc.stdin.write(line.encode("utf-8"))
        await proc.stdin.drain()

    async def _read(self, *, timeout: float) -> dict[str, Any]:
        proc = self._require_proc()
        if proc.stdout is None:
            raise PiAgentRpcError("Pi RPC stdout is not available.")
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
        if not line:
            stderr = "\n".join(self._stderr_tail)
            raise PiAgentRpcError(
                f"Pi RPC process exited before completion. stderr tail: {stderr}"
            )
        text = line.decode("utf-8").rstrip("\n")
        if text.endswith("\r"):
            text = text[:-1]
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise PiAgentRpcError(f"Invalid JSONL from Pi RPC: {text}") from e

    def _require_proc(self) -> asyncio.subprocess.Process:
        if self._proc is None:
            raise PiAgentRpcError("Pi RPC process has not been started.")
        return self._proc

    async def _collect_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                self._stderr_tail.append(text)
                logger.debug(f"piagent stderr: {text}")
