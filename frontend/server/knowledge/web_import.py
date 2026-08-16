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

"""Safely fetch a public web page and extract its main content as Markdown."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit

import httpx
from trafilatura import extract, extract_metadata

MAX_REDIRECTS = 3
MAX_HTML_BYTES = 5 * 1024 * 1024
MAX_MARKDOWN_BYTES = 2 * 1024 * 1024
MAX_URL_LENGTH = 8192
DNS_TIMEOUT_SECONDS = 5.0
TOTAL_IMPORT_TIMEOUT_SECONDS = 15.0
REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
ALLOWED_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})
REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})

AddressResolver = Callable[[str, int], Awaitable[Sequence[str]]]
TransportFactory = Callable[[], httpx.AsyncBaseTransport]
MarkdownExtractor = Callable[[bytes, str], tuple[str, str]]


class WebImportError(RuntimeError):
    """Base error raised for a failed web import."""


class WebImportSecurityError(WebImportError):
    """The URL or its resolved destination violates the SSRF policy."""


class WebImportFetchError(WebImportError):
    """The remote page could not be fetched successfully."""


class WebImportContentError(WebImportError):
    """The response is not extractable HTML."""


class WebImportTooLargeError(WebImportContentError):
    """The downloaded HTML or extracted Markdown exceeds its size limit."""


@dataclass(frozen=True, slots=True)
class WebImportResult:
    markdown: str
    title: str
    final_url: str


@dataclass(frozen=True, slots=True)
class _ValidatedUrl:
    url: str
    hostname: str
    port: int
    authority: str


async def _resolve_addresses(hostname: str, port: int) -> Sequence[str]:
    """Resolve TCP addresses without blocking the event loop."""
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        return tuple(str(record[4][0]) for record in records)
    return (str(literal),)


def _default_transport_factory() -> httpx.AsyncBaseTransport:
    return httpx.AsyncHTTPTransport(retries=0, trust_env=False)


def _extract_markdown(html: bytes, final_url: str) -> tuple[str, str]:
    markdown = extract(
        html,
        url=final_url,
        output_format="markdown",
        with_metadata=False,
        include_comments=False,
        include_tables=True,
        include_images=False,
        include_links=True,
    )
    if not markdown:
        return "", ""
    metadata = extract_metadata(
        html.decode("utf-8", errors="replace"),
        default_url=final_url,
    )
    return markdown, (metadata.title if metadata is not None else "") or ""


def _validate_url(raw_url: str) -> _ValidatedUrl:
    value = raw_url.strip()
    if not value or len(value) > MAX_URL_LENGTH:
        raise WebImportSecurityError("URL is empty or too long.")
    if "\\" in value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise WebImportSecurityError("URL contains unsafe characters.")

    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        hostname_value = parsed.hostname
        port = parsed.port
        has_userinfo = parsed.username is not None or parsed.password is not None
    except (UnicodeError, ValueError) as exc:
        raise WebImportSecurityError("URL is malformed.") from exc

    if scheme not in {"http", "https"}:
        raise WebImportSecurityError("Only HTTP and HTTPS URLs are allowed.")
    if has_userinfo:
        raise WebImportSecurityError("URL user information is not allowed.")
    if not hostname_value or "%" in hostname_value:
        raise WebImportSecurityError("URL must contain a valid hostname.")

    hostname = _normalize_hostname(hostname_value)
    effective_port = port or (443 if scheme == "https" else 80)
    if effective_port not in {80, 443}:
        raise WebImportSecurityError("Only ports 80 and 443 are allowed.")

    normalized_port = ""
    if effective_port != (443 if scheme == "https" else 80):
        normalized_port = f":{effective_port}"
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    authority = f"{display_host}{normalized_port}"
    normalized = urlunsplit(
        SplitResult(
            scheme=scheme,
            netloc=authority,
            path=parsed.path or "/",
            query=parsed.query,
            fragment="",
        )
    )
    try:
        httpx.URL(normalized)
    except (UnicodeError, httpx.InvalidURL) as exc:
        raise WebImportSecurityError("URL is malformed.") from exc
    return _ValidatedUrl(normalized, hostname, effective_port, authority)


def _normalize_hostname(hostname: str) -> str:
    candidate = hostname.rstrip(".").lower()
    if not candidate:
        raise WebImportSecurityError("URL must contain a valid hostname.")
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        try:
            return candidate.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise WebImportSecurityError("URL hostname is invalid.") from exc


def _validated_public_addresses(addresses: Sequence[str]) -> tuple[str, ...]:
    validated: list[str] = []
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise WebImportSecurityError("DNS returned an invalid IP address.") from exc
        if not address.is_global:
            raise WebImportSecurityError(
                "URL resolves to a non-public network address."
            )
        normalized = str(address)
        if normalized not in validated:
            validated.append(normalized)
    if not validated:
        raise WebImportSecurityError("URL hostname did not resolve to an address.")
    return tuple(validated)


def _pinned_url(url: _ValidatedUrl, address: str) -> str:
    parsed = urlsplit(url.url)
    display_address = f"[{address}]" if ":" in address else address
    default_port = 443 if parsed.scheme == "https" else 80
    netloc = (
        display_address if url.port == default_port else f"{display_address}:{url.port}"
    )
    return urlunsplit(parsed._replace(netloc=netloc))


class WebImporter:
    """Fetch public HTML with pinned DNS results and extract Markdown."""

    def __init__(
        self,
        *,
        resolver: AddressResolver | None = None,
        transport_factory: TransportFactory | None = None,
        extractor: MarkdownExtractor | None = None,
    ) -> None:
        self._resolver = resolver or _resolve_addresses
        self._transport_factory = transport_factory or _default_transport_factory
        self._extractor = extractor or _extract_markdown

    async def import_url(self, url: str) -> WebImportResult:
        try:
            return await asyncio.wait_for(
                self._import_url(url),
                timeout=TOTAL_IMPORT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise WebImportFetchError(
                "Web import exceeded its 15 second deadline."
            ) from exc

    async def _import_url(self, url: str) -> WebImportResult:
        current = _validate_url(url)
        for redirect_count in range(MAX_REDIRECTS + 1):
            addresses = await self._resolve_public_addresses(current)
            response_data = await self._request(current, addresses[0])
            if response_data.redirect_location is not None:
                if redirect_count == MAX_REDIRECTS:
                    raise WebImportFetchError("Too many redirects.")
                redirected = _validate_url(
                    urljoin(current.url, response_data.redirect_location)
                )
                if current.url.startswith("https:") and redirected.url.startswith(
                    "http:"
                ):
                    raise WebImportSecurityError(
                        "HTTPS redirects must not downgrade to HTTP."
                    )
                current = redirected
                continue

            markdown, title = await asyncio.to_thread(
                self._extractor,
                response_data.content,
                current.url,
            )
            markdown = markdown.strip()
            if not markdown:
                raise WebImportContentError("No main content could be extracted.")
            if len(markdown.encode("utf-8")) > MAX_MARKDOWN_BYTES:
                raise WebImportTooLargeError("Extracted Markdown exceeds 2 MB.")
            return WebImportResult(
                markdown=markdown,
                title=title.strip(),
                final_url=current.url,
            )
        raise AssertionError("redirect loop did not terminate")

    async def _resolve_public_addresses(
        self,
        url: _ValidatedUrl,
    ) -> tuple[str, ...]:
        try:
            addresses = await asyncio.wait_for(
                self._resolver(url.hostname, url.port),
                timeout=DNS_TIMEOUT_SECONDS,
            )
        except WebImportError:
            raise
        except (OSError, asyncio.TimeoutError) as exc:
            raise WebImportFetchError("URL hostname could not be resolved.") from exc
        return _validated_public_addresses(addresses)

    async def _request(
        self,
        url: _ValidatedUrl,
        address: str,
    ) -> _FetchedResponse:
        headers = {
            "Accept": "text/html, application/xhtml+xml",
            "Host": url.authority,
            "User-Agent": "veadk-studio-web-import/1.0",
        }
        try:
            async with (
                httpx.AsyncClient(
                    transport=self._transport_factory(),
                    timeout=REQUEST_TIMEOUT,
                    follow_redirects=False,
                    trust_env=False,
                ) as client,
                client.stream(
                    "GET",
                    _pinned_url(url, address),
                    headers=headers,
                    extensions={"sni_hostname": url.hostname},
                ) as response,
            ):
                if response.status_code in REDIRECT_STATUS_CODES:
                    location = response.headers.get("location")
                    if not location:
                        raise WebImportFetchError(
                            "Redirect response is missing a Location header."
                        )
                    return _FetchedResponse(redirect_location=location)
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise WebImportFetchError(
                        f"Remote page returned HTTP {response.status_code}."
                    ) from exc
                self._validate_content_headers(response)
                content = await self._read_limited(response)
                return _FetchedResponse(content=content)
        except WebImportError:
            raise
        except httpx.HTTPError as exc:
            raise WebImportFetchError("Remote page request failed.") from exc

    @staticmethod
    def _validate_content_headers(response: httpx.Response) -> None:
        content_type = response.headers.get("content-type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type not in ALLOWED_CONTENT_TYPES:
            raise WebImportContentError("Remote response is not HTML.")
        content_length = response.headers.get("content-length")
        if content_length is None:
            return
        try:
            declared_size = int(content_length)
        except ValueError as exc:
            raise WebImportContentError("Remote response has an invalid size.") from exc
        if declared_size < 0:
            raise WebImportContentError("Remote response has an invalid size.")
        if declared_size > MAX_HTML_BYTES:
            raise WebImportTooLargeError("Remote HTML exceeds 5 MB.")

    @staticmethod
    async def _read_limited(response: httpx.Response) -> bytes:
        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > MAX_HTML_BYTES:
                raise WebImportTooLargeError("Remote HTML exceeds 5 MB.")
        if not content:
            raise WebImportContentError("Remote HTML is empty.")
        return bytes(content)


@dataclass(frozen=True, slots=True)
class _FetchedResponse:
    content: bytes = b""
    redirect_location: str | None = None


async def import_web_page(url: str) -> WebImportResult:
    """Convenience wrapper for one-off imports."""
    return await WebImporter().import_url(url)


__all__ = [
    "WebImportContentError",
    "WebImportError",
    "WebImportFetchError",
    "WebImportResult",
    "WebImportSecurityError",
    "WebImportTooLargeError",
    "WebImporter",
    "import_web_page",
]
