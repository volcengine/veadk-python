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

"""Build a lightweight search index from the Fumadocs MDX content.

The Ask-AI agent searches this index (no embeddings / vector DB needed). Run
this whenever the docs change — the deploy pipeline regenerates it before
shipping the agent.

    python build_index.py

Writes `docs_index.json` next to this file: a list of
`{ "url", "title", "lang", "headings", "text" }` page records.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content" / "docs"
OUTPUT = Path(__file__).resolve().parent / "docs_index.json"

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_IMPORT = re.compile(r"^\s*import\s.+$", re.MULTILINE)
_JSX_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_CODE_FENCE = re.compile(r"^```.*$", re.MULTILINE)
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MULTI_BLANK = re.compile(r"\n{3,}")
_TITLE = re.compile(r'(?:^|\n)title:\s*["\']?(.+?)["\']?\s*(?:\n|$)')
_HEADING = re.compile(r"^#{1,4}\s+(.+)$", re.MULTILINE)


def _route(path: Path) -> tuple[str, str]:
    """Map an MDX file path to (url, lang)."""
    rel = path.relative_to(CONTENT_DIR).as_posix()
    if rel.endswith(".en.mdx"):
        lang, slug = "en", rel[: -len(".en.mdx")]
    else:
        lang, slug = "cn", rel[: -len(".mdx")]
    if slug.endswith("/index"):
        slug = slug[: -len("/index")]
    elif slug == "index":
        slug = ""
    url = f"/{lang}/docs/{slug}".rstrip("/")
    return url, lang


def _to_text(raw: str) -> tuple[str, str, list[str]]:
    fm = _FRONTMATTER.match(raw)
    title = ""
    body = raw
    if fm:
        m = _TITLE.search(fm.group(1))
        if m:
            title = m.group(1).strip()
        body = raw[fm.end() :]
    headings = [h.strip() for h in _HEADING.findall(body)]
    body = _IMPORT.sub("", body)
    body = _CODE_FENCE.sub("", body)
    body = _JSX_TAG.sub("", body)
    body = _MD_LINK.sub(r"\1", body)
    body = _MULTI_BLANK.sub("\n\n", body).strip()
    if not title and headings:
        title = headings[0]
    return title, body, headings


def build() -> list[dict]:
    pages: list[dict] = []
    for path in sorted(CONTENT_DIR.rglob("*.mdx")):
        raw = path.read_text(encoding="utf-8")
        title, text, headings = _to_text(raw)
        url, lang = _route(path)
        if not text:
            continue
        pages.append(
            {
                "url": url,
                "title": title,
                "lang": lang,
                "headings": headings,
                "text": text,
            }
        )
    return pages


if __name__ == "__main__":
    pages = build()
    OUTPUT.write_text(json.dumps(pages, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"Indexed {len(pages)} pages -> {OUTPUT}")
