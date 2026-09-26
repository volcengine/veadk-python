"""Optional async evidence selection; Session originals authorize every use."""

from __future__ import annotations

import asyncio
import inspect
import time
from contextlib import contextmanager

from .evidence import current_question, evidence_preview, repeated_projection
from .context_windows import context_window
from .references import digest, handle, identity, resolve
from .runtime import context_retriever

MAX_PREVIEW_SOURCES = 8
MAX_SOURCE_BYTES = 2_000_000
RETRIEVAL_TIMEOUT = 5.0


@contextmanager
def use_context_retriever(retriever):
    """Bind a trusted async ranker to new invocations in this execution context.

    The ranker implements rank(identity, reference, original_text, query) and
    returns at most 100 Unicode (start, end) pairs. A ranker may also expose
    rank_with_deadline(..., deadline=monotonic_seconds), so optional I/O leaves
    time for local fallback. It never supplies answer text. Do not put clients
    or credentials in serialized Agent configuration.
    """
    token = context_retriever.set(retriever)
    try:
        yield
    finally:
        context_retriever.reset(token)


def _key(scope, source, query):
    return digest([identity(scope), source["text_hash"], query])


def begin_retrieval(scope):
    scope.evidence_rankings.clear()
    scope.evidence_retrieval_deadline = time.monotonic() + RETRIEVAL_TIMEOUT


async def _rank(scope, source, text, query):
    if scope.evidence_retriever is None:
        return None
    if len(text.encode()) > MAX_SOURCE_BYTES or len(query.encode()) > 8192:
        scope.evidence_retrieval_status = "input_limit"
        return None
    if resolve(scope, source) != text:
        scope.evidence_retrieval_status = "source_expired"
        return None
    timeout = RETRIEVAL_TIMEOUT
    if scope.evidence_retrieval_deadline is not None:
        timeout = min(timeout, scope.evidence_retrieval_deadline - time.monotonic())
    if timeout <= 0:
        scope.evidence_retrieval_status = "timeout"
        return None
    try:
        args = (identity(scope), handle(scope, source), text, query)
        bounded = getattr(scope.evidence_retriever, "rank_with_deadline", None)
        # Keep the outer/shared deadline unchanged. The ranker's own deadline
        # leaves time for cancellation cleanup, lexical fallback and validation.
        call = (
            bounded(*args, deadline=time.monotonic() + timeout * 0.8)
            if callable(bounded)
            else scope.evidence_retriever.rank(*args)
        )
        if not inspect.isawaitable(call):
            raise TypeError("context_retriever_must_be_async")
        spans = await asyncio.wait_for(
            call,
            timeout=timeout,
        )
        if not isinstance(spans, (list, tuple)) or len(spans) > 100:
            raise ValueError("invalid_ranges")
        checked = []
        for span in spans:
            if (
                not isinstance(span, (list, tuple))
                or len(span) != 2
                or any(type(position) is not int for position in span)
                or not 0 <= span[0] < span[1] <= len(text)
            ):
                raise ValueError("invalid_range")
            if tuple(span) not in checked:
                checked.append(tuple(span))
        # In particular, never use index contents after Session deletion/change.
        if resolve(scope, source) != text:
            scope.evidence_retrieval_status = "source_expired"
            return None
        scope.evidence_retrieval_status = "selected" if checked else "empty"
        return checked or None
    except Exception:
        # Optional ranker failures cannot expose provider response/credentials.
        # asyncio cancellation remains outside Exception and is not swallowed.
        scope.evidence_retrieval_status = "fallback"
        return None


async def prepare_previews(request, scope, config):
    if scope is None:
        return
    scope.evidence_rankings.clear()
    if scope.evidence_retriever is None:
        return
    from .tool_results import _compression_candidates

    query = current_question(request.contents)
    if not query:
        return

    async def prepare():
        considered = 0
        for _, _, text, source, _, _, _ in _compression_candidates(
            request, scope, config
        ):
            if considered >= MAX_PREVIEW_SOURCES:
                break
            if config.tool_result_max_bytes >= 16000 and repeated_projection(text):
                continue
            key = _key(scope, source, query)
            if key in scope.evidence_rankings:
                continue
            considered += 1
            spans = await _rank(scope, source, text, query)
            if spans:
                scope.evidence_rankings[key] = spans

    try:
        # A whole request has one deadline, rather than N sequential deadlines.
        await asyncio.wait_for(prepare(), timeout=RETRIEVAL_TIMEOUT)
    except asyncio.TimeoutError:
        scope.evidence_retrieval_status = "timeout"


def _matches(text, ranked, maximum, *, preview):
    selected = []
    for start, end in ranked:
        # Keep a bounded amount of the same original paragraph around a hit.
        # If it cannot fit, the verified ranked span remains eligible as-is.
        expanded = context_window(text, start, end)
        choices = [expanded] if expanded == (start, end) else [expanded, (start, end)]
        for span in choices:
            trial = []
            for a, b in sorted([*selected, span]):
                if trial and a <= trial[-1][1]:
                    trial[-1] = (trial[-1][0], max(b, trial[-1][1]))
                else:
                    trial.append((a, b))
            matches = [{"offset": a, "end": b, "text": text[a:b]} for a, b in trial]
            size = (
                len(_preview(matches).encode())
                if preview
                else sum(len(match["text"].encode()) for match in matches)
            )
            if size <= maximum:
                selected = trial
                break
    return [{"offset": a, "end": b, "text": text[a:b]} for a, b in selected]


def _preview(matches):
    return "[Selected verbatim source excerpts; gaps are omitted.]\n" + "".join(
        f"\n[Original characters {match['offset']}:{match['end']}]\n{match['text']}"
        for match in matches
    )


def prepared_preview(scope, source, text, query, maximum):
    ranked = scope.evidence_rankings.get(_key(scope, source, query)) if scope else None
    if ranked and resolve(scope, source) == text:
        matches = _matches(text, ranked, maximum, preview=True)
        if matches:
            return _preview(matches)
    return evidence_preview(text, query, maximum)


async def search_original(scope, source, text, query, maximum):
    ranked = await _rank(scope, source, text, query)
    matches = _matches(text, ranked, maximum, preview=False) if ranked else []
    if not matches:
        return None
    return {
        "found": True,
        "matches": matches,
        "complete": False,
        "total_characters": len(text),
    }
