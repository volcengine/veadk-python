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

"""A plain-HTTP web fetch tool that extracts readable content.

Does a plain HTTP GET and converts the HTML into bounded markdown/text. It does
NOT execute JavaScript — for JS-heavy / login-protected pages a headless browser
is needed instead. The design mirrors OpenClaw's `web_fetch`: Chrome-like
headers, SSRF protection (block private/internal addresses, re-validate every
redirect), a download-size cap, a coarse HTML→markdown extractor, and a short
in-memory cache.
"""

import html as _html
import ipaddress
import re
import socket
import time
from urllib.parse import urljoin, urlparse

import requests

from google.adk.tools import ToolContext

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

# ---- limits / defaults (mirror OpenClaw's tools.web.fetch.* config) ----------
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_ACCEPT_LANGUAGE = "en-US,en;q=0.9"
_TIMEOUT_SECONDS = 30
_MAX_REDIRECTS = 3
_MAX_RESPONSE_BYTES = 2_000_000  # cap the download before truncation (HTML)
_MAX_PDF_BYTES = 10_000_000  # higher cap for PDFs (truncation corrupts parsing)
_MAX_CHARS_CAP = 200_000  # hard ceiling for the max_chars parameter
_DEFAULT_MAX_CHARS = 50_000
_CACHE_TTL_SECONDS = 15 * 60
_CACHE_MAX_ENTRIES = 128

# Tiny in-process TTL cache: {(url, mode, max_chars): (expires_at, result)}.
_CACHE: dict[tuple[str, str, int], tuple[float, dict]] = {}


class _WebFetchError(Exception):
    """Internal: surfaced to the model as {"error": ...}."""


# ---------------------------------------------------------------- SSRF guard --
def _assert_public_host(host: str) -> None:
    """Resolve `host` and reject private/internal/loopback/link-local targets.

    Note: this validates the resolved addresses but does not pin the connection
    to them, so a determined attacker controlling DNS could still race the
    re-resolution (TOCTOU). It blocks the common SSRF cases; pinning the socket
    to the validated IP would be the hardening follow-up.
    """
    if not host:
        raise _WebFetchError("missing host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise _WebFetchError(f"DNS resolution failed for {host!r}: {e}")
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise _WebFetchError(f"Blocked non-public address for host {host!r}: {ip}")


def _check_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise _WebFetchError("only http(s) URLs are supported")
    if not parsed.hostname:
        raise _WebFetchError("URL has no host")
    _assert_public_host(parsed.hostname)
    return parsed.hostname


# ---------------------------------------------- coarse HTML -> markdown/text --
def _normalize_whitespace(value: str) -> str:
    value = value.replace("\r", "")
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = re.sub(r"[ \t]{2,}", " ", value)
    return value.strip()


def _strip_tags(value: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", "", value))


def _html_to_markdown(html_text: str) -> tuple[str, str | None]:
    """Coarse HTML→markdown (ported from OpenClaw's `htmlToMarkdown`)."""
    title_match = re.search(
        r"<title[^>]*>([\s\S]*?)</title>", html_text, flags=re.IGNORECASE
    )
    title = (
        _normalize_whitespace(_strip_tags(title_match.group(1)))
        if title_match
        else None
    )

    text = re.sub(
        r"<script[\s\S]*?</script(?:\s+[^>]*)?>", "", html_text, flags=re.IGNORECASE
    )
    text = re.sub(r"<style[\s\S]*?</style(?:\s+[^>]*)?>", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"<noscript[\s\S]*?</noscript(?:\s+[^>]*)?>", "", text, flags=re.IGNORECASE
    )

    # Preserve link targets so fetched pages stay source-auditable.
    def _link(m: re.Match) -> str:
        href, body = m.group(1), m.group(2)
        label = _normalize_whitespace(_strip_tags(body))
        return f"[{label}]({href})" if label else href

    text = re.sub(
        r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>([\s\S]*?)</a>",
        _link,
        text,
        flags=re.IGNORECASE,
    )

    def _heading(m: re.Match) -> str:
        level = max(1, min(6, int(m.group(1))))
        label = _normalize_whitespace(_strip_tags(m.group(2)))
        return f"\n{'#' * level} {label}\n"

    text = re.sub(
        r"<h([1-6])[^>]*>([\s\S]*?)</h\1>", _heading, text, flags=re.IGNORECASE
    )

    def _li(m: re.Match) -> str:
        label = _normalize_whitespace(_strip_tags(m.group(1)))
        return f"\n- {label}" if label else ""

    text = re.sub(r"<li[^>]*>([\s\S]*?)</li>", _li, text, flags=re.IGNORECASE)
    text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(
        r"</(p|div|section|article|header|footer|table|tr|ul|ol)>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    text = _strip_tags(text)
    return _normalize_whitespace(text), title


def _meta_refresh_url(html_text: str) -> str | None:
    """Return the target of a `<meta http-equiv="refresh" content="0;url=...">`
    tag, if present (the JS-free redirect used by shell pages like sina.com)."""
    m = re.search(
        r"<meta[^>]+http-equiv=[\"']?refresh[\"']?[^>]*content=[\"']?[^\"'>]*?url=([^\"'>\s]+)",
        html_text[:4096],
        flags=re.IGNORECASE,
    )
    return _html.unescape(m.group(1)) if m else None


def _extract_pdf_text(raw: bytes) -> tuple[str, str | None] | None:
    """Extract text from PDF bytes via pypdf. Returns (text, title), or None if
    pypdf isn't installed."""
    try:
        import io

        from pypdf import PdfReader
    except ImportError:
        return None
    reader = PdfReader(io.BytesIO(raw))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - skip unparseable pages
            continue
    title = None
    try:
        if reader.metadata and reader.metadata.title:
            title = str(reader.metadata.title)
    except Exception:  # noqa: BLE001
        title = None
    return _normalize_whitespace("\n\n".join(parts)), title


def _markdown_to_text(markdown: str) -> str:
    text = re.sub(r"!\[[^\]]*]\([^)]+\)", "", markdown)  # images
    text = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", text)  # links -> label
    text = re.sub(r"`([^`]+)`", r"\1", text)  # inline code
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)  # headings
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)  # bullets
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)  # numbered
    return _normalize_whitespace(text)


