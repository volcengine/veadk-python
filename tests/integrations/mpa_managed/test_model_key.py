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

"""Isolated account-key discovery and safe Runtime handoff contracts."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import requests

from veadk.integrations.mpa.managed import model_key, service
from veadk.integrations.mpa.managed.config import (
    ConfigurationError,
    load_studio_profile,
)
from veadk.integrations.mpa.managed.diagnostics import diagnostic_scope


class Cloud:
    region = "cn-beijing"

    def __init__(self):
        self.count = 0

    def _credentials(self):
        self.count += 1
        return SimpleNamespace(
            access_key_id=f"test-ak-{self.count}",
            secret_access_key="test-sk",
            session_token=f"test-sts-{self.count}",
        )


def setup(monkeypatch, pages, *, raw="test-private-model-value"):
    calls = []

    def request(**kw):
        calls.append(kw)
        if kw["query"]["Action"] == "ListApiKeys":
            return {"Result": pages[kw["request_body"]["PageNumber"] - 1]}
        return {"Result": {"ApiKey": raw}}

    monkeypatch.setattr(model_key, "volcengine_signed_request", request)
    return calls


def key(identifier="1", name="mpa", **kw):
    return {"Id": identifier, "Name": name, **kw}


def test_discovery_is_account_scoped_and_only_injects_into_copy(monkeypatch):
    monkeypatch.setenv("VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY", "obsolete-other-account")
    calls = setup(monkeypatch, [{"Items": [key(Status="Active")], "TotalCount": 1}])
    profile = load_studio_profile()
    cloud = Cloud()
    selected = asyncio.run(model_key.resolve_model_key(profile, cloud))
    assert selected.values["model_api_key"] == "test-private-model-value"
    assert not profile.values.get("model_api_key")
    assert "test-private-model-value" not in str(selected.summary())
    assert "test-private-model-value" not in repr(selected)
    assert [c["query"]["Action"] for c in calls] == ["ListApiKeys", "GetRawApiKey"]
    assert calls[-1]["request_body"] == {"Id": 1, "ProjectName": "default"}
    assert calls[-1]["ak"] == "test-ak-2"
    assert calls[-1]["header"]["X-Security-Token"] == "test-sts-2"
    assert all(c["timeout"] == (10, 30) and c["region"] == cloud.region for c in calls)
    selected.values.update(pg_host="pg.example", pg_user="app", pg_password="fake")
    template = service.fresh_template(selected, "mi-123456789abc", "test-account")
    env = {row["Key"]: row["Value"] for row in template["Envs"]}
    assert env["MODEL_AGENT_API_KEY"] == "test-private-model-value"


def test_exact_selection_paginates_and_deduplicates(monkeypatch):
    monkeypatch.setenv("VEADK_MPA_ARK_API_KEY_NAME", "wanted")
    calls = setup(
        monkeypatch,
        [
            {"Items": [key(name="other")], "TotalCount": 3},
            {"Items": [key(name="other"), key("2", "wanted")], "TotalCount": 3},
            {"Items": [key("3", "last")], "TotalCount": 3},
        ],
    )
    asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))
    assert len(calls) == 4
    assert calls[-1]["request_body"]["Id"] == 2


@pytest.mark.parametrize(
    "selector", ["", "VEADK_MPA_ARK_API_KEY_NAME", "VEADK_MPA_ARK_API_KEY_ID"]
)
def test_multiple_candidates_choose_newest_unless_explicit(monkeypatch, selector):
    if selector:
        monkeypatch.setenv(selector, "2" if selector.endswith("ID") else "second")
    calls = setup(
        monkeypatch,
        [
            {
                "Items": [
                    key(CreateTime=1700000001),
                    key("2", "second", CreateTime=1700000000),
                ],
                "Total": 2,
            }
        ],
    )
    asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))
    assert calls[-1]["request_body"]["Id"] == (2 if selector else 1)


def test_newest_selection_scans_all_pages_and_filters_inactive(monkeypatch):
    calls = setup(
        monkeypatch,
        [
            {"Items": [key("90", CreateTime="2026-10-09T12:00:00Z")], "TotalCount": 4},
            {
                "Items": [
                    key("2", CreateTime="2026-10-10T12:00:00+08:00"),
                    key("3", Status="Disabled", CreateTime="2026-10-11T12:00:00Z"),
                ],
                "TotalCount": 4,
            },
            {"Items": [key("4", CreateTime="2026-10-10T03:00:00Z")], "TotalCount": 4},
        ],
    )
    asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))
    assert len(calls) == 4
    assert calls[-1]["request_body"]["Id"] == 2


@pytest.mark.parametrize("field", ["CreateTime", "CreatedAt", "CreationTime"])
@pytest.mark.parametrize(
    "latest",
    [
        1700000001,
        1700000001.5,
        "1700000001",
        1700000001000,
        "1700000001000",
        "2023-11-15T06:13:21+08:00",
    ],
)
def test_creation_time_normalizes_units_and_timezones(monkeypatch, field, latest):
    calls = setup(
        monkeypatch,
        [
            {
                "Items": [
                    key("2", CreateTime="2023-11-14T22:13:20Z"),
                    key("1", **{field: latest}),
                ],
                "TotalCount": 2,
            }
        ],
    )
    asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))
    assert calls[-1]["request_body"]["Id"] == 1


@pytest.mark.parametrize("reverse", [False, True])
def test_equal_creation_times_have_stable_selection(monkeypatch, reverse):
    items = [
        key("2", CreateTime=1700000000),
        key("3", CreateTime="2023-11-14T22:13:20Z"),
    ]
    calls = setup(
        monkeypatch,
        [{"Items": list(reversed(items)) if reverse else items, "TotalCount": 2}],
    )
    asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))
    assert calls[-1]["request_body"]["Id"] == 3


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "private-invalid-value",
        True,
        -1,
        0,
        "NaN",
        float("inf"),
        10**100,
        "2026-10-10T12:00:00",
        {},
        [],
    ],
)
def test_unknown_creation_time_fails_without_raw_lookup(monkeypatch, value):
    calls = setup(
        monkeypatch,
        [
            {
                "Items": [key(CreateTime=1700000000), key("2", CreateTime=value)],
                "TotalCount": 2,
            }
        ],
    )
    with pytest.raises(model_key.ModelKeyError, match="creation time") as error:
        asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))
    assert "private-invalid-value" not in str(error.value)
    assert len(calls) == 1


def test_missing_creation_time_fails_without_raw_lookup(monkeypatch):
    calls = setup(
        monkeypatch,
        [{"Items": [key(), key("2", CreateTime=1700000000)], "TotalCount": 2}],
    )
    with pytest.raises(model_key.ModelKeyError, match="creation time"):
        asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))
    assert len(calls) == 1


@pytest.mark.parametrize(
    "items", [[], [key(Status="Restricted")], [key(Status="Disabled")]]
)
def test_missing_or_inactive_keys_fail_without_raw_lookup(monkeypatch, items):
    calls = setup(monkeypatch, [{"Items": items, "TotalCount": len(items)}])
    with pytest.raises(model_key.ModelKeyError, match="No matching"):
        asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))
    assert len(calls) == 1


@pytest.mark.parametrize(
    "page",
    [
        {"Items": None, "TotalCount": 1},
        {"Items": [], "TotalCount": 1},
        {"Items": [key()], "TotalCount": "1"},
        {"Items": [{}], "TotalCount": 1},
        {"Items": [key()], "TotalCount": 0},
    ],
)
def test_malformed_pages_fail_closed(monkeypatch, page):
    calls = setup(monkeypatch, [page])
    with pytest.raises(model_key.ModelKeyError):
        asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))
    assert len(calls) == 1


def test_empty_raw_key_never_uses_masked_list_value(monkeypatch):
    setup(monkeypatch, [{"Items": [key(Key="masked***")], "TotalCount": 1}], raw="")
    with pytest.raises(model_key.ModelKeyError):
        asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))


def test_transient_retries_are_bounded_and_redacted(monkeypatch, caplog):
    count = 0

    def request(**kw):
        nonlocal count
        count += 1
        raise requests.ConnectionError("test-private-model-value")

    monkeypatch.setattr(model_key, "volcengine_signed_request", request)
    sleep = AsyncMock()
    monkeypatch.setattr(model_key.asyncio, "sleep", sleep)
    events = []
    with diagnostic_scope(events.append):
        with pytest.raises(model_key.ModelKeyError) as error:
            asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))
    assert count == 3
    assert sleep.await_count == 2
    assert [x["outcome"] for x in events] == ["retrying", "retrying", "failed"]
    assert "test-private-model-value" not in str(error.value) + caplog.text + str(
        events
    )
    assert error.value.__cause__ is None


def test_permission_error_is_not_retried_or_echoed(monkeypatch):
    calls = []

    def request(**kw):
        calls.append(kw)
        return {
            "ResponseMetadata": {
                "Error": {"Code": "AccessDenied", "Message": "private-test-value"}
            }
        }

    monkeypatch.setattr(model_key, "volcengine_signed_request", request)
    with pytest.raises(model_key.ModelKeyError, match="permissions") as error:
        asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))
    assert "private-test-value" not in str(error.value)
    assert len(calls) == 1


def test_account_change_stops_before_raw_key_read(monkeypatch):
    calls = setup(monkeypatch, [{"Items": [key()], "TotalCount": 1}])
    cloud = Cloud()
    credentials = cloud._credentials

    def refresh():
        if cloud.count:
            raise RuntimeError("Cloud credentials changed accounts; private-test-value")
        return credentials()

    monkeypatch.setattr(cloud, "_credentials", refresh)
    with pytest.raises(model_key.ModelKeyError):
        asyncio.run(model_key.resolve_model_key(load_studio_profile(), cloud))
    assert len(calls) == 1


def test_cancellation_stops_before_raw_read(monkeypatch):
    async def run():
        started, release = threading.Event(), threading.Event()
        calls = []

        def request(**kw):
            calls.append(kw)
            started.set()
            release.wait(2)
            return {"Result": {"Items": [key()], "TotalCount": 1}}

        monkeypatch.setattr(model_key, "volcengine_signed_request", request)
        task = asyncio.create_task(
            model_key.resolve_model_key(load_studio_profile(), Cloud())
        )
        await asyncio.to_thread(started.wait, 2)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(calls) == 1

    asyncio.run(run())


def test_model_failure_precedes_any_resource_mutation(monkeypatch):
    profile = load_studio_profile()
    cloud = Cloud()
    monkeypatch.setattr(
        cloud, "account_id", AsyncMock(return_value="test-account"), raising=False
    )
    monkeypatch.setattr(service, "RuntimeCloud", lambda **kw: cloud)
    resolve = AsyncMock(side_effect=model_key.ModelKeyError("No matching Ark API key"))
    monkeypatch.setattr(service, "resolve_model_key", resolve)
    iam, identity = AsyncMock(), AsyncMock()
    monkeypatch.setattr(service, "ensure_runtime_role", iam)
    monkeypatch.setattr(service, "ensure_workload_identity", identity)
    with pytest.raises(model_key.ModelKeyError):
        asyncio.run(service.provision(profile, agent_id="mi-test", owner="test-owner"))
    resolve.assert_awaited_once_with(profile, cloud)
    iam.assert_not_awaited()
    identity.assert_not_awaited()


def test_selectors_are_nonsecret_and_exclusive(monkeypatch):
    monkeypatch.setenv("VEADK_MPA_ARK_API_KEY_ID", "1")
    monkeypatch.setenv("VEADK_MPA_ARK_API_KEY_NAME", "wanted")
    with pytest.raises(ConfigurationError):
        load_studio_profile()


def test_duplicate_names_and_missing_selector_do_not_pick_first(monkeypatch):
    monkeypatch.setenv("VEADK_MPA_ARK_API_KEY_NAME", "same")
    calls = setup(
        monkeypatch, [{"Items": [key("1", "same"), key("2", "same")], "TotalCount": 2}]
    )
    with pytest.raises(model_key.ModelKeyError, match="multiple"):
        asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))
    assert len(calls) == 1
    monkeypatch.setenv("VEADK_MPA_ARK_API_KEY_NAME", "missing")
    with pytest.raises(model_key.ModelKeyError, match="No matching"):
        asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))


def test_read_recovers_and_refreshes_credentials(monkeypatch):
    attempts = []

    def request(**kw):
        attempts.append(kw)
        if len(attempts) == 1:
            return {
                "ResponseMetadata": {
                    "Error": {"Code": "Throttling", "Message": "private"}
                }
            }
        if kw["query"]["Action"] == "ListApiKeys":
            return {"Result": {"Items": [key()], "TotalCount": 1}}
        return {"Result": {"ApiKey": "test-model-value"}}

    monkeypatch.setattr(model_key, "volcengine_signed_request", request)
    monkeypatch.setattr(model_key.asyncio, "sleep", AsyncMock())
    selected = asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))
    assert selected.values["model_api_key"] == "test-model-value"
    assert [x["ak"] for x in attempts] == ["test-ak-1", "test-ak-2", "test-ak-3"]


def test_discovery_has_a_page_limit(monkeypatch):
    calls = []

    def request(**kw):
        calls.append(kw)
        page = kw["request_body"]["PageNumber"]
        return {"Result": {"Items": [key(str(page * 100 + i)) for i in range(100)]}}

    monkeypatch.setattr(model_key, "volcengine_signed_request", request)
    with pytest.raises(model_key.ModelKeyError, match="limit"):
        asyncio.run(model_key.resolve_model_key(load_studio_profile(), Cloud()))
    assert len(calls) == 100


@pytest.mark.parametrize(
    "update",
    [
        {"model-api-key": "test-value"},
        {"model-provider": "other"},
        {"model-api-base": "https://untrusted.example"},
        {"managed": {"runtime": {"env": {"MODEL_AGENT_API_KEY": "test-value"}}}},
        {"managed": {"from-runtime": "r-source"}},
    ],
)
def test_ark_configuration_rejects_secret_or_target_overrides(monkeypatch, update):
    from veadk.integrations.mpa.managed import config

    values = config.studio_profile_values()
    if "managed" in update:
        for name, value in update["managed"].items():
            if isinstance(value, dict):
                values["managed"][name].update(value)
            else:
                values["managed"][name] = value
    else:
        values.update(update)
    monkeypatch.setattr(config, "studio_profile_values", lambda: values)
    with pytest.raises(ConfigurationError):
        load_studio_profile()


def test_explicit_mode_never_queries_ark(monkeypatch):
    profile = load_studio_profile()
    profile.managed.model_key.mode = "explicit"
    profile.values["model_api_key"] = "explicit-test-value"
    monkeypatch.setattr(
        model_key,
        "volcengine_signed_request",
        lambda **kw: pytest.fail("Unexpected Ark call"),
    )
    assert asyncio.run(model_key.resolve_model_key(profile, Cloud())) is profile


def test_studio_role_already_grants_ark_read_permissions():
    from veadk.cli.frontend_deploy_policy import FRONTEND_DEPLOY_POLICY

    actions = {
        action
        for statement in FRONTEND_DEPLOY_POLICY["Statement"]
        for action in statement["Action"]
    }
    assert {"ark:ListApiKeys", "ark:GetRawApiKey"} <= actions
