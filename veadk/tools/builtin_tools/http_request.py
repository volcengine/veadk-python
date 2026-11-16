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

"""A generic HTTP request tool with SSRF, redirect, and size safeguards.

The tool performs a single HTTP(S) request on behalf of the model. It reuses
``web_fetch``'s SSRF guard (``assert_public_url``) so private/internal targets
stay blocked, validates the URL again on every redirect hop, supports an
optional host allowlist (``TOOL_HTTP_ALLOWLIST``), resolves secret header
values from the environment via ``env:NAME``, and caps the downloaded body at
``max_bytes`` so a large response cannot exhaust memory.
"""

import os
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from veadk.tools.builtin_tools.web_fetch import assert_public_url

_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"})
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS = 3
_ALLOWLIST_ENV = "TOOL_HTTP_ALLOWLIST"
_BLOCKED_HEADERS = frozenset({"host", "content-length"})
# Credentials must not be replayed to a different origin (or over a
# downgraded scheme). httpx strips `Authorization` itself, but this tool
# follows redirects manually and therefore has to do it here.
_SENSITIVE_HEADERS = frozenset(
    {"authorization", "proxy-authorization", "cookie", "cookie2"}
)
_DEFAULT_PORTS = {"http": 80, "https": 443}
_MIN_TIMEOUT = 1
_MAX_TIMEOUT = 120
_MIN_MAX_BYTES = 1_000
_MAX_MAX_BYTES = 20_000_000


class _RequestAborted(Exception):
    """Internal error surfaced to the model as ``{"error": ...}``."""


def _validate_target(url: str, allowlist: tuple[str, ...]) -> None:
    """Validate scheme/host/SSRF policy and the optional host allowlist."""
    try:
        host = assert_public_url(url)
    except ValueError as exc:
        raise _RequestAborted(str(exc)) from exc
    if allowlist and not _host_is_allowed(host, allowlist):
        raise _RequestAborted(f"host {host!r} is not in the allowlist")


def _host_is_allowed(host: str, allowlist: tuple[str, ...]) -> bool:
    host = host.lower()
    return any(host == entry or host.endswith("." + entry) for entry in allowlist)


def _read_allowlist() -> tuple[str, ...]:
    raw = os.environ.get(_ALLOWLIST_ENV, "")
    return tuple(entry.strip().lower() for entry in raw.split(",") if entry.strip())


def _resolve_headers(
    headers: dict[str, str] | None,
) -> tuple[dict[str, str], frozenset[str]]:
    """Validate headers and resolve ``env:NAME`` values from the environment.

    Returns the resolved headers and the names whose values came from the
    environment, so redirects can drop secrets even for custom header names.
    """
    if headers is None:
        return {}, frozenset()
    if not isinstance(headers, dict):
        raise _RequestAborted("headers must be an object")
    resolved: dict[str, str] = {}
    from_environment: set[str] = set()
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise _RequestAborted("header names and values must be strings")
        lowered = name.lower()
        if lowered in _BLOCKED_HEADERS:
            raise _RequestAborted(f"header {name!r} is not allowed")
        if any(char in name for char in "\r\n") or any(
            char in value for char in "\r\n"
        ):
            raise _RequestAborted(f"header {name!r} contains an invalid character")
        if value.startswith("env:"):
            env_name = value[len("env:") :]
            env_value = os.environ.get(env_name) if env_name else None
            if not env_value:
                raise _RequestAborted(
                    f"environment variable for header {name!r} is not set"
                )
            resolved[name] = env_value
            from_environment.add(name)
        else:
            resolved[name] = value
    return resolved, frozenset(from_environment)


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is None:
        port = _DEFAULT_PORTS.get(scheme)
    return scheme, (parsed.hostname or "").lower(), port


def _headers_for_redirect(
    headers: dict[str, str],
    env_header_names: frozenset[str],
    previous_url: str,
    next_url: str,
) -> dict[str, str]:
    """Drop credentials that must not cross to the redirect target.

    Mirrors httpx's redirect handling: auth headers survive only a same-origin
    hop or a same-host http -> https upgrade. ``env:``-resolved headers are
    treated as secrets regardless of their name, and a scheme downgrade always
    strips credentials.
    """
    previous = _origin(previous_url)
    next_origin = _origin(next_url)
    if previous == next_origin:
        return headers
    previous_scheme, previous_host, previous_port = previous
    next_scheme, next_host, next_port = next_origin
    # Same-host upgrade on the standard ports (requests' behaviour).
    if (
        previous_scheme == "http"
        and next_scheme == "https"
        and previous_host == next_host
        and previous_port == 80
        and next_port == 443
    ):
        return headers
    return {
        name: value
        for name, value in headers.items()
        if name.lower() not in _SENSITIVE_HEADERS and name not in env_header_names
    }


def _read_body(response: httpx.Response, max_bytes: int) -> tuple[bytes, bool]:
    """Read at most ``max_bytes + 1`` bytes so truncation is detectable."""
    remaining = max_bytes + 1
    chunks: list[bytes] = []
    for chunk in response.iter_bytes():
        if not chunk:
            continue
        piece = chunk[:remaining]
        chunks.append(piece)
        remaining -= len(piece)
        if remaining <= 0:
            break
    raw = b"".join(chunks)
    if len(raw) > max_bytes:
        return raw[:max_bytes], True
    return raw, False


def _build_result(
    url: str,
    response: httpx.Response,
    method: str,
    raw: bytes,
    truncated: bool,
) -> dict:
    headers = {
        str(name).lower(): str(value) for name, value in response.headers.items()
    }
    if method == "HEAD":
        raw = b""
        truncated = False
    encoding = response.encoding or "utf-8"
    try:
        body = raw.decode(encoding, errors="replace")
    except LookupError:
        body = raw.decode("utf-8", errors="replace")
    return {
        "status_code": int(response.status_code),
        "url": url,
        "headers": headers,
        "content_type": headers.get("content-type"),
        "body": body,
        "bytes": len(raw),
        "truncated": truncated,
    }


