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

"""A scripted stand-in for ``pi --mode rpc``, run as a real subprocess.

``tests/runtime/piagent`` fakes Pi with binaries that replay a *fixed* NDJSON
stream, which cannot express the conformance suite's scenarios: a bridged ADK
tool is never actually called, and nothing records what the "model" was asked.
This script is a scripted *model* living inside the Pi process instead:

* the plan (``<CONFORMANCE_PI_DIR>/<model>.plan.json``) is a list of rounds in
  the same shape as ``scripted_backend.Round``; the model name the runtime
  passes as ``--model`` selects the plan, so concurrent turns of different
  agents never share a cursor;
* each round is one backend "request", appended to ``<model>.calls.jsonl`` with
  everything the model could see (prompt, tool results so far, the tools and
  skills Pi was given), which is the Pi arm's equivalent of
  ``ScriptedBackend.calls``;
* a tool call is executed for real, over the per-turn HTTP bridge
  ``PiToolRuntime`` wrote into the generated extension file -- the same hop the
  real Pi extension makes -- so ADK tool execution is under test;
* the cursor persists in ``<model>.cursor`` because every turn is a fresh Pi
  process (the runtime passes ``--no-session``).

It is launched through a tiny executable wrapper the adapter writes (Pi is
resolved from ``PIAGENT_BINARY``), and must stay stdlib-only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

EXHAUSTED_TEXT = "[scripted-backend-exhausted]"


def _emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def _args(argv: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {"extensions": [], "skills": [], "model": ""}
    index = 0
    while index < len(argv):
        arg = argv[index]
        value = argv[index + 1] if index + 1 < len(argv) else ""
        if arg == "--model":
            parsed["model"] = value
            index += 1
        elif arg == "--extension":
            parsed["extensions"].append(value)
            index += 1
        elif arg == "--skill":
            parsed["skills"].append(value)
            index += 1
        index += 1
    return parsed


def _bridge(extensions: list[str]) -> tuple[str, str, list[str]]:
    """Recover (bridge url, token, tool names) from the generated extension."""
    for path in extensions:
        source = Path(path).read_text(encoding="utf-8")
        url = re.search(r"const BRIDGE_URL = (\".*?\");", source)
        token = re.search(r"const TOKEN = (\".*?\");", source)
        names = [
            json.loads(match)
            for match in re.findall(r"pi\.registerTool\(\{\s*name: (\".*?\"),", source)
        ]
        if url and token:
            return json.loads(url.group(1)), json.loads(token.group(1)), names
    return "", "", []


def _skill_texts(skill_dirs: list[str]) -> list[str]:
    texts: list[str] = []
    for skill_dir in skill_dirs:
        manifest = Path(skill_dir) / "SKILL.md"
        if manifest.is_file():
            texts.append(manifest.read_text(encoding="utf-8"))
    return texts


def _call_tool(
    url: str, token: str, name: str, call_id: str, args: dict[str, Any]
) -> dict[str, Any]:
    if not url:
        # Pi itself answers a call to a tool it was never given.
        return {"isError": True, "content": [{"type": "text", "text": "unknown tool"}]}
    body = json.dumps({"toolName": name, "toolCallId": call_id, "args": args})
    request = urllib.request.Request(
        f"{url}/call",
        data=body.encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 - reported to the "model" like Pi does
        return {"isError": True, "content": [{"type": "text", "text": str(e)}]}
    if not payload.get("ok"):
        return {
            "isError": True,
            "content": [{"type": "text", "text": str(payload.get("error"))}],
        }
    return dict(payload.get("result") or {})


def _usage(pair: list[int]) -> dict[str, int]:
    return {
        "input": int(pair[0]),
        "output": int(pair[1]),
        "totalTokens": int(pair[0]) + int(pair[1]),
    }


def main() -> None:
    parsed = _args(sys.argv[1:])
    root = Path(os.environ["CONFORMANCE_PI_DIR"])
    model = parsed["model"]
    plan_path = root / f"{model}.plan.json"
    cursor_path = root / f"{model}.cursor"
    calls_path = root / f"{model}.calls.jsonl"

    with (root / f"{model}.pids").open("a", encoding="utf-8") as handle:
        handle.write(f"{os.getpid()}\n")

    rounds = json.loads(plan_path.read_text(encoding="utf-8"))
    cursor = int(cursor_path.read_text() or "0") if cursor_path.exists() else 0
    bridge_url, token, tool_names = _bridge(parsed["extensions"])
    skills = _skill_texts(parsed["skills"])

    for raw in sys.stdin:
        command = json.loads(raw)
        if command.get("type") != "prompt":
            continue
        _emit(
            {
                "id": command.get("id"),
                "type": "response",
                "command": "prompt",
                "success": True,
            }
        )
        prompt = str(command.get("message") or "")
        tool_results: list[dict[str, Any]] = []
        while True:
            with calls_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "prompt": prompt,
                            "tool_results": tool_results,
                            "tool_names": tool_names,
                            "skills": skills,
                            "extensions": parsed["extensions"],
                            "skill_dirs": parsed["skills"],
                        }
                    )
                    + "\n"
                )
            if cursor < len(rounds):
                rnd = rounds[cursor]
            else:
                rnd = {"texts": [EXHAUSTED_TEXT], "tool_calls": [], "usage": [0, 0]}
            cursor += 1
            cursor_path.write_text(str(cursor))

            if rnd.get("hang"):
                (root / f"{model}.hang").write_text(str(os.getpid()))
                # A model that never answers. Only the runtime tearing the
                # process down ends this.
                while True:
                    time.sleep(3600)

            texts = list(rnd.get("texts") or [])
            for text in texts:
                _emit(
                    {
                        "type": "message_update",
                        "assistantMessageEvent": {"type": "text_delta", "delta": text},
                    }
                )
            _emit(
                {
                    "type": "message_end",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "".join(texts)}],
                        "usage": _usage(rnd.get("usage") or [0, 0]),
                    },
                }
            )
            calls = list(rnd.get("tool_calls") or [])
            if not calls:
                break
            for offset, (name, args) in enumerate(calls):
                call_id = f"pi-call-{cursor}-{offset}"
                _emit(
                    {
                        "type": "tool_execution_start",
                        "toolCallId": call_id,
                        "toolName": name,
                        "args": args,
                    }
                )
                result = _call_tool(
                    bridge_url if name in tool_names else "",
                    token,
                    name,
                    call_id,
                    dict(args),
                )
                _emit(
                    {
                        "type": "tool_execution_end",
                        "toolCallId": call_id,
                        "toolName": name,
                        "result": result,
                        "isError": bool(result.get("isError")),
                    }
                )
                tool_results.append({"name": name, "result": result})
        _emit({"type": "agent_settled"})


if __name__ == "__main__":
    main()
