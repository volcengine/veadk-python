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

"""Tool wrappers that record Harness capability receipts."""

from __future__ import annotations

import functools
import inspect
import json
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import ParamSpec, Protocol, TypeVar, overload

from .core import (
    CapabilityReceipt,
    EvidenceRef,
    JSONDict,
    current_harness_context,
    summarize_text,
)


P = ParamSpec("P")
R = TypeVar("R")


class ReceiptStoreProtocol(Protocol):
    def put_evidence(
        self,
        *,
        kind: str,
        text: str,
        metadata: JSONDict | None = None,
        ref_id: str | None = None,
    ) -> EvidenceRef: ...

    def append_receipt(self, receipt: CapabilityReceipt) -> None: ...


def wrap_tools(
    tools: list[Callable[..., object]],
    *,
    store: ReceiptStoreProtocol,
    externalize_threshold: int = 4000,
) -> list[Callable[..., object]]:
    """Wrap multiple veADK tools without changing their public signatures."""

    return [
        wrap_tool(tool, store=store, externalize_threshold=externalize_threshold)
        for tool in tools
    ]


@overload
def wrap_tool(
    tool: Callable[P, Awaitable[R]],
    *,
    store: ReceiptStoreProtocol,
    externalize_threshold: int = 4000,
) -> Callable[P, Awaitable[R]]: ...


@overload
def wrap_tool(
    tool: Callable[P, R],
    *,
    store: ReceiptStoreProtocol,
    externalize_threshold: int = 4000,
) -> Callable[P, R]: ...


def wrap_tool(
    tool: Callable[P, R] | Callable[P, Awaitable[R]],
    *,
    store: ReceiptStoreProtocol,
    externalize_threshold: int = 4000,
) -> Callable[P, R] | Callable[P, Awaitable[R]]:
    """Return a receipt-recording wrapper for a sync or async callable."""

    if inspect.iscoroutinefunction(tool):

        @functools.wraps(tool)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            started = time.perf_counter()
            try:
                result = await tool(*args, **kwargs)
            except Exception as exc:
                _record_receipt(
                    tool=tool,
                    args=args,
                    kwargs=kwargs,
                    result=None,
                    status="failed",
                    duration_ms=(time.perf_counter() - started) * 1000,
                    error=exc,
                    store=store,
                    externalize_threshold=externalize_threshold,
                )
                raise

            _record_receipt(
                tool=tool,
                args=args,
                kwargs=kwargs,
                result=result,
                status="success",
                duration_ms=(time.perf_counter() - started) * 1000,
                error=None,
                store=store,
                externalize_threshold=externalize_threshold,
            )
            return result

        return async_wrapper

    @functools.wraps(tool)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        started = time.perf_counter()
        try:
            result = tool(*args, **kwargs)
        except Exception as exc:
            _record_receipt(
                tool=tool,
                args=args,
                kwargs=kwargs,
                result=None,
                status="failed",
                duration_ms=(time.perf_counter() - started) * 1000,
                error=exc,
                store=store,
                externalize_threshold=externalize_threshold,
            )
            raise

        _record_receipt(
            tool=tool,
            args=args,
            kwargs=kwargs,
            result=result,
            status="success",
            duration_ms=(time.perf_counter() - started) * 1000,
            error=None,
            store=store,
            externalize_threshold=externalize_threshold,
        )
        return result

    return sync_wrapper


def _record_receipt(
    *,
    tool: Callable[..., object],
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
    result: object,
    status: str,
    duration_ms: float,
    error: Exception | None,
    store: ReceiptStoreProtocol,
    externalize_threshold: int,
) -> CapabilityReceipt:
    context = current_harness_context()
    result_text = _result_to_text(result) if error is None else ""
    evidence_refs = []
    result_summary = summarize_text(result_text, max_chars=900)

    if error is None and len(result_text) > externalize_threshold:
        evidence_refs.append(
            store.put_evidence(
                kind="tool-result",
                text=result_text,
                metadata={
                    "tool_name": getattr(tool, "__name__", tool.__class__.__name__)
                },
            )
        )
        result_summary = summarize_text(result_text, max_chars=500)

    receipt = CapabilityReceipt(
        id=f"receipt-{uuid.uuid4().hex[:12]}",
        run_id=context.run_id if context else "manual-run",
        session_id=context.session_id if context else "manual-session",
        tool_name=getattr(tool, "__name__", tool.__class__.__name__),
        input_summary=_summarize_call(args=args, kwargs=kwargs),
        result_summary=result_summary,
        status=status,
        duration_ms=round(duration_ms, 3),
        evidence_refs=evidence_refs,
        sources=_extract_sources(result),
        artifacts=_extract_artifacts(result),
        error_type=type(error).__name__ if error else None,
        error_message=str(error) if error else None,
    )
    store.append_receipt(receipt)
    return receipt


def _summarize_call(*, args: tuple[object, ...], kwargs: Mapping[str, object]) -> str:
    payload: dict[str, object] = {}
    if args:
        payload["args"] = args
    if kwargs:
        payload["kwargs"] = kwargs
    return summarize_text(_json_dumps(payload), max_chars=500)


def _result_to_text(result: object) -> str:
    if isinstance(result, (dict, list, tuple)):
        return _json_dumps(result)
    return "" if result is None else str(result)


def _json_dumps(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def _extract_sources(result: object) -> list[JSONDict]:
    if not isinstance(result, Mapping):
        return []

    sources: list[JSONDict] = []
    for key in ("sources", "citations"):
        raw_sources = result.get(key)
        if raw_sources is None:
            continue
        if not isinstance(raw_sources, list):
            raw_sources = [raw_sources]
        for item in raw_sources:
            sources.append(_normalize_source(item))

    for key in ("url", "source_url", "link"):
        if result.get(key):
            sources.append({"url": str(result[key]), "source_key": key})

    return [source for source in sources if source]


def _normalize_source(item: object) -> JSONDict:
    if isinstance(item, Mapping):
        return dict(item)
    text = str(item)
    if text.startswith(("http://", "https://")):
        return {"url": text}
    return {"text": text}


def _extract_artifacts(result: object) -> list[JSONDict]:
    if not isinstance(result, Mapping):
        return []

    artifacts: list[JSONDict] = []
    raw_artifacts = result.get("artifacts")
    if raw_artifacts:
        if not isinstance(raw_artifacts, list):
            raw_artifacts = [raw_artifacts]
        for item in raw_artifacts:
            if isinstance(item, Mapping):
                artifacts.append(dict(item))
            else:
                artifacts.append({"value": str(item)})

    for key in ("artifact_id", "file_path", "path"):
        if result.get(key):
            artifacts.append({key: str(result[key])})
    return artifacts
