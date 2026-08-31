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

"""VeADK Agent with Official Managed Agents & Self-Hosted Sandbox Protocol.

Uses the 100% standard Managed Agents REST & SSE protocol:
1. POST /v1/sessions (or /api/sessions): Creates a Session bound to `agent` and `environment_id`.
   The server automatically enqueues the Session into the environment's Work Queue.
2. GET /v1/sessions/{id}/events/stream: Streams events (agent.message, agent.tool_use, etc.).
3. POST /v1/sessions/{id}/events: Sends user messages or tool results back.

Usage:
    python examples/self_host_sandbox_demo.py \
        --base-url "http://localhost:8080" \
        --agent-id "agent_011CSd8hFhXGpz33bM1pBw7y" \
        --env-id "env_01SLqXHseguCmohifEqeUAYu" \
        --api-key "your-api-key" \
        --prompt "请在沙箱 /workspace 下写一个快速排序 quick_sort.py 并运行验证"
"""

import argparse
import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Generator, Optional

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("veadk.managed_agents_sandbox")


# ─────────────────────────────────────────────────────────────
# 1. Standard Managed Agents API Client
# ─────────────────────────────────────────────────────────────
class ManagedAgentsStandardClient:
    """Standard client implementing the Anthropic / OMA Managed Agents HTTP & SSE protocol."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.base_url = (
            base_url
            or os.getenv("ANTHROPIC_BASE_URL")
            or os.getenv("SANDBOX_BASE_URL")
            or "http://127.0.0.1:8080"
        ).rstrip("/")
        self.api_key = (
            api_key
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("SANDBOX_API_KEY")
            or "dummy_key"
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "X-Builder-Environment-Key": self.api_key,
            "anthropic-beta": "managed-agents-2026-04-01",
        }

    def create_session(
        self,
        agent_id: str,
        environment_id: str,
        initial_prompt: str,
        title: str = "VeADK Session",
    ) -> Dict[str, Any]:
        """Standard POST /v1/sessions (or /api/sessions).

        Creating a session with an environment_id automatically triggers the server
        to enqueue a WorkItem for the self-hosted worker.
        """
        payload = {
            "agent": agent_id,
            "environment_id": environment_id,
            "title": title,
            "initial_events": [
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": initial_prompt}],
                }
            ],
        }

        # Try /v1/sessions first, fallback to /api/sessions
        for path in ["/v1/sessions", "/api/sessions"]:
            url = f"{self.base_url}{path}"
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=data, headers=self._headers(), method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 404 and path == "/v1/sessions":
                    continue
                err_text = e.read().decode("utf-8") if e.fp else str(e)
                raise RuntimeError(
                    f"Failed to create session at {url} (HTTP {e.code}): {err_text}"
                ) from e
            except urllib.error.URLError as e:
                raise ConnectionError(
                    f"Cannot connect to Managed Agents Server at {url}: {e}"
                ) from e

        raise RuntimeError("Failed to reach sessions endpoint on server")

    def stream_session_events(
        self, session_id: str
    ) -> Generator[Dict[str, Any], None, None]:
        """Standard GET /v1/sessions/{id}/events/stream (SSE)."""
        for path in [
            f"/v1/sessions/{session_id}/events/stream",
            f"/api/sessions/{session_id}/events/stream",
        ]:
            url = f"{self.base_url}{path}"
            req = urllib.request.Request(
                url, headers={**self._headers(), "Accept": "text/event-stream"}
            )
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    for line in resp:
                        line_str = line.decode("utf-8").strip()
                        if line_str.startswith("data:"):
                            data_str = line_str[5:].strip()
                            if data_str and data_str != "[DONE]":
                                try:
                                    yield json.loads(data_str)
                                except json.JSONDecodeError:
                                    pass
                    return
            except urllib.error.HTTPError as e:
                if e.code == 404 and "/v1/" in path:
                    continue
                err_text = e.read().decode("utf-8") if e.fp else str(e)
                raise RuntimeError(
                    f"SSE Error from {url} (HTTP {e.code}): {err_text}"
                ) from e


# ─────────────────────────────────────────────────────────────
# 2. Main Entry Point
# ─────────────────────────────────────────────────────────────
async def main() -> None:
    parser = argparse.ArgumentParser(
        description="VeADK Standard Managed Agents & Sandbox Demo"
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("SANDBOX_BASE_URL", "http://127.0.0.1:8080"),
        help="Base URL of the Managed Agents Server (default: http://127.0.0.1:8080)",
    )
    parser.add_argument(
        "--agent-id",
        default=os.getenv("SANDBOX_AGENT_ID", "agent_011CSd8hFhXGpz33bM1pBw7y"),
        help="Managed Agent ID",
    )
    parser.add_argument(
        "--env-id",
        default=os.getenv("SANDBOX_ENVIRONMENT_ID", "env_01SLqXHseguCmohifEqeUAYu"),
        help="Self-Hosted Environment ID",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("SANDBOX_API_KEY", "your-api-key"),
        help="API Key for Managed Agents Server",
    )
    parser.add_argument(
        "--prompt",
        default="请在沙箱工作区 /workspace 下创建一个 quick_sort.py 文件，编写快速排序代码并运行验证。",
        help="Task prompt for the agent",
    )
    args = parser.parse_args()

    client = ManagedAgentsStandardClient(base_url=args.base_url, api_key=args.api_key)

    print("=" * 65)
    print("🚀 Standard Managed Agents & Self-Hosted Sandbox Execution")
    print(f"📍 Server Base URL:        {client.base_url}")
    print(f"🤖 Agent ID:               {args.agent_id}")
    print(f"📦 Environment ID:         {args.env_id}")
    print(f"💬 Prompt:                 {args.prompt}")
    print("=" * 65)

    try:
        # Step 1: Create Session via standard API
        print("\n⏳ 正在通过标准 API (POST /v1/sessions) 创建 Session...")
        session = client.create_session(
            agent_id=args.agent_id,
            environment_id=args.env_id,
            initial_prompt=args.prompt,
        )
        session_id = session.get("id", session.get("session_id"))
        print(f"✅ Session 创建成功! Session ID: {session_id}")
        print(
            "   (服务端已自动将该 Session 作为 WorkItem 派发给绑定的 Self-Hosted Worker)"
        )

        # Step 2: Stream Session Events via standard SSE
        print("\n📡 正在连接标准 SSE 事件流 (GET /v1/sessions/:id/events/stream)...")
        for event in client.stream_session_events(session_id):
            event_type = event.get("type", "")

            # 1. 打印 Agent 思考过程与回复
            if event_type == "agent.message":
                print(f"\n🤖 [Agent 回复]:\n{event.get('content', '')}")

            # 2. 打印沙箱工具调用
            elif event_type == "agent.tool_use":
                print(
                    f"🔧 [沙箱工具调用]: {event.get('name')} | 参数: {event.get('input')}"
                )

            # 3. 打印工具在沙箱内的执行结果
            elif event_type == "user.tool_result" or event_type == "agent.tool_result":
                print(f"📥 [沙箱执行回传]: {event.get('content')}")

            # 4. 会话状态变化
            elif event_type == "session.status_idle":
                stop_reason = event.get("stop_reason", {})
                if (
                    isinstance(stop_reason, dict)
                    and stop_reason.get("type") == "end_turn"
                ):
                    print("\n🏁 任务已全部在自建沙箱中执行完毕 (Turn Completed)！")
                    break

    except (ConnectionError, RuntimeError) as e:
        print(f"\n⚠️ 连接或执行提示: {e}")
        print(
            "💡 提示: 请确保服务端（如 open-managed-agents 或 agentscope-service）以及沙箱 Worker (ant beta:worker poll) 已启动运行。"
        )


if __name__ == "__main__":
    asyncio.run(main())
