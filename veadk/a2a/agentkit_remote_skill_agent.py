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

"""A Session-aware A2A agent for ephemeral AgentKit Skill sandboxes."""

from __future__ import annotations

import asyncio
import time
from types import MethodType
from typing import AsyncGenerator, Literal, Optional

import requests
from a2a.types import (
    AgentCard,
    MessageSendConfiguration,
    MessageSendParams,
    Task,
    TaskQueryParams,
    TaskState,
)
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.utils.context_utils import Aclosing
from pydantic import PrivateAttr

from veadk.a2a.remote_ve_agent import RemoteVeAgent, _url_with_path
from veadk.tools.builtin_tools._agentkit import (
    AgentKitSessionLease,
    ensure_agentkit_session_lease,
    resolve_agentkit_tool_id,
)
from veadk.utils.auth import build_auth_config
from veadk.utils.logger import get_logger


logger = get_logger(__name__)

_AGENTKIT_SESSION_ID_METADATA_KEY = "veadk:agentkit_session_id"
_INBOUND_AUTH_HEADER = "inbound_auth"
_A2A_HISTORY_LENGTH = 20
_A2A_POLLING_STATES = frozenset({TaskState.submitted, TaskState.working})
_AGENT_CARD_PATH = "/.well-known/agent-card.json"
_AGENT_CARD_RETRY_STATUS_CODES = frozenset({502, 503, 504})
_AGENT_CARD_REQUEST_TIMEOUT = 10.0
_monotonic = time.monotonic


def _credential_token_value(credential: object | None) -> str | None:
    if credential is None:
        return None
    api_key = getattr(credential, "api_key", None)
    if api_key:
        return str(api_key)
    http = getattr(credential, "http", None)
    http_credentials = getattr(http, "credentials", None) if http else None
    http_token = getattr(http_credentials, "token", None) if http_credentials else None
    if http_token:
        return str(http_token)
    oauth2 = getattr(credential, "oauth2", None)
    access_token = getattr(oauth2, "access_token", None) if oauth2 else None
    return str(access_token) if access_token else None


async def _inbound_auth_token(ctx: InvocationContext) -> str | None:
    if not ctx.credential_service:
        return None
    auth_config = build_auth_config(
        credential_key="inbound_auth",
        auth_method="header",
        header_scheme="bearer",
    )
    credential = await ctx.credential_service.load_credential(
        auth_config=auth_config,
        callback_context=CallbackContext(ctx),
    )
    return _credential_token_value(credential)


def _agentkit_request_metadata(ctx: InvocationContext, _message) -> dict[str, str]:
    return {
        "user_id": ctx.user_id,
        "session_id": ctx.session.id,
    }


