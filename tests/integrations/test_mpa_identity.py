"""Tests for idempotent Studio workload identity provisioning."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from volcenginesdkcore.rest import ApiException

from veadk.integrations.mpa.mpa_identity import (
    MpaIdentityError,
    ensure_studio_workload_identity,
)
from veadk.integrations.ve_identity.identity_client import IdentityClient


class FakeIdentityClient:
    def __init__(self, *, pool_exists: bool = False, identity_exists: bool = False):
        self.pool_exists = pool_exists
        self.identity_exists = identity_exists
        self.calls: list[tuple[str, object]] = []
        self.pool_create_error: Exception | None = None

    def get_workload_pool(self, *, workload_pool_name: str):
        self.calls.append(("get_pool", workload_pool_name))
        if not self.pool_exists:
            raise ApiException(status=404, reason="NotFound")
        return SimpleNamespace(workload_pool_name=workload_pool_name)

    def create_workload_pool(self, *, workload_pool_name: str):
        self.calls.append(("create_pool", workload_pool_name))
        if self.pool_create_error:
            raise self.pool_create_error
        self.pool_exists = True
        return SimpleNamespace(workload_pool_name=workload_pool_name)

    def get_workload_identity(self, *, workload_pool_name: str, name: str):
        self.calls.append(("get_identity", (workload_pool_name, name)))
        if not self.identity_exists:
            raise ApiException(status=404, reason="NotFound")
        return SimpleNamespace(name=name, workload_pool_name=workload_pool_name)

    def create_workload_identity(self, *, workload_pool_name: str, name: str):
        self.calls.append(("create_identity", (workload_pool_name, name)))
        self.identity_exists = True
        return SimpleNamespace(name=name, workload_pool_name=workload_pool_name)


def test_ensure_studio_workload_identity_creates_missing_resources() -> None:
    client = FakeIdentityClient()

    result = ensure_studio_workload_identity(client, "mi-abc123def456")

    assert result.workload_pool_name == "agentkit-studio-workload"
    assert result.workload_identity_name == "mi-abc123def456-studio"
    assert result.pool_created is True
    assert result.identity_created is True
    assert [call[0] for call in client.calls] == [
        "get_pool",
        "create_pool",
        "get_identity",
        "create_identity",
    ]


def test_ensure_studio_workload_identity_reuses_existing_resources() -> None:
    client = FakeIdentityClient(pool_exists=True, identity_exists=True)

    result = ensure_studio_workload_identity(client, "mi-abc123def456")

    assert result.pool_created is False
    assert result.identity_created is False
    assert [call[0] for call in client.calls] == ["get_pool", "get_identity"]


def test_ensure_studio_workload_identity_rereads_after_create_conflict() -> None:
    client = FakeIdentityClient()
    client.pool_create_error = ApiException(status=409, reason="AlreadyExists")

    original_create = client.create_workload_pool

    def concurrent_create(*, workload_pool_name: str):
        client.pool_exists = True
        return original_create(workload_pool_name=workload_pool_name)

    client.create_workload_pool = concurrent_create  # type: ignore[method-assign]

    result = ensure_studio_workload_identity(client, "mi-abc123def456")

    assert result.pool_created is False
    assert [call[0] for call in client.calls[:3]] == [
        "get_pool",
        "create_pool",
        "get_pool",
    ]


def test_ensure_studio_workload_identity_reports_create_permission() -> None:
    client = FakeIdentityClient()
    client.pool_create_error = ApiException(status=403, reason="AccessDenied")

    with pytest.raises(MpaIdentityError, match="id:CreateWorkloadPool"):
        ensure_studio_workload_identity(client, "mi-abc123def456")


def test_ensure_studio_workload_identity_fails_if_conflict_cannot_be_read() -> None:
    client = FakeIdentityClient()
    client.pool_create_error = ApiException(status=409, reason="AlreadyExists")

    with pytest.raises(MpaIdentityError, match="after a concurrent create"):
        ensure_studio_workload_identity(client, "mi-abc123def456")


def test_ensure_studio_workload_identity_fails_closed_on_access_denied() -> None:
    client = FakeIdentityClient()

    def denied(*, workload_pool_name: str):
        raise ApiException(status=403, reason="AccessDenied")

    client.get_workload_pool = denied  # type: ignore[method-assign]

    with pytest.raises(MpaIdentityError, match="agentkit-studio-workload"):
        ensure_studio_workload_identity(client, "mi-abc123def456")
    assert not any(call[0].endswith("identity") for call in client.calls)


def test_identity_client_maps_pool_scoped_sdk_requests() -> None:
    client = IdentityClient(
        access_key="ak",
        secret_key="sk",
        session_token="token",
        region="cn-beijing",
        enable_vefaas_iam_fallback=False,
    )
    api = Mock()
    api.api_client.configuration = SimpleNamespace()
    client._api_client = api

    client.get_workload_pool(workload_pool_name="pool")
    client.create_workload_pool(workload_pool_name="pool")
    client.get_workload_identity(workload_pool_name="pool", name="identity")
    client.create_workload_identity(workload_pool_name="pool", name="identity")

    assert api.get_workload_pool.call_args.args[0].workload_pool_name == "pool"
    assert api.create_workload_pool.call_args.args[0].workload_pool_name == "pool"
    get_identity = api.get_workload_identity.call_args.args[0]
    assert (get_identity.workload_pool_name, get_identity.name) == (
        "pool",
        "identity",
    )
    create_identity = api.create_workload_identity.call_args.args[0]
    assert (create_identity.workload_pool_name, create_identity.name) == (
        "pool",
        "identity",
    )
