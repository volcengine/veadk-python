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

"""Event-driven Managed Agents loop backed entirely by the Anthropic SDK."""

from __future__ import annotations

import asyncio
from contextlib import aclosing
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict

from veadk.runtime.managed_agents.events import (
    iter_session_events,
    send_session_events,
    trace_event,
)
from google.adk.agents import RunConfig
from google.adk.agents.run_config import StreamingMode
from google.adk.events import Event
from google.genai import types
from veadk.integrations.mpa.session_client import SelfHostSandboxClient

from veadk.utils.adk_compat import get_event_function_calls

logger = logging.getLogger("veadk.managed_agent_loop")

_TERMINAL_EVENT_TYPES = {
    "session.status_idle",
    "session.status_terminated",
    "session.error",
}


@dataclass(slots=True)
class ManagedAgentEventState:
    """Incremental event state shared by handlers for one Managed Session."""

    completed_inputs: set[str] = field(default_factory=set)
    pending_inputs: list[str] = field(default_factory=list)
    reconciled_events: set[str] = field(default_factory=set)
    cursor_seq: int | None = None
    history_reconciled: bool = False
    ark_response_id: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


class ManagedAgentsLoop:
    """Consume one pending Managed Session turn and drive a VeADK Runner.

    A self-hosted sandbox is normally started for one WorkItem. Consequently
    ``run(max_turns=1)`` handles one uncompleted ``user.message``, emits the
    canonical Agent/Session events, and exits after ``session.status_idle``.
    A later user message creates another WorkItem and starts a fresh sandbox.
    """

    def __init__(
        self,
        *,
        runner: Any,
        session_client: SelfHostSandboxClient | None = None,
        session_id: str | None = None,
        user_id: str = "managed_agents_user",
        event_state: ManagedAgentEventState | None = None,
    ) -> None:
        resolved_session_id = session_id or getattr(session_client, "session_id", None)
        if not resolved_session_id:
            raise ValueError(
                "ANTHROPIC_SESSION_ID (or SANDBOX_SESSION_ID) is required for Agent Loop mode."
            )
        self.runner = runner
        self.session_client = session_client
        self.session_id = str(resolved_session_id)
        self.user_id = user_id
        self._event_state = event_state or ManagedAgentEventState()

    @property
    def _completed_inputs(self) -> set[str]:
        return self._event_state.completed_inputs

    @property
    def _event_cursor_seq(self) -> int | None:
        return self._event_state.cursor_seq

    @_event_cursor_seq.setter
    def _event_cursor_seq(self, value: int | None) -> None:
        self._event_state.cursor_seq = value

    @property
    def _history_reconciled(self) -> bool:
        return self._event_state.history_reconciled

    @_history_reconciled.setter
    def _history_reconciled(self, value: bool) -> None:
        self._event_state.history_reconciled = value

    async def run(
        self,
        *,
        max_turns: int | None = 1,
        stop_event: asyncio.Event | None = None,
    ) -> int:
        """Listen through SDK SSE, process pending user messages, and return turns run."""
        if self.session_client is None:
            raise ValueError(
                "run() requires session_client; use run_pending() with a scoped SDK client"
            )
        self._restore_completed_inputs(
            await asyncio.to_thread(self.session_client.list_events)
        )
        turns = 0
        backoff = 0.25
        stop_after_terminal = False

        async with self.session_client.create_async_client() as sdk:
            while stop_event is None or not stop_event.is_set():
                try:
                    stream = await sdk.beta.sessions.events.stream(self.session_id)
                    terminal_seen = False
                    async with stream:
                        async for event in stream:
                            trace_event("received", "sse", self.session_id, event)
                            event_type = str(getattr(event, "type", "") or "")
                            if event_type == "session.status_terminated":
                                return turns
                            if (
                                stop_after_terminal
                                and event_type in _TERMINAL_EVENT_TYPES
                            ):
                                terminal_seen = True
                                continue
                            if event_type != "user.message":
                                continue

                            event_id = str(getattr(event, "id", "") or "")
                            if event_id and event_id in self._completed_inputs:
                                continue

                            await self._run_turn(sdk, event)
                            if event_id:
                                self._completed_inputs.add(event_id)
                            turns += 1
                            if max_turns is not None and turns >= max_turns:
                                stop_after_terminal = True
                    if terminal_seen:
                        return turns
                    backoff = 0.25
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning(
                        "Managed Session event stream failed; reconnecting in %.2fs",
                        backoff,
                    )
                    if stop_event is not None:
                        try:
                            await asyncio.wait_for(stop_event.wait(), timeout=backoff)
                            return turns
                        except TimeoutError:
                            pass
                    else:
                        await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 5.0)
        return turns

    async def run_pending(self, sdk: Any, *, max_turns: int | None = 1) -> int:
        """Process persisted, incomplete user messages for one claimed work item.

        The first pass reconciles the complete durable ledger so a replacement
        worker can recover work that arrived before it started. Later passes
        use the last observed event sequence as a cursor and read only newer
        events. Handlers for the same Session serialize through their shared
        event state so concurrent WorkItems cannot advance the cursor past an
        unprocessed message.
        """
        async with self._event_state.lock:
            return await self._run_pending_locked(sdk, max_turns=max_turns)

    async def _run_pending_locked(self, sdk: Any, *, max_turns: int | None) -> int:
        previous_cursor = self._event_cursor_seq if self._history_reconciled else None
        events, full_reconciliation = await self._list_pending_events(sdk)
        # Another Pod may have completed inputs since our last cursor. A
        # process-local completed set is only a cache of the canonical ledger.
        self._restore_completed_inputs(events, incremental=not full_reconciliation)
        turns = 0
        consumed = 0
        for index, event in enumerate(events):
            consumed = index + 1
            if self._value(event, "type") != "user.message":
                continue
            event_id = str(self._value(event, "id") or "")
            if event_id and event_id in self._completed_inputs:
                continue
            await self._run_turn(sdk, event)
            if event_id:
                self._completed_inputs.add(event_id)
            turns += 1
            if max_turns is not None and turns >= max_turns:
                break
        self._history_reconciled = True
        self._advance_event_cursor(events[:consumed], previous=previous_cursor)
        return turns

    async def _list_pending_events(self, sdk: Any) -> tuple[list[Any], bool]:
        """Read a recovery snapshot once, then advance through new events."""
        cursor_seq = self._event_cursor_seq if self._history_reconciled else None
        incremental = cursor_seq is not None
        try:
            events = await self._list_events_after(sdk, cursor_seq)
            if incremental and any(
                (seq := self._event_seq(event)) is not None and seq <= cursor_seq
                for event in events
            ):
                raise RuntimeError("event server did not advance the requested cursor")
            full_reconciliation = cursor_seq is None
        except asyncio.CancelledError:
            raise
        except Exception:
            if not incremental:
                raise
            logger.warning(
                "Managed Session event cursor failed; reconciling full history once",
                exc_info=True,
            )
            full_history = await self._list_events_after(sdk, None)
            self._restore_completed_inputs(full_history)
            events = full_history
            full_reconciliation = False

        if incremental:
            # A server that ignores ``page`` must not make an already-consumed
            # user.message visible to the execution loop again. Missing seq is
            # retained so correctness falls back to the completed-input guard.
            events = [
                event
                for event in events
                if (seq := self._event_seq(event)) is None or seq > cursor_seq
            ]

        return events, full_reconciliation

    async def _list_events_after(self, sdk: Any, cursor_seq: int | None) -> list[Any]:
        options: dict[str, Any] = {"limit": 100, "order": "asc"}
        if cursor_seq is not None:
            # ma-infra ListEvents/next_page uses decimal sequence cursors.
            options["page"] = str(cursor_seq)
        return [
            event
            async for event in iter_session_events(sdk, self.session_id, **options)
        ]

    def _advance_event_cursor(self, events: list[Any], *, previous: int | None) -> None:
        if not events:
            if previous is None:
                self._event_cursor_seq = 0
            return
        sequences = [self._event_seq(event) for event in events]
        if any(sequence is None for sequence in sequences):
            # Custom/older servers may omit sequence metadata. Keep correctness
            # by using full reconciliation on the next pass instead of risking
            # a cursor that skips an event.
            self._event_cursor_seq = None
            logger.warning(
                "Managed Session events omitted sequence metadata; "
                "next poll will reconcile full history"
            )
            return
        self._event_cursor_seq = max(previous or 0, *(int(seq) for seq in sequences))

    async def run_claimed(
        self,
        sdk: Any,
        *,
        environment_id: str,
        work_id: str,
        last_heartbeat: str = "NO_HEARTBEAT",
        poll_interval: float = 1.0,
        heartbeat_interval: float | None = None,
    ) -> int:
        turns = 0
        stopped = asyncio.Event()
        if heartbeat_interval is None:
            heartbeat_interval = float(
                os.getenv("MANAGED_AGENT_HEARTBEAT_INTERVAL_SECONDS", "2")
            )
        if heartbeat_interval <= 0:
            raise ValueError("heartbeat_interval must be positive")

        async def heartbeat() -> None:
            nonlocal last_heartbeat
            while not stopped.is_set():
                response = await sdk.beta.environments.work.heartbeat(
                    work_id,
                    environment_id=environment_id,
                    expected_last_heartbeat=last_heartbeat,
                    desired_ttl_seconds=90,
                )
                if not response.lease_extended:
                    raise RuntimeError("Managed work lease is no longer active")
                last_heartbeat = response.last_heartbeat
                try:
                    await asyncio.wait_for(stopped.wait(), timeout=heartbeat_interval)
                except TimeoutError:
                    pass

        async def consume() -> None:
            nonlocal turns
            while True:
                session = await sdk.beta.sessions.retrieve(self.session_id)
                if self._value(session, "status") in {"terminated", "deleted"}:
                    return
                turns += await self.run_pending(sdk, max_turns=None)
                await asyncio.sleep(poll_interval)

        tasks = [asyncio.create_task(consume()), asyncio.create_task(heartbeat())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            stopped.set()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        return turns

    def _restore_completed_inputs(
        self, events: list[Any], *, incremental: bool = False
    ) -> None:
        """Reconcile completion on both full recovery and cross-Pod handoff."""
        if not incremental:
            self._event_state.pending_inputs.clear()
            self._event_state.reconciled_events.clear()
        pending = self._event_state.pending_inputs
        for event in events:
            event_id = str(self._value(event, "id") or "")
            sequence = self._event_seq(event)
            key = f"seq:{sequence}" if sequence is not None else event_id
            if key:
                if key in self._event_state.reconciled_events:
                    continue
                self._event_state.reconciled_events.add(key)
            event_type = str(self._value(event, "type") or "")
            if event_type == "span.model_request_end":
                metadata = self._value(event, "metadata") or {}
                response_id = self._value(metadata, "ark_response_id")
                if response_id and not self._value(event, "is_error"):
                    self._event_state.ark_response_id = str(response_id)
            if event_type == "user.message":
                if event_id:
                    pending.append(event_id)
            elif event_type in {"user.interrupt", "session.status_terminated"}:
                self._completed_inputs.update(pending)
                pending.clear()
            elif event_type in _TERMINAL_EVENT_TYPES and event_type != "session.error":
                if event_type == "session.status_idle":
                    reason = self._value(event, "stop_reason")
                    if self._value(reason, "type") not in {None, "end_turn"}:
                        continue
                # A terminal event closes one turn. More than one user message
                # may have accumulated while no worker was running, so marking
                # the entire pending list complete here would silently drop all
                # but the first queued turn.
                if pending:
                    self._completed_inputs.add(pending.pop(0))

    async def _run_turn(self, sdk: Any, user_event: Any) -> None:
        span_id = ""
        usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }

        try:
            prompt = self._message_text(self._value(user_event, "content"))
            await self._ensure_local_session()
            started = await send_session_events(
                sdk,
                self.session_id,
                events=[
                    {"type": "session.status_running"},
                    {"type": "span.model_request_start"},
                ],
            )
            for event in getattr(started, "data", None) or []:
                if getattr(event, "type", None) == "span.model_request_start":
                    span_id = str(getattr(event, "id", "") or "")
                    break
            if not span_id:
                raise RuntimeError(
                    "events.send did not return the persisted span.model_request_start id"
                )

            message = types.Content(role="user", parts=[types.Part(text=prompt)])
            stream_ids: dict[str, str] = {}
            try:
                async with aclosing(
                    self.runner.run_async(
                        user_id=self.user_id,
                        session_id=self.session_id,
                        new_message=message,
                        run_config=RunConfig(streaming_mode=StreamingMode.SSE),
                    )
                ) as runner_events:
                    async for event in runner_events:
                        trace_event("received", "runner", self.session_id, event)
                        self._merge_usage(usage, getattr(event, "usage_metadata", None))
                        if not getattr(event, "partial", False):
                            response_id = getattr(event, "interaction_id", None)
                            if response_id:
                                self._event_state.ark_response_id = str(response_id)
                        await self._publish_runner_event(
                            sdk, event, stream_ids=stream_ids
                        )
            except (Exception, asyncio.CancelledError):
                try:
                    await asyncio.shield(
                        self._close_transient_streams(sdk, stream_ids, status="aborted")
                    )
                except Exception as cleanup_error:
                    logger.warning(
                        "Managed stream cleanup failed: %s",
                        type(cleanup_error).__name__,
                    )
                raise
            await self._close_transient_streams(sdk, stream_ids, status="completed")

            await send_session_events(
                sdk,
                self.session_id,
                events=[
                    {
                        "type": "span.model_request_end",
                        "model_request_start_id": span_id,
                        "model_usage": usage,
                        **(
                            {
                                "metadata": {
                                    "ark_response_id": self._event_state.ark_response_id
                                }
                            }
                            if self._event_state.ark_response_id
                            else {}
                        ),
                    },
                    {
                        "type": "session.status_idle",
                        "stop_reason": {"type": "end_turn"},
                    },
                ],
            )
        except asyncio.CancelledError:
            events: list[dict[str, Any]] = []
            if span_id:
                events.append(
                    {
                        "type": "span.model_request_end",
                        "model_request_start_id": span_id,
                        "model_usage": usage,
                        "is_error": True,
                    }
                )
            if events:
                try:
                    await asyncio.shield(
                        send_session_events(sdk, self.session_id, events=events)
                    )
                except Exception as cleanup_error:
                    logger.warning(
                        "Managed cancellation event failed: %s",
                        type(cleanup_error).__name__,
                    )
            raise
        except Exception as error:
            logger.error("Managed Agents turn failed: %s", type(error).__name__)
            events: list[dict[str, Any]] = []
            if span_id:
                events.append(
                    {
                        "type": "span.model_request_end",
                        "model_request_start_id": span_id,
                        "model_usage": usage,
                        "is_error": True,
                    }
                )
            events.append(
                {"type": "session.error", "error": "Managed Agents turn failed"}
            )

            try:
                await send_session_events(sdk, self.session_id, events=events)
            except Exception as reporting_error:
                logger.warning(
                    "Managed failure event failed: %s", type(reporting_error).__name__
                )
            raise

    async def _ensure_local_session(self) -> None:
        service = self.runner.session_service
        session = await service.get_session(
            app_name=self.runner.app_name,
            user_id=self.user_id,
            session_id=self.session_id,
        )
        if session is None:
            session = await service.create_session(
                app_name=self.runner.app_name,
                user_id=self.user_id,
                session_id=self.session_id,
            )
            # A new Work may run in another process. Only the opaque response
            # reference is restored; conversation inputs/outputs stay in Ark.
            if self._event_state.ark_response_id:
                await service.append_event(
                    session,
                    Event(
                        author=self.runner.agent.name,
                        interaction_id=self._event_state.ark_response_id,
                    ),
                )

    async def _publish_runner_event(
        self, sdk: Any, event: Any, *, stream_ids: dict[str, str]
    ) -> None:
        partial = bool(getattr(event, "partial", False))
        content = getattr(event, "content", None)
        if partial:
            for part in getattr(content, "parts", None) or []:
                text = str(getattr(part, "text", "") or "")
                if not text:
                    continue
                kind = (
                    "thinking" if bool(getattr(part, "thought", False)) else "message"
                )
                stream_id = stream_ids.get(kind)
                if stream_id is None:
                    stream_id = f"sevt-{uuid.uuid4().hex}"
                    stream_ids[kind] = stream_id
                    await self._publish_transient(
                        sdk,
                        {
                            "type": f"agent.{kind}_stream_start",
                            f"{kind}_id": stream_id,
                        },
                    )
                await self._publish_transient(
                    sdk,
                    {
                        "type": f"agent.{kind}_chunk",
                        f"{kind}_id": stream_id,
                        "delta": text,
                    },
                )
            return

        # Remote tools publish agent.tool_use before execution and the client
        # canonicalizes user.tool_result into agent.tool_result. Do not duplicate
        # those events when ADK later exposes its function-call bookkeeping.
        if get_event_function_calls(event):
            return

        output_events: list[dict[str, Any]] = []
        for part in getattr(content, "parts", None) or []:
            text = str(getattr(part, "text", "") or "")
            if not text:
                continue
            if bool(getattr(part, "thought", False)):
                thinking_id = stream_ids.pop("thinking", None)
                if thinking_id is not None:
                    await self._publish_transient(
                        sdk,
                        {
                            "type": "agent.thinking_stream_end",
                            "thinking_id": thinking_id,
                            "status": "completed",
                        },
                    )
                else:
                    thinking_id = f"sevt-{uuid.uuid4().hex}"
                output_events.append(
                    {
                        "type": "agent.thinking",
                        "thinking_id": thinking_id,
                        "text": text,
                    }
                )
            else:
                message_id = stream_ids.pop("message", None)
                if message_id is not None:
                    await self._publish_transient(
                        sdk,
                        {
                            "type": "agent.message_stream_end",
                            "message_id": message_id,
                            "status": "completed",
                        },
                    )
                else:
                    message_id = f"sevt-{uuid.uuid4().hex}"
                output_events.append(
                    {
                        "type": "agent.message",
                        "message_id": message_id,
                        "content": [{"type": "text", "text": text}],
                    }
                )
        if output_events:
            await send_session_events(sdk, self.session_id, events=output_events)

    async def _publish_transient(self, sdk: Any, event: dict[str, Any]) -> None:
        # Previews use the existing events.send route and SSE event delta wire
        # format. The canonical event closes the preview; stream-end markers
        # are local bookkeeping and need no extra event or endpoint.
        typ = event["type"]
        if typ.endswith("_stream_end") or typ == "agent.thinking_chunk":
            return
        thinking = typ.startswith("agent.thinking")
        stream_id = event["thinking_id" if thinking else "message_id"]
        if typ.endswith("_stream_start"):
            event = {
                "type": "event_start",
                "event": {
                    "type": "agent.thinking" if thinking else "agent.message",
                    "id": stream_id,
                },
            }
        else:
            event = {
                "type": "event_delta",
                "event_id": stream_id,
                "delta": {
                    "type": "content_delta",
                    "index": 0,
                    "content": {
                        "type": "text",
                        "text": event["delta"],
                    },
                },
            }
        event = {
            "id": f"transient-{uuid.uuid4().hex}",
            "processed_at": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        try:
            trace_event("sent", "transient", self.session_id, event)
            await sdk.post(
                f"/v1/sessions/{self.session_id}/events",
                cast_to=Dict[str, Any],
                body={"events": [event]},
            )
        except Exception as error:
            logger.warning(
                "Managed Agents transient stream publish failed type=%s error_type=%s",
                event.get("type"),
                type(error).__name__,
            )
            raise

    async def _close_transient_streams(
        self, sdk: Any, stream_ids: dict[str, str], *, status: str
    ) -> None:
        for kind, stream_id in list(stream_ids.items()):
            await self._publish_transient(
                sdk,
                {
                    "type": f"agent.{kind}_stream_end",
                    f"{kind}_id": stream_id,
                    "status": status,
                },
            )
            stream_ids.pop(kind, None)

    @staticmethod
    def _value(value: Any, name: str) -> Any:
        return (
            value.get(name) if isinstance(value, dict) else getattr(value, name, None)
        )

    @classmethod
    def _event_seq(cls, event: Any) -> int | None:
        value = cls._value(event, "seq")
        if value is None:
            value = cls._value(event, "_seq")
        try:
            sequence = int(value)
        except (TypeError, ValueError):
            return None
        return sequence if sequence >= 0 else None

    @staticmethod
    def _message_text(content: Any) -> str:
        blocks = content if isinstance(content, list) else list(content or [])
        parts: list[str] = []
        for block in blocks:
            block_type = (
                block.get("type")
                if isinstance(block, dict)
                else getattr(block, "type", None)
            )
            if block_type != "text":
                continue
            text = (
                block.get("text")
                if isinstance(block, dict)
                else getattr(block, "text", None)
            )
            if text:
                parts.append(str(text))
        if not parts:
            raise ValueError("user.message must contain at least one text block")
        return "\n".join(parts)

    @staticmethod
    def _merge_usage(target: dict[str, int], usage: Any) -> None:
        if usage is None:
            return
        target["input_tokens"] += int(getattr(usage, "prompt_token_count", 0) or 0)
        target["output_tokens"] += int(getattr(usage, "candidates_token_count", 0) or 0)
        target["cache_read_input_tokens"] += int(
            getattr(usage, "cached_content_token_count", 0) or 0
        )
