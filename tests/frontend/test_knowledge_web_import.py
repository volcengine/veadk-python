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

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence

import httpx
import pytest

from frontend.server.knowledge import web_import
from frontend.server.knowledge.web_import import (
    MAX_HTML_BYTES,
    MAX_MARKDOWN_BYTES,
    WebImportContentError,
    WebImporter,
    WebImportFetchError,
    WebImportSecurityError,
    WebImportTooLargeError,
)

PUBLIC_IP = "93.184.216.34"


async def _public_resolver(hostname: str, port: int) -> Sequence[str]:
    assert hostname
    assert port in {80, 443}
    return (PUBLIC_IP,)


def _transport_factory(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[[], httpx.AsyncBaseTransport]:
    return lambda: httpx.MockTransport(handler)


class _ChunkStream(httpx.AsyncByteStream):
    def __init__(self, *chunks: bytes) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


@pytest.mark.asyncio
async def test_import_extracts_chinese_markdown_pins_ip_and_preserves_sni() -> None:
    html = """
    <html lang="zh-CN">
      <head><title>中文测试页面</title></head>
      <body>
        <nav>导航噪声</nav>
        <article>
          <h1>安全导入网页正文</h1>
          <p>这是用于验证中文正文抽取的完整段落。页面中的正文应被转换为 Markdown，导航和页脚不应成为主要内容。</p>
          <p>第二段包含更多有效文字，以便正文抽取器稳定识别文章区域，并保留清晰的段落结构和标题信息。</p>
        </article>
        <footer>页脚噪声</footer>
      </body>
    </html>
    """.encode()

    def upstream(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL(f"https://{PUBLIC_IP}/article?lang=zh")
        assert request.headers["host"] == "news.example"
        assert request.extensions["sni_hostname"] == "news.example"
        assert isinstance(request.extensions["sni_hostname"], str)
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        return httpx.Response(
            200,
            content=html,
            headers={"content-type": "text/html; charset=utf-8"},
        )

    importer = WebImporter(
        resolver=_public_resolver,
        transport_factory=_transport_factory(upstream),
    )
    result = await importer.import_url(
        " HTTPS://news.example/article?lang=zh#ignored-fragment "
    )

    assert result.title == "安全导入网页正文"
    assert "安全导入网页正文" in result.markdown
    assert "这是用于验证中文正文抽取" in result.markdown
    assert "url:" not in result.markdown
    assert result.final_url == "https://news.example/article?lang=zh"


@pytest.mark.asyncio
async def test_extracted_markdown_never_embeds_source_url_frontmatter() -> None:
    html = b"""
    <html>
      <head><title>Public article</title></head>
      <body><article><p>This is the public article body used for import.</p></article></body>
    </html>
    """
    importer = WebImporter(
        resolver=_public_resolver,
        transport_factory=_transport_factory(
            lambda request: httpx.Response(
                200,
                content=html,
                headers={"content-type": "text/html"},
            )
        ),
    )

    result = await importer.import_url(
        "https://example.com/article?token=must-not-enter-markdown"
    )

    assert result.title == "Public article"
    assert "public article body" in result.markdown
    assert "must-not-enter-markdown" not in result.markdown
    assert "url:" not in result.markdown


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://example.com/file",
        "https://user@example.com/",
        "https://user:secret@example.com/",
        "https://example.com:8080/",
        "https://example.com\\@127.0.0.1/",
        "https://[fe80::1%25eth0]/",
        "https://example.com/\x00path",
    ],
)
async def test_rejects_unsafe_url_syntax_before_network(url: str) -> None:
    async def unexpected_resolver(hostname: str, port: int) -> Sequence[str]:
        raise AssertionError(f"unexpected DNS lookup for {hostname}:{port}")

    with pytest.raises(WebImportSecurityError):
        await WebImporter(resolver=unexpected_resolver).import_url(url)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "addresses",
    [
        ("127.0.0.1",),
        ("10.0.0.1",),
        ("169.254.169.254",),
        ("100.64.0.1",),
        ("::1",),
        ("fc00::1",),
        (PUBLIC_IP, "192.168.1.1"),
        (),
        ("not-an-ip",),
    ],
)
async def test_rejects_any_non_public_dns_result(addresses: Sequence[str]) -> None:
    async def resolver(hostname: str, port: int) -> Sequence[str]:
        return addresses

    with pytest.raises(WebImportSecurityError):
        await WebImporter(resolver=resolver).import_url("https://example.com/")


