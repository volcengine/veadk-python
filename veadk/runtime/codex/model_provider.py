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

"""How a Codex thread reaches its model: directly, or through the shim.

Codex speaks the OpenAI Responses API. Some model endpoints (Volcengine Ark,
BytePlus ModelArk, OpenAI) serve that API compatibly, so Codex can call them
*directly*; everything else goes through VeADK's in-process Responses-to-chat
shim (:mod:`veadk.runtime.codex.proxy`).

Everything here is expressed as a ``thread_start(config=...)`` override rather
than ``config.toml``. Every key in :func:`lean_codex_config` and every provider
key used below was checked against the pinned CLI (0.159.2) by capturing the
request Codex sends to a stub model: each takes effect at thread level, so no
file-level fallback is needed.

Credentials never enter the thread config. A route carries them in ``env``
(the provider's ``env_key`` names the variable), which is excluded from the
route's ``repr``. Note that :func:`~veadk.runtime.codex.config.codex_subprocess_env`
blanks every inherited variable whose name looks like a credential, so the
caller must apply ``route.env`` *after* that masking.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit

from veadk.runtime.codex.config import _KEY_ENV

if TYPE_CHECKING:
    from veadk.runtime.codex.config import CodexRuntimeConfig

Transport = Literal["direct", "shim"]

#: Provider id of the in-process shim route; matches ``runtime._PROVIDER_ID``.
SHIM_PROVIDER_ID = "veadk"
#: Provider id of the direct route.
DIRECT_PROVIDER_ID = "veadk_direct"
#: Env var carrying the model API key on the direct route. Named like a
#: credential on purpose, so ``codex_subprocess_env`` masks any host value.
DIRECT_KEY_ENV = "VEADK_CODEX_MODEL_API_KEY"
# Env vars carrying sensitive model headers; the VEADK_CODEX_ prefix keeps them
# out of the sandboxed shell (see `pinned_codex_settings`).
_HEADER_ENV_PREFIX = "VEADK_CODEX_MODEL_HEADER_"
_SENSITIVE_HEADER_NAMES = frozenset({"authorization", "proxy-authorization", "cookie"})
_SENSITIVE_HEADER_MARKERS = ("key", "token", "secret", "password", "signature")

#: Small, bounded retries for the direct route. Codex's defaults (4 request /
#: 5 stream retries with backoff) turn one dead endpoint into a long stall;
#: the runtime has no turn-level timeout of its own.
_DIRECT_REQUEST_MAX_RETRIES = 2
_DIRECT_STREAM_MAX_RETRIES = 2

#: Hosts known to serve the OpenAI Responses API compatibly. A suffix entry
#: (leading dot) matches the domain itself and any subdomain.
_DIRECT_HOST_SUFFIXES = (".volces.com", ".bytepluses.com")
_DIRECT_HOSTS = frozenset({"api.openai.com"})


@dataclass(frozen=True)
class CodexModelRoute:
    """One way for a Codex thread to reach its model.

    Attributes:
        transport: ``"direct"`` or ``"shim"``.
        provider_id: Key under ``model_providers``; pass it as the thread's
            ``model_provider``.
        provider_config: Value for ``config["model_providers"][provider_id]``.
            Never contains a credential.
        env: Environment variables the Codex subprocess needs for this route
            (credentials). Excluded from ``repr`` and must never be logged.
    """

    transport: Transport
    provider_id: str
    provider_config: dict[str, Any]
    env: dict[str, str] = field(repr=False)

    def thread_config(self) -> dict[str, Any]:
        """Build the ``thread_start(config=...)`` override for this route.

        Returns:
            dict[str, Any]: A fresh dict with this route's provider merged into
            :func:`lean_codex_config`.
        """
        config = lean_codex_config()
        config["model_providers"] = {
            self.provider_id: copy.deepcopy(self.provider_config)
        }
        return config


def pinned_codex_settings() -> dict[str, Any]:
    """Settings every VeADK Codex thread needs, on either transport.

    The single source for both the generated ``config.toml`` (shim and direct)
    and the direct transport's thread override. Each key was verified against
    CLI 0.159.2:

    - ``model_reasoning_summary="none"``: Codex otherwise sends
      ``reasoning.summary="auto"``, which Ark rejects outright.
    - ``features.unbounded_connection_retries=false``: otherwise an unreachable
      endpoint is retried forever instead of failing the turn fast.
    - ``features.goals=false``: VeADK does not drive Codex goals; left on,
      Codex advertises ``create_goal``/``get_goal``/``update_goal``.
    - ``shell_environment_policy.exclude``: keeps VeADK's credentials (the
      direct model key, the shim turn token, the MCP bridge token) out of the
      shell Codex runs for the model; without it `env` in the sandbox printed
      them.

    Returns:
        dict[str, Any]: A fresh nested dict, safe for the caller to mutate.
    """
    return {
        "model_reasoning_summary": "none",
        "features": {"unbounded_connection_retries": False, "goals": False},
        "shell_environment_policy": {
            "exclude": ["VEADK_CODEX_*", "*API_KEY*", "*SECRET*", "*TOKEN*"]
        },
    }


def lean_codex_config() -> dict[str, Any]:
    """:func:`pinned_codex_settings` plus the direct transport's tool trimming.

    On top of the pinned settings (all verified at thread level on 0.159.2):

    - ``features.multi_agent=false``: removes ``multi_agent_v1``.
    - ``features.view_image=false``: removes ``view_image``.
    - ``web_search="disabled"``: removes the hosted ``web_search`` tool.
    - ``tools.experimental_request_user_input.enabled=false``: removes
      ``request_user_input``; there is no interactive user behind a turn.

    Together the trimmed tools roughly halve the input tokens of each request.
    The shim keeps Codex's tools (it forwards function tools only anyway).

    Returns:
        dict[str, Any]: A fresh nested dict, safe for the caller to mutate.
    """
    config = pinned_codex_settings()
    config["web_search"] = "disabled"
    config["features"].update({"multi_agent": False, "view_image": False})
    config["tools"] = {"experimental_request_user_input": {"enabled": False}}
    return config


def _host(api_base: str) -> str:
    """Lower-cased host of ``api_base`` (port and path dropped), or ``""``."""
    value = (api_base or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = f"//{value}"
    try:
        return (urlsplit(value).hostname or "").rstrip(".")
    except ValueError:
        return ""


def _serves_responses_api(api_base: str) -> bool:
    host = _host(api_base)
    if not host:
        return False
    if host in _DIRECT_HOSTS:
        return True
    return any(
        host.endswith(suffix) or host == suffix[1:] for suffix in _DIRECT_HOST_SUFFIXES
    )


def resolve_transport(runtime_config: "CodexRuntimeConfig", api_base: str) -> Transport:
    """Pick the route for ``api_base``.

    An explicit ``runtime_config.model_transport`` ("direct"/"shim") wins;
    ``VEADK_CODEX_MODEL_TRANSPORT`` reaches it through
    :meth:`CodexRuntimeConfig.from_agent`. ``"auto"`` picks ``"direct"`` only
    for hosts known to serve the Responses API compatibly.

    Args:
        runtime_config: The resolved Codex runtime config.
        api_base: The agent's model API base URL.

    Returns:
        Transport: ``"direct"`` or ``"shim"``.
    """
    transport = runtime_config.model_transport
    if transport in ("direct", "shim"):
        return transport
    return "direct" if _serves_responses_api(api_base) else "shim"


def _direct_base_url(api_base: str) -> str:
    base = (api_base or "").strip().rstrip("/")
    if base.endswith("/responses"):
        base = base[: -len("/responses")].rstrip("/")
    parts = urlsplit(base)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(
            "direct Codex route needs an http(s) api_base with a host; "
            f"got scheme={parts.scheme!r}"
        )
    return base


def direct_route(
    api_base: str, api_key: str, *, extra_headers: dict[str, str] | None = None
) -> CodexModelRoute:
    """Route Codex straight at the model endpoint's Responses API.

    Args:
        api_base: Endpoint base, e.g. ``https://ark.cn-beijing.volces.com/api/v3``.
            A trailing slash or ``/responses`` suffix is removed; Codex appends
            ``/responses`` itself.
        api_key: Model API key. Travels only in ``route.env``.
        extra_headers: Headers for every model request. Sensitive ones (see
            :func:`is_sensitive_header`) go through ``env_http_headers``: the
            config file names an env var, and the value travels only in
            ``route.env``, which the sandboxed shell cannot see. The rest are
            static ``http_headers``.

    Returns:
        CodexModelRoute: The direct route.

    Raises:
        ValueError: If ``api_key`` is empty or ``api_base`` is not http(s).
    """
    if not api_key:
        raise ValueError("direct Codex route needs a non-empty api_key")
    provider_config: dict[str, Any] = {
        "name": DIRECT_PROVIDER_ID,
        "base_url": _direct_base_url(api_base),
        "env_key": DIRECT_KEY_ENV,
        "wire_api": "responses",
        "request_max_retries": _DIRECT_REQUEST_MAX_RETRIES,
        "stream_max_retries": _DIRECT_STREAM_MAX_RETRIES,
    }
    env = {DIRECT_KEY_ENV: api_key}
    static: dict[str, str] = {}
    from_env: dict[str, str] = {}
    for index, (name, value) in enumerate((extra_headers or {}).items()):
        if is_sensitive_header(str(name)):
            var = f"{_HEADER_ENV_PREFIX}{index}"
            from_env[str(name)] = var
            env[var] = str(value)
        else:
            static[str(name)] = str(value)
    if static:
        provider_config["http_headers"] = static
    if from_env:
        provider_config["env_http_headers"] = from_env
    return CodexModelRoute(
        transport="direct",
        provider_id=DIRECT_PROVIDER_ID,
        provider_config=provider_config,
        env=env,
    )


def is_sensitive_header(name: str) -> bool:
    """Whether a header carries a credential and must stay out of files.

    Codex's config file sits on disk for the whole turn; a credential written
    there is readable by anything that can read CODEX_HOME.
    """
    lowered = name.strip().lower()
    return lowered in _SENSITIVE_HEADER_NAMES or any(
        marker in lowered for marker in _SENSITIVE_HEADER_MARKERS
    )


def shim_route(shim_url: str, turn_token: str) -> CodexModelRoute:
    """Route Codex through the in-process shim, as ``_prepare_codex_home`` does.

    Args:
        shim_url: The shim's base URL (without ``/v1``).
        turn_token: Per-turn token the shim uses to find the turn.

    Returns:
        CodexModelRoute: The shim route.
    """
    return CodexModelRoute(
        transport="shim",
        provider_id=SHIM_PROVIDER_ID,
        provider_config={
            "name": SHIM_PROVIDER_ID,
            "base_url": f"{shim_url.rstrip('/')}/v1",
            "env_key": _KEY_ENV,
            "wire_api": "responses",
        },
        env={_KEY_ENV: turn_token},
    )
