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

"""Optional, bounded ingestion of this request's authorized original sources."""

from __future__ import annotations

import asyncio
import copy
import time

from .attempts import current_attempts
from .budget import count_input, request_payload, resolve_payload_budget
from .defaults import DefaultContextRetriever
from .evidence import repeated_projection
from .history import eligible_prefix_end
from .references import archive_history, handle, identity, resolve
from .retrieval import MAX_PREVIEW_SOURCES, MAX_SOURCE_BYTES
from .tool_results import _compression_candidates


def _sources(request, scope, config, available, history_pressure):
    # Reuse projection eligibility, without publishing references or mutating
    # input/Session state. Do not index arbitrary Session events or recent turns.
    discovery = copy.copy(scope)
    discovery.pending_state = dict(scope.pending_state)
    discovery.projection_bytes = max(256, int(available * 0.3))
    found = False
    for _, _, text, source, _, _, _ in _compression_candidates(
        request, discovery, config
    ):
        if config.tool_result_max_bytes >= 16000 and repeated_projection(text):
            continue
        found = True
        yield source, text
    # Tool sources have priority. Avoid indexing the same large tool payload
    # again inside a history archive before knowing whether it is needed.
    if not found and history_pressure:
        end = eligible_prefix_end(request.contents, config.keep_recent_turns)
        if any(
            part.text is None or set(part.model_dump(exclude_none=True)) != {"text"}
            for content in request.contents[:end]
            for part in content.parts or []
        ):
            return
        refs = {}
        reference = (
            archive_history(discovery, request.contents[:end], refs) if end else None
        )
        if reference:
            source = refs[reference]
            text = resolve(scope, source)
            if text is not None:
                yield source, text


async def prepare_request_index(request, model, config, additional_args, scope):
    """Preparation has its own cumulative invocation budget, inside turn time.

    Explicitly supplied retrievers retain their caller-owned ingestion lifecycle.
    Completed batches survive in SQLite; partial indexes never count as complete.
    Failure is optional, caller cancellation and exhausted turn budgets are not.
    """
    owner = scope.evidence_retriever
    if (
        not config.prepare_index
        or config.mode == "off"
        or config.retrieval == "lexical"
        or scope.compression_owner == "legacy_harness"
        or not isinstance(owner, DefaultContextRetriever)
        or request.previous_interaction_id
    ):
        return
    payload = {
        **additional_args,
        **request_payload(request),
        "model": request.model or model.model,
    }
    budget = resolve_payload_budget(payload, config)
    tokens = count_input(request_payload(request), config)
    if budget is None or tokens < budget.available * config.trigger_ratio:
        return
    if scope.index_preparation_remaining is None:
        scope.index_preparation_remaining = config.index_preparation_timeout_seconds
    duration = scope.index_preparation_remaining
    ledger = current_attempts.get()
    remaining = ledger.remaining() if ledger else None
    if remaining is not None:
        # Leave at least half the remaining turn for retrieval and generation.
        duration = min(duration, remaining * 0.5)
    scope.index_preparation_results = []
    if duration <= 0:
        scope.index_preparation_status = "budget_exhausted"
        return
    started = time.monotonic()
    deadline = started + duration
    scope.index_preparation_status = "not_requested"

    async def prepare():
        seen = set()
        available = budget.available - min(1024, budget.available // 20)
        for source, text in _sources(
            request,
            scope,
            config,
            available,
            tokens >= budget.available * config.summary_trigger_ratio,
        ):
            if len(seen) >= MAX_PREVIEW_SOURCES or time.monotonic() >= deadline:
                break
            reference = handle(scope, source)
            if reference in seen or len(text.encode()) > MAX_SOURCE_BYTES:
                continue
            seen.add(reference)
            if resolve(scope, source) != text:
                continue
            result = await owner.prepare_source(
                identity(scope), reference, text, deadline=deadline
            )
            if resolve(scope, source) != text:
                scope.index_preparation_status = "source_expired"
                return
            scope.index_preparation_results.append(result)
            if result.get("reason") == "no_embedding":
                scope.index_preparation_status = "no_embedding"
                return
        if scope.index_preparation_results:
            scope.index_preparation_status = (
                "complete"
                if all(r["complete"] for r in scope.index_preparation_results)
                else "partial"
            )

    try:
        await asyncio.wait_for(prepare(), timeout=duration)
    except asyncio.TimeoutError:
        scope.index_preparation_status = "timeout"
    except Exception:
        # Never expose provider bodies, credentials, source text or raw errors.
        scope.index_preparation_status = "fallback"
    finally:
        scope.index_preparation_remaining = max(
            0.0, scope.index_preparation_remaining - (time.monotonic() - started)
        )
    if ledger:
        ledger.remaining()