@pytest.mark.asyncio
async def test_follows_three_redirects_and_revalidates_every_hop() -> None:
    resolved_hosts: list[str] = []
    requested_paths: list[str] = []

    async def resolver(hostname: str, port: int) -> Sequence[str]:
        resolved_hosts.append(hostname)
        return (PUBLIC_IP,)

    def upstream(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        redirects = {
            "/": "/one#discarded",
            "/one": "https://second.example/two",
            "/two": "/final",
        }
        if request.url.path in redirects:
            return httpx.Response(
                302, headers={"location": redirects[request.url.path]}
            )
        return httpx.Response(
            200,
            content=b"<html><body><article>final content</article></body></html>",
            headers={"content-type": "application/xhtml+xml"},
        )

    importer = WebImporter(
        resolver=resolver,
        transport_factory=_transport_factory(upstream),
        extractor=lambda html, url: ("# Final\n\nImported content", "Final"),
    )
    result = await importer.import_url("https://first.example")

    assert resolved_hosts == [
        "first.example",
        "first.example",
        "second.example",
        "second.example",
    ]
    assert requested_paths == ["/", "/one", "/two", "/final"]
    assert result.final_url == "https://second.example/final"


@pytest.mark.asyncio
async def test_rejects_a_fourth_redirect() -> None:
    def upstream(request: httpx.Request) -> httpx.Response:
        step = int(request.url.path.removeprefix("/step/") or "0")
        return httpx.Response(302, headers={"location": f"/step/{step + 1}"})

    importer = WebImporter(
        resolver=_public_resolver,
        transport_factory=_transport_factory(upstream),
    )
    with pytest.raises(WebImportFetchError, match="Too many redirects"):
        await importer.import_url("https://example.com/step/0")


@pytest.mark.asyncio
async def test_rejects_redirect_that_rebinds_to_private_address() -> None:
    resolution_count = 0
    request_count = 0

    async def resolver(hostname: str, port: int) -> Sequence[str]:
        nonlocal resolution_count
        resolution_count += 1
        return (PUBLIC_IP,) if resolution_count == 1 else ("127.0.0.1",)

    def upstream(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(302, headers={"location": "/next"})

    importer = WebImporter(
        resolver=resolver,
        transport_factory=_transport_factory(upstream),
    )
    with pytest.raises(WebImportSecurityError):
        await importer.import_url("https://rebind.example/")
    assert resolution_count == 2
    assert request_count == 1


@pytest.mark.asyncio
async def test_rejects_https_redirect_downgrade_before_second_request() -> None:
    request_count = 0

    def upstream(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            302,
            headers={"location": "http://secure.example/plaintext"},
        )

    importer = WebImporter(
        resolver=_public_resolver,
        transport_factory=_transport_factory(upstream),
    )
    with pytest.raises(WebImportSecurityError, match="downgrade"):
        await importer.import_url("https://secure.example/")
    assert request_count == 1


@pytest.mark.asyncio
async def test_total_import_deadline_is_reported_as_fetch_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow_resolver(hostname: str, port: int) -> Sequence[str]:
        await asyncio.sleep(1)
        return (PUBLIC_IP,)

    monkeypatch.setattr(web_import, "TOTAL_IMPORT_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(WebImportFetchError, match="15 second deadline"):
        await WebImporter(resolver=slow_resolver).import_url("https://example.com/")


@pytest.mark.asyncio
async def test_redirect_requires_location_header() -> None:
    importer = WebImporter(
        resolver=_public_resolver,
        transport_factory=_transport_factory(lambda request: httpx.Response(302)),
    )
    with pytest.raises(WebImportFetchError, match="Location"):
        await importer.import_url("https://example.com/")


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", ["", "text/plain", "application/json"])
async def test_rejects_non_html_content_type(content_type: str) -> None:
    importer = WebImporter(
        resolver=_public_resolver,
        transport_factory=_transport_factory(
            lambda request: httpx.Response(
                200,
                content=b"not html",
                headers={"content-type": content_type},
            )
        ),
    )
    with pytest.raises(WebImportContentError, match="not HTML"):
        await importer.import_url("https://example.com/")


@pytest.mark.asyncio
async def test_rejects_declared_html_over_five_megabytes() -> None:
    importer = WebImporter(
        resolver=_public_resolver,
        transport_factory=_transport_factory(
            lambda request: httpx.Response(
                200,
                headers={
                    "content-type": "text/html",
                    "content-length": str(MAX_HTML_BYTES + 1),
                },
            )
        ),
    )
    with pytest.raises(WebImportTooLargeError, match="5 MB"):
        await importer.import_url("https://example.com/")


@pytest.mark.asyncio
async def test_rejects_streamed_html_over_five_megabytes() -> None:
    stream = _ChunkStream(b"a" * MAX_HTML_BYTES, b"b")
    importer = WebImporter(
        resolver=_public_resolver,
        transport_factory=_transport_factory(
            lambda request: httpx.Response(
                200,
                stream=stream,
                headers={"content-type": "text/html"},
            )
        ),
    )
    with pytest.raises(WebImportTooLargeError, match="5 MB"):
        await importer.import_url("https://example.com/")


@pytest.mark.asyncio
async def test_rejects_markdown_over_two_megabytes() -> None:
    importer = WebImporter(
        resolver=_public_resolver,
        transport_factory=_transport_factory(
            lambda request: httpx.Response(
                200,
                content=b"<html><body>content</body></html>",
                headers={"content-type": "text/html"},
            )
        ),
        extractor=lambda html, url: ("x" * (MAX_MARKDOWN_BYTES + 1), "Title"),
    )
    with pytest.raises(WebImportTooLargeError, match="2 MB"):
        await importer.import_url("https://example.com/")


@pytest.mark.asyncio
async def test_rejects_empty_html_and_empty_extraction() -> None:
    empty_html_importer = WebImporter(
        resolver=_public_resolver,
        transport_factory=_transport_factory(
            lambda request: httpx.Response(
                200,
                content=b"",
                headers={"content-type": "text/html"},
            )
        ),
    )
    with pytest.raises(WebImportContentError, match="empty"):
        await empty_html_importer.import_url("https://example.com/")

    empty_markdown_importer = WebImporter(
        resolver=_public_resolver,
        transport_factory=_transport_factory(
            lambda request: httpx.Response(
                200,
                content=b"<html></html>",
                headers={"content-type": "text/html"},
            )
        ),
        extractor=lambda html, url: ("  ", "Title"),
    )
    with pytest.raises(WebImportContentError, match="No main content"):
        await empty_markdown_importer.import_url("https://example.com/")


@pytest.mark.asyncio
async def test_wraps_remote_status_and_network_errors() -> None:
    status_importer = WebImporter(
        resolver=_public_resolver,
        transport_factory=_transport_factory(
            lambda request: httpx.Response(
                503,
                headers={"content-type": "text/html"},
            )
        ),
    )
    with pytest.raises(WebImportFetchError, match="HTTP 503"):
        await status_importer.import_url("https://example.com/")

    def network_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    network_importer = WebImporter(
        resolver=_public_resolver,
        transport_factory=_transport_factory(network_error),
    )
    with pytest.raises(WebImportFetchError, match="request failed"):
        await network_importer.import_url("https://example.com/")
