"""Allowlisted transport accounting for the isolated live HTTP test server."""

import json
import time
import uuid
from contextvars import ContextVar

import httpx

REQUEST_SCOPE = ContextVar("routing_experiment_request", default={})


class UsageStream(httpx.AsyncByteStream):
    def __init__(self, inner, finish, streaming, decoder):
        self.inner, self.finish, self.streaming = inner, finish, streaming
        self.decoder = decoder
        self.buffer = b""
        self.usage = None
        self.closed = False

    def consume(self, data):
        try:
            item = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            return
        body = item.get("response", item)
        if isinstance(body, dict) and isinstance(body.get("usage"), dict):
            self.usage = body["usage"]

    async def __aiter__(self):
        try:
            async for chunk in self.inner:
                self.buffer += self.decoder.decode(chunk)
                if self.streaming:
                    while b"\n" in self.buffer:
                        line, self.buffer = self.buffer.split(b"\n", 1)
                        if line.startswith(b"data: "):
                            self.consume(line[6:])
                yield chunk
            self.buffer += self.decoder.flush()
            if not self.streaming:
                self.consume(self.buffer)
            elif self.buffer.startswith(b"data: "):
                self.consume(self.buffer[6:])
        finally:
            self.flush()

    def flush(self):
        if not self.closed:
            self.closed = True
            self.finish(self.usage)
            self.buffer = b""

    async def aclose(self):
        try:
            await self.inner.aclose()
        finally:
            self.flush()


def install_usage_audit(audit):
    """Record every transport attempt, including SDK retries and failed calls."""
    original = httpx.AsyncClient.send

    async def send(client, request, **kwargs):
        path = request.url.path
        if not any(
            path.endswith(p) for p in ("/systemone", "/responses", "/chat/completions")
        ):
            return await original(client, request, **kwargs)
        payload = json.loads(request.content)
        record = {
            **REQUEST_SCOPE.get(),
            "attempt_id": uuid.uuid4().hex,
            "endpoint": path,
            "model": payload.get("model"),
        }
        audit(kind="transport_start", **record)
        started = time.monotonic()
        try:
            # Consume through our stream even for non-streaming callers so the
            # response body is observed before response parsing can fail.
            stream = kwargs.pop("stream", False)
            response = await original(client, request, stream=True, **kwargs)
        except BaseException as exc:
            audit(
                kind="transport_end",
                **record,
                error=type(exc).__name__,
                usage=None,
                completed_at=time.time(),
            )
            raise

        def finish(usage):
            audit(
                kind="transport_end",
                **record,
                status=response.status_code,
                usage=usage,
                completed_at=time.time(),
                elapsed_ms=round((time.monotonic() - started) * 1000, 2),
            )

        response.stream = UsageStream(
            response.stream,
            finish,
            "text/event-stream" in response.headers.get("content-type", ""),
            httpx.Response(200, headers=response.headers)._get_content_decoder(),
        )
        if not stream:
            await response.aread()
        return response

    httpx.AsyncClient.send = send