def _perform_request(
    client: httpx.Client,
    url: str,
    method: str,
    headers: dict[str, str],
    params: dict[str, Any] | None,
    json_body: Any,
    body: str | None,
    max_bytes: int,
    follow_redirects: bool,
    allowlist: tuple[str, ...],
    env_header_names: frozenset[str] = frozenset(),
) -> dict:
    current_url = url
    current_method = method
    current_params = params
    current_json = json_body
    current_body = body
    current_headers = headers
    hops = 0

    while True:
        _validate_target(current_url, allowlist)
        with client.stream(
            current_method,
            current_url,
            headers=current_headers,
            params=current_params,
            json=current_json,
            content=current_body,
        ) as response:
            if follow_redirects and response.status_code in _REDIRECT_STATUSES:
                location = response.headers.get("location")
                if location:
                    hops += 1
                    if hops > _MAX_REDIRECTS:
                        raise _RequestAborted(
                            f"too many redirects (max {_MAX_REDIRECTS})"
                        )
                    next_url = urljoin(current_url, location)
                    # Credentials follow httpx semantics: never cross origins
                    # or downgrade to http, including env-resolved secrets.
                    current_headers = _headers_for_redirect(
                        current_headers,
                        env_header_names,
                        current_url,
                        next_url,
                    )
                    if current_method != "HEAD" and (
                        response.status_code == 303
                        or (
                            response.status_code in (301, 302)
                            and current_method == "POST"
                        )
                    ):
                        current_method = "GET"
                        current_json = None
                        current_body = None
                    current_url = next_url
                    # Query params belong to the original URL; a redirect's
                    # Location already carries the target query string.
                    current_params = None
                    continue
            raw, truncated = _read_body(response, max_bytes)
            return _build_result(current_url, response, current_method, raw, truncated)


def _run(
    url: str,
    method: str,
    headers: dict[str, str] | None,
    params: dict[str, Any] | None,
    json_body: Any,
    body: str | None,
    timeout: int,
    max_bytes: int,
    follow_redirects: bool,
) -> dict:
    if not isinstance(method, str):
        raise _RequestAborted("method must be a string")
    normalized_method = method.upper()
    if normalized_method not in _ALLOWED_METHODS:
        raise _RequestAborted(f"unsupported method: {method}")
    if type(timeout) is not int or not _MIN_TIMEOUT <= timeout <= _MAX_TIMEOUT:
        raise _RequestAborted(
            f"timeout must be an integer between {_MIN_TIMEOUT} and {_MAX_TIMEOUT}"
        )
    if type(max_bytes) is not int or not _MIN_MAX_BYTES <= max_bytes <= _MAX_MAX_BYTES:
        raise _RequestAborted(
            "max_bytes must be an integer between "
            f"{_MIN_MAX_BYTES} and {_MAX_MAX_BYTES}"
        )
    if not isinstance(url, str) or not url:
        raise _RequestAborted("url must be a non-empty string")
    if json_body is not None and body is not None:
        raise _RequestAborted("provide only one of json_body or body")

    allowlist = _read_allowlist()
    resolved_headers, env_header_names = _resolve_headers(headers)

    client = httpx.Client(timeout=timeout, follow_redirects=False)
    try:
        return _perform_request(
            client,
            url,
            normalized_method,
            resolved_headers,
            params,
            json_body,
            body,
            max_bytes,
            follow_redirects,
            allowlist,
            env_header_names,
        )
    finally:
        client.close()


def http_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any = None,
    body: str | None = None,
    timeout: int = 30,
    max_bytes: int = 5_000_000,
    follow_redirects: bool = False,
) -> dict:
    """Make an HTTP(S) request and return the status, headers, and body.

    Use this tool when you need to call an HTTP API or download a small
    resource. Private/internal addresses are blocked. Redirects are only
    followed when ``follow_redirects`` is true (at most three hops), and every
    hop is re-validated. Credentials (``Authorization``, ``Cookie``,
    ``Proxy-Authorization``, and any ``env:``-resolved header) are dropped when
    a redirect changes origin or downgrades to http. Set a header value to
    ``env:NAME`` to read a secret from environment variable ``NAME`` without
    exposing it in the arguments.

    Args:
        url: The absolute http(s) URL to request.
        method: One of GET, POST, PUT, PATCH, DELETE, HEAD (case-insensitive).
        headers: Optional request headers. ``env:NAME`` values are resolved from
            the environment.
        params: Optional query parameters.
        json_body: Optional JSON-serializable request body.
        body: Optional raw string request body. Mutually exclusive with
            ``json_body``.
        timeout: Request timeout in seconds (1-120).
        max_bytes: Maximum response body size in bytes (1,000-20,000,000).
            Larger bodies are truncated and ``truncated`` is set to true.
        follow_redirects: Whether to follow 301/302/303/307/308 redirects.

    Returns:
        A dict with ``status_code``, ``url``, ``headers``, ``content_type``,
        ``body``, ``bytes``, and ``truncated``. On failure, a dict with an
        ``error`` key.
    """
    try:
        return _run(
            url,
            method,
            headers,
            params,
            json_body,
            body,
            timeout,
            max_bytes,
            follow_redirects,
        )
    except _RequestAborted as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - tool results must not raise
        # Do not interpolate the exception text: it may contain request headers.
        return {"error": f"request failed ({type(exc).__name__})"}
