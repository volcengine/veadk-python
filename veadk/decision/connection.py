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
"""Common SystemOne endpoint and credential resolution."""

from urllib.parse import urlsplit

from .config import DecisionConfig, DecisionConfigError


def _systemone_url(api_base: str) -> str:
    """Derive the Beta System One URL from an Ark API base.

    The design inherits the region/domain/gateway prefix and appends
    ``/api/v1/systemone``; it explicitly must not produce ``/api/v3/systemone``.
    """
    base = api_base.rstrip("/")
    for suffix in ("/api/v3", "/api/v1"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return f"{base}/api/v1/systemone"


_ARK_HOST_SUFFIXES = (".volces.com", ".bytepluses.com")


def _is_ark_api_base(api_base: str) -> bool:
    """Return whether ``api_base`` is a known Ark HTTPS endpoint.

    The content-safety fallback must never derive a System One URL from an
    arbitrary model endpoint: doing so could send audited content to a
    non-Ark provider. Custom gateways must be configured explicitly through
    ``decision.api_url``.
    """
    try:
        parsed = urlsplit(api_base)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and host.startswith("ark.")
        and host.endswith(_ARK_HOST_SUFFIXES)
    )


def resolve_decision_connection(
    config: DecisionConfig,
    ark_api_base: str | None = None,
    ark_api_key: str | None = None,
) -> tuple[str, str]:
    """Resolve credentials without crossing an implicit provider boundary."""
    endpoint, explicit_key = config.api_url, config.api_key_value
    if endpoint and explicit_key:
        return endpoint, explicit_key
    if endpoint and not _is_ark_api_base(endpoint):
        raise DecisionConfigError(
            "decision.api_key is required when decision.api_url is not an Ark endpoint"
        )
    if ark_api_base is None:
        from veadk.config import settings

        ark_api_base = settings.model.api_base
    base = ark_api_base
    if not _is_ark_api_base(base):
        raise DecisionConfigError(
            "cannot derive System One connection: fallback Ark API base is not an Ark endpoint; set decision.api_url and decision.api_key explicitly"
        )
    key = explicit_key if explicit_key is not None else ark_api_key
    if key is None:
        from veadk.config import settings

        key = settings.model.api_key
    if not key:
        raise DecisionConfigError("decision API key is not configured")
    return endpoint or _systemone_url(base), key
