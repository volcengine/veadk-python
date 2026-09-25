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

"""A local System One endpoint for tests.

It either replays a scripted list of responses or answers each question with a
valid payload of the matching type, so tests can exercise the client, extension,
and tool against real HTTP without a decision model.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast

ScriptedResponse = tuple[int, dict[str, str], dict[str, Any] | None]


@dataclass
class RecordedCall:
    """One request the fake endpoint received."""

    path: str
    authorization: str
    model: str
    state: Any
    questions: dict[str, Any] = field(default_factory=dict)


class FakeSystemOneServer(ThreadingHTTPServer):
    """Serve ``/v1/systemone`` from a script or from generated answers."""

    def __init__(self, script: Sequence[ScriptedResponse] | None = None) -> None:
        super().__init__(("127.0.0.1", 0), _SystemOneHandler)
        self.calls: list[RecordedCall] = []
        self.script: list[ScriptedResponse] = list(script or [])

    @property
    def base_url(self) -> str:
        """Base URL to pass as ``api_base``."""
        return f"http://127.0.0.1:{self.server_address[1]}"

    def next_response(
        self, payload: Mapping[str, Any]
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        """Return the next scripted response, or a generated one."""
        if not self.script:
            return 200, {}, _generated_response(payload)
        status, headers, body = self.script.pop(0)
        return (
            status,
            headers,
            body if body is not None else _generated_response(payload),
        )


class _SystemOneHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        server = cast(FakeSystemOneServer, self.server)
        length = int(self.headers.get("content-length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        server.calls.append(
            RecordedCall(
                path=self.path,
                authorization=self.headers.get("authorization") or "",
                model=str(payload.get("model") or ""),
                state=payload.get("state"),
                questions=dict(payload.get("questions") or {}),
            )
        )
        status, headers, body = server.next_response(payload)
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args: object) -> None:
        """Keep pytest output clean."""


def _generated_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Answer every question with a valid payload of its own type."""
    questions = payload.get("questions") or {}
    return {
        "model": "fake-system-one",
        "answers": {qid: _answer(question) for qid, question in questions.items()},
        "usage": {"input_tokens": 12, "output_tokens": 3},
    }


def _answer(question: Mapping[str, Any]) -> dict[str, Any]:
    kind = question.get("type")
    criteria = question.get("criteria") or {}
    if kind == "choice":
        options = list(criteria) or ["none"]
        return {
            "type": "choice",
            "choice": options[0],
            "confidence": 0.9,
            "probabilities": {option: 0.9 for option in options[:1]},
        }
    if kind == "score":
        levels = list(criteria)
        return {
            "type": "score",
            "score": 1.0,
            "confidence": 0.8,
            "legend": {str(index): level for index, level in enumerate(levels)},
            "probabilities": {"1": 0.8},
        }
    if kind == "noul":
        return {"type": "noul", "noul": 0.9}
    return {"type": str(kind)}


@contextmanager
def fake_system_one(
    script: Sequence[ScriptedResponse] | None = None,
) -> Iterator[FakeSystemOneServer]:
    """Run the fake endpoint for the body of a ``with`` block."""
    server = FakeSystemOneServer(script)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
