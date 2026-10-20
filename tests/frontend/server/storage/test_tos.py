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

import sys
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest

import requests

from frontend.server.storage import StudioStorageConfig
from frontend.server.storage.tos import create_tos_client_factory


class _TosClientError(Exception):
    def __init__(self, cause: Exception | None = None) -> None:
        self.cause = cause


class _TosServerError(Exception):
    pass


def _config(provider: str = "volcengine") -> StudioStorageConfig:
    region = "cn-beijing" if provider == "volcengine" else "ap-southeast-1"
    domain = "volces.com" if provider == "volcengine" else "bytepluses.com"
    return StudioStorageConfig(
        provider=provider,  # type: ignore[arg-type]
        bucket="studio",
        region=region,
        endpoint=f"tos-{region}.{domain}",
    )


def test_factory_falls_back_to_volcengine_intranet_on_public_network_error(
    monkeypatch,
) -> None:
    created: list[dict[str, object]] = []
    probes: list[tuple[str, int, int]] = []

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            self.endpoint = str(kwargs["endpoint"])
            self.max_retry_count = 3
            self.connection_time = 10
            created.append(kwargs)

        def head_bucket(self, *, bucket: str) -> None:
            assert bucket == "studio"
            probes.append((self.endpoint, self.max_retry_count, self.connection_time))
            if self.endpoint.endswith(".volces.com"):
                raise _TosClientError(requests.ConnectionError("no public route"))

    monkeypatch.setitem(
        sys.modules,
        "tos",
        SimpleNamespace(
            TosClientV2=_Client,
            exceptions=SimpleNamespace(
                TosClientError=_TosClientError,
                TosServerError=_TosServerError,
            ),
        ),
    )
    factory = create_tos_client_factory(_config(), lambda: ("ak", "sk", "token"))

    first = factory()
    second = factory()

    assert first is not second
    assert first.endpoint == "tos-cn-beijing.ivolces.com"
    assert second.endpoint == "tos-cn-beijing.ivolces.com"
    assert probes == [("tos-cn-beijing.volces.com", 0, 3)]


def test_factory_keeps_public_endpoint_when_tos_returns_a_server_error(
    monkeypatch,
) -> None:
    probes: list[str] = []

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            self.endpoint = str(kwargs["endpoint"])

        def head_bucket(self, *, bucket: str) -> None:
            assert bucket == "studio"
            probes.append(self.endpoint)
            raise _TosServerError("AccessDenied")

    monkeypatch.setitem(
        sys.modules,
        "tos",
        SimpleNamespace(
            TosClientV2=_Client,
            exceptions=SimpleNamespace(
                TosClientError=_TosClientError,
                TosServerError=_TosServerError,
            ),
        ),
    )

    client = create_tos_client_factory(_config(), lambda: ("ak", "sk", None))()

    assert client.endpoint == "tos-cn-beijing.volces.com"
    assert probes == ["tos-cn-beijing.volces.com"]


def test_factory_keeps_public_endpoint_for_non_network_client_errors(
    monkeypatch,
) -> None:
    class _Client:
        def __init__(self, **kwargs: object) -> None:
            self.endpoint = str(kwargs["endpoint"])

        def head_bucket(self, *, bucket: str) -> None:
            assert bucket == "studio"
            raise _TosClientError(ValueError("invalid request"))

    monkeypatch.setitem(
        sys.modules,
        "tos",
        SimpleNamespace(
            TosClientV2=_Client,
            exceptions=SimpleNamespace(
                TosClientError=_TosClientError,
                TosServerError=_TosServerError,
            ),
        ),
    )

    client = create_tos_client_factory(_config(), lambda: ("ak", "sk", None))()

    assert client.endpoint == "tos-cn-beijing.volces.com"


def test_factory_does_not_probe_or_infer_an_intranet_endpoint_for_byteplus(
    monkeypatch,
) -> None:
    created: list[dict[str, object]] = []

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            self.endpoint = str(kwargs["endpoint"])
            created.append(kwargs)

        def head_bucket(self, *, bucket: str) -> None:
            raise AssertionError(f"unexpected probe for {bucket}")

    monkeypatch.setitem(
        sys.modules,
        "tos",
        SimpleNamespace(
            TosClientV2=_Client,
            exceptions=SimpleNamespace(
                TosClientError=_TosClientError,
                TosServerError=_TosServerError,
            ),
        ),
    )

    client = create_tos_client_factory(
        _config("byteplus"), lambda: ("ak", "sk", None)
    )()

    assert client.endpoint == "tos-ap-southeast-1.bytepluses.com"
    assert len(created) == 1


