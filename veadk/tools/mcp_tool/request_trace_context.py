"""Extract per-call W3C context without forwarding authentication or baggage."""

from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


def request_trace_context() -> dict[str, str] | None:
    carrier: dict[str, str] = {}
    try:
        # Use only W3C trace context; the global propagator can include baggage.
        TraceContextTextMapPropagator().inject(carrier)
    except Exception:
        # Observability extraction cannot fail or retry the actual tool call.
        return None
    if "traceparent" not in carrier:
        return None
    return {
        key: carrier[key] for key in ("traceparent", "tracestate") if key in carrier
    }
