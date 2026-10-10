"""Observe owned database persistence without changing caller-owned services."""

from contextlib import suppress

from google.adk.events import Event
from google.adk.sessions import DatabaseSessionService, Session
from opentelemetry import context, trace
from opentelemetry.trace import Status, StatusCode


class TracedDatabaseSessionService(DatabaseSessionService):
    async def append_event(self, session: Session, event: Event) -> Event:
        # ADK does not persist partial events; do not count them as database writes.
        if event.partial:
            return await super().append_event(session, event)
        span = None
        token = None
        try:
            span = trace.get_tracer("veadk.session").start_span(
                "veadk.session.append_event"
            )
            span.set_attribute("gen_ai.session.id", session.id)
            if event.invocation_id:
                span.set_attribute("gen_ai.invocation.id", event.invocation_id)
            token = context.attach(trace.set_span_in_context(span))
        except Exception:
            # Observability failure must not skip or repeat the storage operation.
            pass
        try:
            return await super().append_event(session, event)
        except BaseException as error:
            if span is not None:
                # Database exceptions may contain credentials or event bodies.
                with suppress(Exception):
                    span.set_attribute("error.type", type(error).__name__)
                    span.set_status(Status(StatusCode.ERROR))
            raise
        finally:
            if token is not None:
                with suppress(Exception):
                    context.detach(token)
            if span is not None:
                with suppress(Exception):
                    span.end()