# ----------------------------------------------------------------- the tool --
def web_fetch(
    url: str,
    extract_mode: str = "markdown",
    max_chars: int = _DEFAULT_MAX_CHARS,
    tool_context: ToolContext | None = None,
) -> dict:
    """Fetch a web page over HTTP(S) and return its readable main content.

    Performs a plain HTTP GET (no JavaScript execution) and extracts the page's
    readable text. Handles HTML pages (converted to markdown/text) and **PDF**
    URLs (text extracted via pypdf). Follows HTTP and `<meta refresh>` redirects.
    Use it to read articles, docs, or any public URL the user references. For
    pages that require login or render entirely via JavaScript, the content may
    be incomplete.

    Args:
        url: The http(s) URL to fetch.
        extract_mode: "markdown" (default, keeps headings/links/lists) or "text"
            (plain text with markdown decoration removed).
        max_chars: Truncate the extracted content to at most this many characters.

    Returns:
        A dict with keys: "url" (final URL after redirects), "title", "content",
        and "truncated" (bool). On failure, a dict with an "error" key.
    """
    mode = extract_mode if extract_mode in ("markdown", "text") else "markdown"
    try:
        max_chars = int(max_chars)
    except (TypeError, ValueError):
        max_chars = _DEFAULT_MAX_CHARS
    max_chars = max(1, min(max_chars, _MAX_CHARS_CAP))

    cache_key = (url, mode, max_chars)
    cached = _CACHE.get(cache_key)
    if cached and cached[0] > time.monotonic():
        return cached[1]

    try:
        result = _fetch_and_extract(url, mode, max_chars)
    except _WebFetchError as e:
        logger.warning(f"web_fetch failed for {url!r}: {e}")
        return {"error": str(e)}
    except requests.RequestException as e:
        logger.warning(f"web_fetch request error for {url!r}: {e}")
        return {"error": f"request failed: {e}"}

    # Cache + bound the cache size.
    if len(_CACHE) >= _CACHE_MAX_ENTRIES:
        _CACHE.clear()
    _CACHE[cache_key] = (time.monotonic() + _CACHE_TTL_SECONDS, result)
    return result


def _read_capped(response: requests.Response, cap: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=16_384):
        if not chunk:
            continue
        chunks.append(chunk)
        total += len(chunk)
        if total >= cap:
            break
    return b"".join(chunks)


def _result(url: str, title: str | None, content: str, max_chars: int) -> dict:
    return {
        "url": url,
        "title": title,
        "content": content[:max_chars],
        "truncated": len(content) > max_chars,
    }


def _fetch_and_extract(url: str, mode: str, max_chars: int) -> dict:
    session = requests.Session()
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept-Language": _ACCEPT_LANGUAGE,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    current = url
    hops = 0
    # Follow HTTP 3xx AND <meta refresh> redirects, both bounded by the same hop
    # budget, SSRF-checking every hop.
    while True:
        _check_url(current)
        response = session.get(
            current,
            headers=headers,
            timeout=_TIMEOUT_SECONDS,
            allow_redirects=False,
            stream=True,
        )

        if response.is_redirect and response.headers.get("location"):
            response.close()
            hops += 1
            if hops > _MAX_REDIRECTS:
                raise _WebFetchError(f"too many redirects (>{_MAX_REDIRECTS})")
            current = urljoin(current, response.headers["location"])
            continue

        if not response.ok:
            status = response.status_code
            response.close()
            raise _WebFetchError(f"HTTP {status}")

        content_type = response.headers.get("content-type", "")
        is_pdf = "pdf" in content_type.lower()
        raw = _read_capped(response, _MAX_PDF_BYTES if is_pdf else _MAX_RESPONSE_BYTES)
        response.close()

        # PDF (by content-type or magic bytes) -> extract text via pypdf.
        if is_pdf or raw[:5] == b"%PDF-":
            extracted = _extract_pdf_text(raw)
            if extracted is None:
                return {
                    "url": current,
                    "title": None,
                    "content": "[PDF detected — text extraction requires `pypdf`]",
                    "truncated": False,
                }
            text, title = extracted
            return _result(
                current, title, text or "[PDF had no extractable text]", max_chars
            )

        # Decode: honor charset from the header, else fall back to utf-8.
        charset = "utf-8"
        m = re.search(r"charset=([\w-]+)", content_type, flags=re.IGNORECASE)
        if m:
            charset = m.group(1)
        try:
            body = raw.decode(charset, errors="replace")
        except LookupError:
            body = raw.decode("utf-8", errors="replace")

        is_html = "html" in content_type.lower() or "xml" in content_type.lower()

        # Honor <meta refresh> redirects on shell pages (e.g. sina.com).
        if is_html and hops < _MAX_REDIRECTS:
            meta = _meta_refresh_url(body)
            if meta:
                nxt = urljoin(current, meta)
                if nxt != current:
                    hops += 1
                    current = nxt
                    continue

        if not is_html:
            # Other text-ish content: return as-is (truncated).
            return _result(current, None, _normalize_whitespace(body), max_chars)

        markdown, title = _html_to_markdown(body)
        content = markdown if mode == "markdown" else _markdown_to_text(markdown)
        if not content:
            content = _normalize_whitespace(_strip_tags(body))
        return _result(current, title, content, max_chars)
