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

"""Send a text task to server.py and display its ADK event stream."""

import argparse
import asyncio
import json
import sys
from urllib.parse import quote

import httpx


async def session_id_for(client, app_name, user_id, session_id=None):
    path = f"/apps/{quote(app_name, safe='')}/users/{quote(user_id, safe='')}/sessions"
    if session_id:
        response = await client.get(f"{path}/{quote(session_id, safe='')}")
        response.raise_for_status()
        return response.json()["id"]
    response = await client.post(path, json={})
    response.raise_for_status()
    return response.json()["id"]


async def stream_events(client, *, app_name, user_id, session_id, task):
    body = {
        "appName": app_name,
        "userId": user_id,
        "sessionId": session_id,
        "newMessage": {"role": "user", "parts": [{"text": task}]},
        "streaming": True,
    }
    async with client.stream("POST", "/run_sse", json=body) as response:
        response.raise_for_status()
        data = []
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                data.append(line[5:].lstrip(" "))
            elif not line and data:
                yield json.loads("\n".join(data))
                data.clear()
        if data:
            yield json.loads("\n".join(data))


class EventPrinter:
    def __init__(self):
        self.segment = None
        self.author = None

    def finish(self):
        if self.segment is not None:
            print(flush=True)
            self.segment = None

    def __call__(self, event):
        error = event.get("error") or event.get("errorMessage")
        if error:
            self.finish()
            raise RuntimeError(str(error))
        final = False
        parts = (event.get("content") or {}).get("parts", [])
        author = event.get("author", "unknown")
        if parts and author != self.author:
            self.finish()
            self.author = author

        for part in parts:
            if "functionCall" in part or "functionResponse" in part:
                self.finish()
                key = "functionCall" if "functionCall" in part else "functionResponse"
                label = "tool" if key == "functionCall" else "tool result"
                print(
                    f"[{label}]", json.dumps(part[key], ensure_ascii=False), flush=True
                )
            elif part.get("text"):
                if part.get("thought"):
                    label = "progress"
                elif event.get("partial"):
                    label = "delta"
                else:
                    label = "answer"
                    final = True
                if label in {"progress", "delta"}:
                    if self.segment != label:
                        self.finish()
                        print(f"[{label}] ", end="", flush=True)
                        self.segment = label
                    print(part["text"], end="", flush=True)
                else:
                    self.finish()
                    print(f"[{label}] {part['text']}", flush=True)
        return final


async def run(args):
    # Match the agent's execution/readiness budget, allowing quiet long-running tasks.
    async with httpx.AsyncClient(
        base_url=args.url.rstrip("/"),
        timeout=httpx.Timeout(args.timeout, connect=10),
        trust_env=False,
    ) as client:
        session_id = await session_id_for(
            client, args.app_name, args.user_id, args.session_id
        )
        print(f"session_id={session_id}", flush=True)
        print("Reuse this ID with --session-id for the next turn.", flush=True)
        final = False
        display_event = EventPrinter()
        try:
            async for event in stream_events(
                client,
                app_name=args.app_name,
                user_id=args.user_id,
                session_id=session_id,
                task=args.task,
            ):
                final = display_event(event) or final
        finally:
            display_event.finish()
        if not final:
            raise RuntimeError(
                "Stream ended without a final answer; execution is unconfirmed. Do not automatically resubmit."
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", help="Text task to execute in the sandbox")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--app-name", default="remote_sandbox_demo")
    parser.add_argument("--user-id", default="demo_user")
    parser.add_argument("--session-id", help="Resume an existing session for this user")
    parser.add_argument("--timeout", type=float, default=1500)
    args = parser.parse_args()
    if not args.task.strip():
        parser.error("task must contain text")
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    try:
        asyncio.run(run(args))
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