def test_factory_preserves_a_custom_volcengine_endpoint(monkeypatch) -> None:
    created: list[dict[str, object]] = []

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            self.endpoint = str(kwargs["endpoint"])
            created.append(kwargs)

        def head_bucket(self, *, bucket: str) -> None:
            raise AssertionError(f"unexpected probe for {bucket}")

    monkeypatch.setitem(
        sys.modules,
        "tos",
        SimpleNamespace(
            TosClientV2=_Client,
            exceptions=SimpleNamespace(
                TosClientError=_TosClientError,
                TosServerError=_TosServerError,
            ),
        ),
    )
    config = StudioStorageConfig(
        provider="volcengine",
        bucket="studio",
        region="cn-beijing",
        endpoint="tos.example.com",
    )

    client = create_tos_client_factory(config, lambda: ("ak", "sk", None))()

    assert client.endpoint == "tos.example.com"
    assert len(created) == 1


@pytest.mark.parametrize("changed_index", [0, 1, 2])
def test_cached_factory_reuses_clients_and_rotates_full_credentials(
    monkeypatch: pytest.MonkeyPatch,
    changed_index: int,
) -> None:
    from frontend.server.storage.tos import create_cached_tos_client_factory

    created: list[dict[str, object]] = []
    probes: list[str] = []
    credentials = ["access-1", "secret-1", "session-1"]
    resolved = 0

    class Client:
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)
            self.endpoint = str(kwargs["endpoint"])

        def head_bucket(self, *, bucket: str) -> None:
            probes.append(bucket)
            raise _TosClientError(requests.ConnectionError("no public route"))

    def resolve() -> tuple[str, str, str | None]:
        nonlocal resolved
        resolved += 1
        return credentials[0], credentials[1], credentials[2]

    monkeypatch.setitem(
        sys.modules,
        "tos",
        SimpleNamespace(
            TosClientV2=Client,
            exceptions=SimpleNamespace(
                TosClientError=_TosClientError, TosServerError=_TosServerError
            ),
        ),
    )
    factory = create_cached_tos_client_factory(_config(), resolve)
    first = factory()
    assert factory() is first
    credentials[changed_index] += "-rotated"
    second = factory()
    assert second is not first
    assert factory() is second
    assert resolved == 4
    assert probes == ["studio"]
    assert len(created) == 3  # One endpoint probe, then one client per credential set
    assert created[-1]["ak"] == credentials[0]
    assert created[-1]["sk"] == credentials[1]
    assert created[-1]["security_token"] == credentials[2]
    assert second.endpoint == "tos-cn-beijing.ivolces.com"


@pytest.mark.parametrize("failure", ["resolver", "empty-credentials", "constructor"])
def test_cached_factory_invalidates_old_client_after_failure(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    from frontend.server.storage.tos import create_cached_tos_client_factory

    failed = False

    class Client:
        def __init__(self, **kwargs: object) -> None:
            if failed and failure == "constructor":
                raise RuntimeError("client construction failed")

    def resolve() -> tuple[str, str, str | None]:
        if failed:
            if failure == "resolver":
                raise RuntimeError("role credentials unavailable")
            if failure == "empty-credentials":
                return "", "", None
            return "access", "secret", "rotated-session"
        return "access", "secret", "session"

    monkeypatch.setitem(sys.modules, "tos", SimpleNamespace(TosClientV2=Client))
    factory = create_cached_tos_client_factory(_config("byteplus"), resolve)
    first = factory()
    failed = True
    with pytest.raises((RuntimeError, ValueError)):
        factory()
    failed = False
    recovered = factory()
    assert recovered is not first
    assert factory() is recovered


def test_cached_factory_shares_one_client_across_concurrent_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from frontend.server.storage.tos import create_cached_tos_client_factory

    resolved: list[bool] = []
    created: list[object] = []

    class Client:
        def __init__(self, **kwargs: object) -> None:
            created.append(self)

    def resolve() -> tuple[str, str, str | None]:
        resolved.append(True)
        return "access", "secret", "session"

    monkeypatch.setitem(sys.modules, "tos", SimpleNamespace(TosClientV2=Client))
    factory = create_cached_tos_client_factory(_config("byteplus"), resolve)
    with ThreadPoolExecutor(max_workers=8) as executor:
        clients = list(executor.map(lambda _: factory(), range(16)))
    assert len(created) == 1
    assert len(resolved) == 16
    assert all(client is created[0] for client in clients)
