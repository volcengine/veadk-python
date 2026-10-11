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

"""Tests for VeFaaS.deploy_image key-auth extension (FR-3, VC-4/VC-5/AC-10)."""

from unittest.mock import MagicMock

import pytest

from veadk.integrations.ve_faas.ve_faas import VeFaaS


def _make_vefaas() -> VeFaaS:
    """Build a VeFaaS without running __init__ (no cloud credentials needed)."""
    fake = object.__new__(VeFaaS)
    fake.region = "cn-beijing"
    fake.apig_client = MagicMock()
    return fake


def _stub_deploy_internals(
    fake: VeFaaS,
    monkeypatch: pytest.MonkeyPatch,
    *,
    created_kwargs: dict,
) -> None:
    """Stub the cloud-touching internals of deploy_image."""
    monkeypatch.setattr(fake, "query_user_cr_vpc_tunnel", lambda registry: True)
    monkeypatch.setattr(
        fake,
        "_create_image_function",
        lambda function_name, image: (function_name, "function-id"),
    )

    def _create_application(*args, **kwargs):
        created_kwargs["args"] = args
        created_kwargs["kwargs"] = kwargs
        return "app-id"

    monkeypatch.setattr(fake, "_create_application", _create_application)
    monkeypatch.setattr(
        fake, "_release_application", lambda app_id: "https://app.example.com"
    )
    monkeypatch.setattr(
        fake, "ensure_application_route_methods", lambda app_id, **kw: True
    )


def test_deploy_image_compat_returns_three_tuple_without_key_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-10: without enable_key_auth, deploy_image keeps its 3-tuple and no key auth."""
    fake = _make_vefaas()
    created: dict = {}
    _stub_deploy_internals(fake, monkeypatch, created_kwargs=created)

    # Guard: key retrieval / route lookup must not run in the default path.
    def _fail_route(*args, **kwargs):
        raise AssertionError("get_application_route must not run without key auth")

    monkeypatch.setattr(fake, "get_application_route", _fail_route)

    result = VeFaaS.deploy_image(
        fake,
        "mpa-agent",
        "registry.example.com/mpa:latest",
        "registry",
        gateway_name="gw",
        gateway_service_name="svc",
        gateway_upstream_name="us",
    )

    assert result == ("https://app.example.com", "app-id", "function-id")
    assert len(result) == 3
    assert created["kwargs"].get("enable_key_auth", False) is False


def test_deploy_image_with_key_auth_returns_gateway_and_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VC-4: enable_key_auth deploy captures gateway id and key-auth API key."""
    fake = _make_vefaas()
    created: dict = {}
    _stub_deploy_internals(fake, monkeypatch, created_kwargs=created)

    monkeypatch.setattr(
        fake,
        "get_application_route",
        lambda app_id=None, app_name=None: ("gw-123", "svc-1", "route-1"),
    )
    captured_gateway: dict = {}

    def _get_key(gateway_id):
        captured_gateway["gateway_id"] = gateway_id
        return "runtime-api-key-xyz"

    monkeypatch.setattr(fake, "_get_key_auth_api_key", _get_key)

    result = VeFaaS.deploy_image(
        fake,
        "mpa-agent",
        "registry.example.com/mpa:latest",
        "registry",
        gateway_name="gw",
        gateway_service_name="svc",
        gateway_upstream_name="us",
        enable_key_auth=True,
    )

    assert result == (
        "https://app.example.com",
        "app-id",
        "function-id",
        "gw-123",
        "runtime-api-key-xyz",
    )
    assert created["kwargs"].get("enable_key_auth") is True
    assert captured_gateway["gateway_id"] == "gw-123"


def test_deploy_image_key_auth_missing_key_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VC-4 negative: requesting key auth but resolving no key fails clearly."""
    fake = _make_vefaas()
    created: dict = {}
    _stub_deploy_internals(fake, monkeypatch, created_kwargs=created)
    monkeypatch.setattr(
        fake,
        "get_application_route",
        lambda app_id=None, app_name=None: ("gw-123", "svc-1", "route-1"),
    )
    monkeypatch.setattr(fake, "_get_key_auth_api_key", lambda gateway_id: "")

    with pytest.raises(ValueError, match="key"):
        VeFaaS.deploy_image(
            fake,
            "mpa-agent",
            "registry.example.com/mpa:latest",
            "registry",
            gateway_name="gw",
            gateway_service_name="svc",
            gateway_upstream_name="us",
            enable_key_auth=True,
        )
