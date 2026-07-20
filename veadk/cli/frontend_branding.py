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

"""Resolve the optional title and logo used to brand VeADK Studio."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import filetype
import httpx

DEFAULT_SITE_TITLE = "VeADK Studio"
MAX_SITE_TITLE_LENGTH = 6
MAX_SITE_LOGO_BYTES = 5 * 1024 * 1024

_SUPPORTED_IMAGE_TYPES = {
    "image/avif",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/vnd.microsoft.icon",
    "image/webp",
    "image/x-icon",
}


@dataclass(frozen=True)
class SiteLogo:
    """Validated image bytes and browser-facing metadata."""

    content: bytes
    media_type: str
    extension: str


def normalize_site_title(value: str | None) -> str:
    """Return the default title or validate a user-provided title."""
    if value is None:
        return DEFAULT_SITE_TITLE
    title = value.strip()
    if not title:
        raise ValueError("Site title cannot be empty.")
    if len(title) > MAX_SITE_TITLE_LENGTH:
        raise ValueError(
            f"Site title must contain at most {MAX_SITE_TITLE_LENGTH} characters."
        )
    return title


def resolve_site_logo(source: str | None) -> SiteLogo | None:
    """Load and validate a logo from an HTTP(S) URL or local file path."""
    if not source:
        return None
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        content = _download_logo(source)
    elif parsed.scheme:
        raise ValueError("Site logo must be a local file or an HTTP(S) URL.")
    else:
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Site logo file does not exist: {path}")
        if path.stat().st_size > MAX_SITE_LOGO_BYTES:
            raise ValueError("Site logo must not exceed 5 MB.")
        content = path.read_bytes()
    return _validate_logo(content)


def _download_logo(url: str) -> bytes:
    content = bytearray()
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=10.0) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                if len(content) + len(chunk) > MAX_SITE_LOGO_BYTES:
                    raise ValueError("Site logo must not exceed 5 MB.")
                content.extend(chunk)
    except httpx.HTTPError as error:
        raise ValueError(f"Could not download site logo: {error}") from error
    return bytes(content)


def _validate_logo(content: bytes) -> SiteLogo:
    kind = filetype.guess(content)
    if kind is None or kind.mime not in _SUPPORTED_IMAGE_TYPES:
        raise ValueError("Site logo must be PNG, JPEG, GIF, WebP, AVIF, or ICO.")
    return SiteLogo(
        content=content,
        media_type=kind.mime,
        extension=kind.extension,
    )
