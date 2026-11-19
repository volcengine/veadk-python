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

"""Invocation-scoped model transport for the Codex runtime.

A host that must observe or rewrite every model request can supply a
``provider_factory`` on :class:`~veadk.runtime.codex.config.CodexRuntimeConfig`.
The runtime enters the factory once per invocation and points the Codex
subprocess at the endpoint it yields. The host owns that HTTP server; VeADK
only carries its address and per-invocation credential.

The factory is an async context manager:

.. code-block:: python

    @asynccontextmanager
    async def provider_factory(agent, context):
        # start a loopback Responses proxy
        yield CodexProviderEndpoint(
            "http://127.0.0.1:8123/v1",
            token,
            handles_extra_body=True,
            wrap_tool_executor=policy.wrap_tool_executor,
        )
        # stop the proxy, cancel in-flight requests

``handles_extra_body`` says the endpoint consumes the agent's
``model_extra_config`` body itself (for example to turn it into provider
fields), so the runtime must not divert the turn to its in-process shim.
``wrap_tool_executor`` lets the host wrap each ADK tool executor before the
MCP bridge publishes it to Codex; it is optional.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _validate_api_base(value: str) -> str:
    """Return ``value`` unchanged when it is a safe Responses base URL."""
    if not isinstance(value, str) or not value:
        raise ValueError("Codex provider endpoint requires an api_base")
    if any(ord(character) <= 32 or ord(character) == 127 for character in value):
        raise ValueError("Codex provider api_base contains control characters")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise ValueError("Codex provider api_base is not a valid URL") from error
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port == 0
    ):
        raise ValueError(
            "Codex provider api_base must be an unauthenticated http(s) URL "
            "without query or fragment"
        )
    if parsed.scheme == "http" and parsed.hostname not in _LOOPBACK_HOSTS:
        # The per-invocation bearer token travels in a header. Cleartext is
        # acceptable only across the loopback interface, never a network hop.
        raise ValueError("Codex provider api_base must use https unless it is loopback")
    return value


def _validate_api_key(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Codex provider endpoint requires an api_key")
    if any(character in value for character in ("\x00", "\r", "\n")):
        raise ValueError("Codex provider api_key contains control characters")
    return value


@dataclass(frozen=True)
class CodexProviderEndpoint:
    """The host's Responses endpoint for one Codex invocation.

    Attributes:
        api_base: Base URL the Codex subprocess calls. Codex appends
            ``/responses``. Loopback may use ``http``; anything else must use
            ``https``.
        api_key: Per-invocation bearer token. Kept out of ``repr`` so a
            diagnostic log cannot leak it.
        handles_extra_body: Whether the endpoint consumes the agent's
            ``model_extra_config`` body itself. When true, the runtime keeps
            the direct transport instead of using its shim.
        wrap_tool_executor: Optional ``(name, executor) -> executor`` hook the
            runtime applies to every ADK tool executor before the MCP bridge
            publishes it. The wrapper must accept ``(arguments, call_id)`` and
            return the tool's string result.
    """

    api_base: str
    api_key: str = field(repr=False)
    handles_extra_body: bool = False
    wrap_tool_executor: Callable[[str, Any], Any] | None = field(
        default=None, repr=False
    )

    def __post_init__(self) -> None:
        """Reject endpoints the runtime cannot safely hand to Codex.

        Raises:
            ValueError: If ``api_base`` is not a safe http(s) URL, ``api_key``
                is not a usable token, ``handles_extra_body`` is not a
                boolean, or ``wrap_tool_executor`` is not callable.
        """
        _validate_api_base(self.api_base)
        _validate_api_key(self.api_key)
        if type(self.handles_extra_body) is not bool:
            raise ValueError("handles_extra_body must be a boolean")
        if self.wrap_tool_executor is not None and not callable(
            self.wrap_tool_executor
        ):
            raise ValueError("wrap_tool_executor must be callable")

    @property
    def base_url(self) -> str:
        """Alias for :attr:`api_base`."""
        return self.api_base

    @property
    def token(self) -> str:
        """Alias for :attr:`api_key`."""
        return self.api_key


def validate_provider_endpoint(endpoint: Any) -> CodexProviderEndpoint:
    """Require the documented endpoint type, not an arbitrary duck type.

    The factory is trusted host code, but the runtime relies on the
    constructor's URL/credential validation. Accepting any object with
    ``api_base``/``api_key`` would let a factory skip those checks.

    Args:
        endpoint: The value yielded by ``provider_factory``.

    Returns:
        CodexProviderEndpoint: The validated endpoint.

    Raises:
        TypeError: If ``endpoint`` is not a :class:`CodexProviderEndpoint`.
    """
    if not isinstance(endpoint, CodexProviderEndpoint):
        raise TypeError(
            "provider_factory must yield a CodexProviderEndpoint; got "
            f"{type(endpoint).__name__}"
        )
    return endpoint


def wrap_provider_executors(
    endpoint: CodexProviderEndpoint, executors: dict[str, Any]
) -> dict[str, Any]:
    """Apply the host's executor hook before the MCP bridge publishes tools.

    The bridge and the shim receive only wrapped executors, so the host sees
    every ADK tool call and can fence it against the invocation's policy.

    Args:
        endpoint: The invocation's provider endpoint.
        executors: ``{tool name: executor}`` built for this turn.

    Returns:
        dict[str, Any]: The same mapping when the endpoint has no hook,
        otherwise a new mapping of wrapped executors.

    Raises:
        TypeError: If the hook does not return a callable for a tool.
    """
    wrapper = endpoint.wrap_tool_executor
    if wrapper is None:
        return executors
    wrapped: dict[str, Any] = {}
    for name, executor in executors.items():
        result = wrapper(name, executor)
        if not callable(result):
            raise TypeError(
                f"provider wrap_tool_executor({name!r}) did not return a callable"
            )
        wrapped[name] = result
    return wrapped
