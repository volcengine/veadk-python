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

"""Stable deployment-level signing keys for Studio knowledge metadata."""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Mapping

STUDIO_KNOWLEDGE_SIGNING_KEY_ENV = "VEADK_STUDIO_KNOWLEDGE_SIGNING_KEY"


def studio_knowledge_signing_namespace(*parts: str) -> str:
    """Build an unambiguous namespace for one Studio deployment."""
    return "\0".join(parts)


def resolve_studio_knowledge_signing_key(
    environment: Mapping[str, object],
    *,
    seed: str = "",
    namespace: str = "",
) -> str:
    """Preserve an existing key or create a stable key for one deployment."""
    existing = str(environment.get(STUDIO_KNOWLEDGE_SIGNING_KEY_ENV) or "").strip()
    if existing:
        return existing
    if seed:
        context = f"veadk-studio-knowledge-signing-v1\0{namespace}".encode()
        return hmac.new(seed.encode(), context, "sha256").hexdigest()
    return secrets.token_urlsafe(32)


__all__ = [
    "STUDIO_KNOWLEDGE_SIGNING_KEY_ENV",
    "resolve_studio_knowledge_signing_key",
    "studio_knowledge_signing_namespace",
]
