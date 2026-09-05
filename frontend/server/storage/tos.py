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

"""Reusable TOS client composition for Studio-owned persistent data."""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from typing import Any

from veadk.utils.logger import get_logger

from . import StudioStorageConfig

CredentialResolver = Callable[[], tuple[str, str, str | None]]
TosClientFactory = Callable[[], Any]

_PUBLIC_ENDPOINT_PROBE_TIMEOUT_SECONDS = 3
logger = get_logger(__name__)


def _endpoint_candidates(config: StudioStorageConfig) -> tuple[str, ...]:
    """Return safe endpoint candidates without overriding custom endpoints."""
    public_endpoint = f"tos-{config.region}.volces.com"
    if config.provider == "volcengine" and config.endpoint == public_endpoint:
        return public_endpoint, f"tos-{config.region}.ivolces.com"
    return (config.endpoint,)


def _new_client(
    tos_module: Any,
    *,
    endpoint: str,
    region: str,
    access_key: str,
    secret_key: str,
    session_token: str | None,
    probe: bool = False,
) -> Any:
    options: dict[str, Any] = {
        "ak": access_key,
        "sk": secret_key,
        "security_token": session_token,
        "endpoint": endpoint,
        "region": region,
    }
    client = tos_module.TosClientV2(**options)
    if probe:
        # Endpoint selection should not inherit the SDK's three retries and turn
        # a predictable private-network fallback into a long cold-start delay.
        client.max_retry_count = 0
        client.connection_time = _PUBLIC_ENDPOINT_PROBE_TIMEOUT_SECONDS
    return client


def _is_network_error(error: Exception, tos_module: Any) -> bool:
    """Return whether the SDK error represents a transport failure."""
    client_error = getattr(
        getattr(tos_module, "exceptions", None),
        "TosClientError",
        None,
    )
    if client_error is None or not isinstance(error, client_error):
        return False
    try:
        import requests
    except ImportError:
        return False
    return isinstance(
        getattr(error, "cause", None),
        requests.exceptions.RequestException,
    )


def create_tos_client_factory(
    config: StudioStorageConfig,
    resolve_credentials: CredentialResolver,
) -> TosClientFactory:
    """Create clients lazily and select a reachable Volcengine endpoint once."""
    if not config.configured:
        raise ValueError(config.unavailable_reason)

    candidates = _endpoint_candidates(config)
    selected_endpoint = candidates[0] if len(candidates) == 1 else ""
    selection_lock = Lock()

    def factory() -> Any:
        nonlocal selected_endpoint
        import tos

        access_key, secret_key, session_token = resolve_credentials()
        if not selected_endpoint:
            with selection_lock:
                if not selected_endpoint:
                    public_endpoint = candidates[0]
                    intranet_endpoint = f"tos-{config.region}.ivolces.com"
                    probe = _new_client(
                        tos,
                        endpoint=public_endpoint,
                        region=config.region,
                        access_key=access_key,
                        secret_key=secret_key,
                        session_token=session_token,
                        probe=True,
                    )
                    head_bucket = getattr(probe, "head_bucket", None)
                    if not callable(head_bucket):
                        selected_endpoint = public_endpoint
                    else:
                        try:
                            head_bucket(bucket=config.bucket)
                        except Exception as error:
                            tos_exceptions = getattr(tos, "exceptions", None)
                            expected_errors = tuple(
                                error_type
                                for error_type in (
                                    getattr(tos_exceptions, "TosClientError", None),
                                    getattr(tos_exceptions, "TosServerError", None),
                                )
                                if isinstance(error_type, type)
                            )
                            if not expected_errors or not isinstance(
                                error, expected_errors
                            ):
                                raise
                            if not _is_network_error(error, tos):
                                selected_endpoint = public_endpoint
                            else:
                                selected_endpoint = intranet_endpoint
                                logger.warning(
                                    "Studio TOS public endpoint %s is unreachable; "
                                    "using intranet endpoint %s.",
                                    public_endpoint,
                                    intranet_endpoint,
                                )
                        else:
                            selected_endpoint = public_endpoint

        return _new_client(
            tos,
            endpoint=selected_endpoint,
            region=config.region,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
        )

    return factory


__all__ = [
    "CredentialResolver",
    "TosClientFactory",
    "create_tos_client_factory",
]
