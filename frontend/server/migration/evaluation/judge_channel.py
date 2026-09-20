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

"""Durable request/response channel between the in-Sandbox judge and Studio.

The evaluation runner stays the orchestrator: it owns batching, the thread record, the
batch cache, and the report.  Studio owns the one capability the Sandbox cannot host -
a Codex app-server turn that delivers its verdict through a dynamic tool - so the two
sides meet on a single-slot file channel inside the Sandbox:

* the runner writes ``request.json`` for the batch it is judging and waits for the
  ``response.json`` that names the same request id;
* Studio reads the request, runs one app-server turn, and writes that response.

The channel is a pure contract: it holds the file names, the enable switch, and the
dynamic tool name so both sides cannot drift, and it imports nothing from the rest of
the migration package.

Request::

    {"schema_version": 1, "request_id": "batch-001-010-attempt-1",
     "batch_start": 0, "batch_end": 10, "case_ids": ["case-1"],
     "dimensions": ["semantic_fidelity"], "prompt_version": 4,
     "thread_id": "", "created_at": "2025-01-01T00:00:00Z", "prompt": "...",
     "budget_seconds": 360,
     "case_context": [{"case_id": "case-1", "state": "succeeded",
                       "criteria": True, "contract": False,
                       "runtime_observation": True}]}

Response on success::

    {"schema_version": 1, "request_id": "batch-001-010-attempt-1", "ok": True,
     "thread_id": "thread-1", "cases": [...], "created_at": "..."}

Response on failure, so the runner falls back to ``codex exec`` instead of waiting for
a turn that will never arrive::

    {"schema_version": 1, "request_id": "batch-001-010-attempt-1", "ok": False,
     "thread_id": "", "error": {"code": "judge_turn_unavailable",
                                "message": "..."}}

``budget_seconds`` is how long the runner will wait for the response.  It is the only
deadline in the protocol: Studio sizes its turn to answer inside that window, so a slow
turn reaches the runner as ``ok: false`` while the runner is still listening instead of
as a verdict nobody reads.

Both sides key on the request id, so a response that arrives late, out of order, or
twice is either ignored or replayed for the same batch verdict - never applied to a
different batch.
"""

from __future__ import annotations

import os

JUDGE_CHANNEL_SCHEMA_VERSION = 1
JUDGE_CHANNEL_DIRECTORY = "judge"
JUDGE_REQUEST_NAME = "request.json"
JUDGE_RESPONSE_NAME = "response.json"

JUDGE_TOOL_NAME = "reportEvaluation"
JUDGE_APP_SERVER_ENV = "AGENTKIT_MIGRATION_JUDGE_APP_SERVER"
_DISABLED_VALUES = {"0", "false", "no", "off"}

EVALUATION_RESULTS_DIRECTORY = "results"
EVALUATION_ATTEMPT_DIRECTORY_PREFIX = "attempt-"

__all__ = [
    "EVALUATION_ATTEMPT_DIRECTORY_PREFIX",
    "EVALUATION_RESULTS_DIRECTORY",
    "JUDGE_APP_SERVER_ENV",
    "JUDGE_CHANNEL_DIRECTORY",
    "JUDGE_CHANNEL_SCHEMA_VERSION",
    "JUDGE_REQUEST_NAME",
    "JUDGE_RESPONSE_NAME",
    "JUDGE_TOOL_NAME",
    "evaluation_result_root",
    "judge_app_server_enabled",
    "judge_channel_paths",
]


def judge_app_server_enabled() -> bool:
    """Whether batch judging runs through the app-server instead of ``codex exec``.

    The runner still owns batching, the thread record, the batch cache, and the report;
    Studio only answers the judge request.  Set ``AGENTKIT_MIGRATION_JUDGE_APP_SERVER=0``
    to pin the scripted judge, which the runner also falls back to whenever this path
    cannot deliver a batch.
    """
    return os.getenv(JUDGE_APP_SERVER_ENV, "").strip().lower() not in _DISABLED_VALUES


def evaluation_result_root(evaluation_root: str, attempt: int) -> str:
    """Return the directory that holds one evaluation attempt's durable results."""
    return (
        f"{evaluation_root.rstrip('/')}/{EVALUATION_RESULTS_DIRECTORY}/"
        f"{EVALUATION_ATTEMPT_DIRECTORY_PREFIX}{attempt}"
    )


def judge_channel_paths(evaluation_root: str, attempt: int) -> tuple[str, str]:
    """Return the ``(request_path, response_path)`` of one evaluation attempt."""
    base = (
        f"{evaluation_result_root(evaluation_root, attempt)}/{JUDGE_CHANNEL_DIRECTORY}"
    )
    return (
        f"{base}/{JUDGE_REQUEST_NAME}",
        f"{base}/{JUDGE_RESPONSE_NAME}",
    )