class _SessionBoundRemoteSkillAgent(RemoteVeAgent):
    """RemoteVeAgent that only resumes A2A context from its physical Session."""

    _bound_agentkit_session_id: str = PrivateAttr()
    _poll_interval: float = PrivateAttr()
    _max_poll_interval: float = PrivateAttr()
    _polling_configured: bool = PrivateAttr(default=False)

    def __init__(
        self,
        *,
        agentkit_session_id: str,
        poll_interval: float,
        max_poll_interval: float,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._a2a_request_meta_provider = _agentkit_request_metadata
        self._bound_agentkit_session_id = agentkit_session_id
        self._poll_interval = poll_interval
        self._max_poll_interval = max_poll_interval

    def _is_remote_response(self, event: Event) -> bool:
        if not super()._is_remote_response(event):
            return False
        metadata = event.custom_metadata or {}
        return (
            metadata.get(_AGENTKIT_SESSION_ID_METADATA_KEY)
            == self._bound_agentkit_session_id
        )

    async def _pre_run(self, ctx: InvocationContext) -> None:
        await super()._pre_run(ctx)
        self._configure_polling_client()

    def _configure_polling_client(self) -> None:
        """Adapt ADK's A2A client to Skill Sandbox non-blocking task execution."""
        if self._polling_configured:
            return
        client = self._a2a_client
        client._config.polling = True
        request_timeout = float(self._timeout)
        poll_interval = self._poll_interval
        max_poll_interval = self._max_poll_interval

        async def send_message_with_polling(
            _client,
            request,
            *,
            context=None,
            request_metadata=None,
        ):
            deadline = asyncio.get_running_loop().time() + request_timeout
            configuration = MessageSendConfiguration(
                accepted_output_modes=client._config.accepted_output_modes,
                blocking=False,
                push_notification_config=(
                    client._config.push_notification_configs[0]
                    if client._config.push_notification_configs
                    else None
                ),
            )
            params = MessageSendParams(
                message=request,
                configuration=configuration,
                metadata=request_metadata,
            )
            response = await client._transport.send_message(
                params,
                context=context,
            )
            result = (response, None) if isinstance(response, Task) else response
            await client.consume(result, client._card)
            if not isinstance(response, Task) or (
                response.status.state not in _A2A_POLLING_STATES
            ):
                yield result
                return

            current_task = response
            current_interval = poll_interval
            while current_task.status.state in _A2A_POLLING_STATES:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError(
                        f"Timed out while waiting for A2A task {response.id}"
                    )
                await asyncio.sleep(min(current_interval, remaining))
                current_task = await client.get_task(
                    TaskQueryParams(
                        id=response.id,
                        historyLength=_A2A_HISTORY_LENGTH,
                    ),
                    context=context,
                )
                current_interval = min(
                    current_interval * 2,
                    max_poll_interval,
                )
            await client.consume((current_task, None), client._card)
            yield current_task, None

        client.send_message = MethodType(send_message_with_polling, client)
        self._polling_configured = True


class AgentkitRemoteSkillAgent(BaseAgent):
    """Connect to an A2A agent hosted by an expiring AgentKit Session.

    ``tool_user_session_id`` is a stable logical key. The corresponding physical
    AgentKit Session, endpoint, Agent Card, and A2A client are resolved lazily and
    replaced when the Session no longer has enough remaining lifetime.
    """

    tool_id: Optional[str] = None
    tool_user_session_id: Optional[str] = None
    ttl: int = 1800
    request_timeout: int = 1800
    expiry_buffer: int = 60
    ready_timeout: float = 120
    a2a_ready_timeout: float = 120
    a2a_ready_poll_interval: float = 2
    poll_interval: float = 2
    max_poll_interval: float = 16
    prefer_internal_endpoint: bool = False
    rpc_path: str = "/a2a"
    auth_method: Literal["header", "querystring"] | None = "header"

    _delegates: dict[str, _SessionBoundRemoteSkillAgent] = PrivateAttr(
        default_factory=dict
    )
    _leases: dict[str, AgentKitSessionLease] = PrivateAttr(default_factory=dict)
    _delegate_use_counts: dict[str, int] = PrivateAttr(default_factory=dict)
    _delegate_lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)

    def __init__(
        self,
        name: str,
        *,
        tool_id: Optional[str] = None,
        tool_user_session_id: Optional[str] = None,
        description: str = "",
        ttl: int = 1800,
        request_timeout: int = 1800,
        expiry_buffer: int = 60,
        ready_timeout: float = 120,
        a2a_ready_timeout: float = 120,
        a2a_ready_poll_interval: float = 2,
        poll_interval: float = 2,
        max_poll_interval: float = 16,
        prefer_internal_endpoint: bool = False,
        rpc_path: str = "/a2a",
        auth_method: Literal["header", "querystring"] | None = "header",
        **kwargs,
    ) -> None:
        super().__init__(name=name, description=description, **kwargs)
        if not 60 <= ttl <= 86400:
            raise ValueError("ttl must be between 60 and 86400 seconds")
        if request_timeout <= 0:
            raise ValueError("request_timeout must be greater than 0")
        if expiry_buffer < 0:
            raise ValueError("expiry_buffer must be greater than or equal to 0")
        if request_timeout + expiry_buffer >= 86400:
            raise ValueError(
                "request_timeout plus expiry_buffer must be less than 86400 seconds"
            )
        if ready_timeout < 0:
            raise ValueError("ready_timeout must be greater than or equal to 0")
        if a2a_ready_timeout <= 0:
            raise ValueError("a2a_ready_timeout must be greater than 0")
        if a2a_ready_poll_interval <= 0:
            raise ValueError("a2a_ready_poll_interval must be greater than 0")
        if poll_interval <= 0:
            raise ValueError("poll_interval must be greater than 0")
        if max_poll_interval < poll_interval:
            raise ValueError(
                "max_poll_interval must be greater than or equal to poll_interval"
            )
        if not rpc_path.strip():
            raise ValueError("rpc_path must not be empty")

        self.tool_id = tool_id
        self.tool_user_session_id = tool_user_session_id
        self.ttl = ttl
        self.request_timeout = request_timeout
        self.expiry_buffer = expiry_buffer
        self.ready_timeout = ready_timeout
        self.a2a_ready_timeout = a2a_ready_timeout
        self.a2a_ready_poll_interval = a2a_ready_poll_interval
        self.poll_interval = poll_interval
        self.max_poll_interval = max_poll_interval
        self.prefer_internal_endpoint = prefer_internal_endpoint
        self.rpc_path = rpc_path
        self.auth_method = auth_method

    def _logical_user_session_id(self, ctx: InvocationContext) -> str:
        if self.tool_user_session_id:
            return self.tool_user_session_id
        return f"{self.name}_{ctx.user_id}_{ctx.session.id}"

    async def _resolve_lease(self, ctx: InvocationContext) -> AgentKitSessionLease:
        tool_id = self.tool_id or resolve_agentkit_tool_id("AGENTKIT_TOOL_ID_SKILLS")
        session_state = getattr(ctx.session, "state", None)
        tool_state = dict(session_state) if isinstance(session_state, dict) else None
        return await asyncio.to_thread(
            ensure_agentkit_session_lease,
            tool_id=tool_id,
            tool_user_session_id=self._logical_user_session_id(ctx),
            tool_state=tool_state,
            ttl=self.ttl,
            min_remaining_seconds=self.request_timeout + self.expiry_buffer,
            wait_until_ready=True,
            ready_timeout=self.ready_timeout,
        )

    @staticmethod
    def _agent_card_response_summary(response: requests.Response) -> str:
        content_type = response.headers.get("Content-Type", "unknown").split(";", 1)[0]
        return (
            f"HTTP {response.status_code}, content-type={content_type}, "
            f"body-bytes={len(response.content)}"
        )

    async def _wait_for_agent_card(
        self,
        *,
        endpoint: str,
        headers: dict[str, str],
    ) -> None:
        """Wait until the Session data plane serves a valid A2A Agent Card."""
        url = _url_with_path(endpoint, _AGENT_CARD_PATH)
        deadline = _monotonic() + self.a2a_ready_timeout
        last_result = "no response"

        while True:
            remaining = deadline - _monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    "Timed out waiting for AgentKit A2A Agent Card; "
                    f"last result: {last_result}"
                )

            try:
                response = await asyncio.to_thread(
                    requests.get,
                    url,
                    headers=headers,
                    timeout=min(_AGENT_CARD_REQUEST_TIMEOUT, remaining),
                )
            except requests.RequestException as exc:
                last_result = f"request failed ({type(exc).__name__})"
            else:
                last_result = self._agent_card_response_summary(response)
                if response.status_code == 200:
                    try:
                        AgentCard.model_validate(response.json())
                    except ValueError:
                        last_result = f"{last_result}, invalid JSON"
                    else:
                        logger.debug("AgentKit A2A Agent Card is ready")
                        return
                elif response.status_code not in _AGENT_CARD_RETRY_STATUS_CODES:
                    raise RuntimeError(
                        f"AgentKit A2A Agent Card request failed: {last_result}"
                    )

            remaining = deadline - _monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    "Timed out waiting for AgentKit A2A Agent Card; "
                    f"last result: {last_result}"
                )
            await asyncio.sleep(min(self.a2a_ready_poll_interval, remaining))

    async def _delegate_for(
        self,
        lease: AgentKitSessionLease,
        ctx: InvocationContext,
    ) -> _SessionBoundRemoteSkillAgent:
        inbound_auth = await _inbound_auth_token(ctx)
        endpoint = lease.select_endpoint(
            prefer_internal_endpoint=self.prefer_internal_endpoint
        )
        if not endpoint:
            raise RuntimeError(f"AgentKit session {lease.session_id} has no endpoint")
        extra_headers = {_INBOUND_AUTH_HEADER: inbound_auth} if inbound_auth else {}

        async with self._delegate_lock:
            needs_agent_card = lease.session_id not in self._delegates
        if needs_agent_card:
            await self._wait_for_agent_card(
                endpoint=endpoint,
                headers=extra_headers,
            )

        stale_delegate: _SessionBoundRemoteSkillAgent | None = None
        async with self._delegate_lock:
            delegate = self._delegates.get(lease.session_id)
            if delegate is None:
                delegate = await asyncio.to_thread(
                    _SessionBoundRemoteSkillAgent,
                    agentkit_session_id=lease.session_id,
                    poll_interval=self.poll_interval,
                    max_poll_interval=self.max_poll_interval,
                    name=self.name,
                    url=endpoint,
                    rpc_url=_url_with_path(endpoint, self.rpc_path),
                    auth_method=self.auth_method,
                    extra_headers=extra_headers,
                    timeout=float(self.request_timeout),
                )
                self._delegates[lease.session_id] = delegate
                logger.info(
                    "Bound AgentKit A2A agent %s to Session %s",
                    self.name,
                    lease.session_id,
                )
            elif inbound_auth:
                delegate._httpx_client.headers[_INBOUND_AUTH_HEADER] = inbound_auth
            else:
                delegate._httpx_client.headers.pop(_INBOUND_AUTH_HEADER, None)

            previous_lease = self._leases.get(lease.logical_user_session_id)
            self._leases[lease.logical_user_session_id] = lease
            self._delegate_use_counts[lease.session_id] = (
                self._delegate_use_counts.get(lease.session_id, 0) + 1
            )
            if (
                previous_lease
                and previous_lease.session_id != lease.session_id
                and self._delegate_use_counts.get(previous_lease.session_id, 0) == 0
            ):
                stale_delegate = self._delegates.pop(previous_lease.session_id, None)

        if stale_delegate:
            await stale_delegate.cleanup()
        return delegate

    async def _release_delegate(self, session_id: str) -> None:
        stale_delegate: _SessionBoundRemoteSkillAgent | None = None
        async with self._delegate_lock:
            remaining = max(self._delegate_use_counts.get(session_id, 1) - 1, 0)
            if remaining:
                self._delegate_use_counts[session_id] = remaining
                return
            self._delegate_use_counts.pop(session_id, None)
            if all(lease.session_id != session_id for lease in self._leases.values()):
                stale_delegate = self._delegates.pop(session_id, None)

        if stale_delegate:
            await stale_delegate.cleanup()

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        try:
            lease = await self._resolve_lease(ctx)
            delegate = await self._delegate_for(lease, ctx)
        except Exception as exc:
            yield Event(
                author=self.name,
                error_message=f"Failed to initialize AgentKit A2A Session: {exc}",
                invocation_id=ctx.invocation_id,
                branch=ctx.branch,
            )
            return

        try:
            async with Aclosing(delegate._run_async_impl(ctx)) as agen:
                async for event in agen:
                    event.custom_metadata = event.custom_metadata or {}
                    event.custom_metadata[_AGENTKIT_SESSION_ID_METADATA_KEY] = (
                        lease.session_id
                    )
                    yield event
        finally:
            await self._release_delegate(lease.session_id)

    async def cleanup(self) -> None:
        """Close every A2A HTTP client created for physical Sessions."""
        delegates = list(self._delegates.values())
        self._delegates.clear()
        self._leases.clear()
        self._delegate_use_counts.clear()
        for delegate in delegates:
            await delegate.cleanup()
