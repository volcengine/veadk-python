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

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest


@pytest.fixture
def mod():
    path = (
        Path(__file__).resolve().parents[1]
        / "veadk/tools/builtin_tools/agentsentry_v3.py"
    )
    spec = importlib.util.spec_from_file_location("transport", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def client(mod):
    return mod.AgentSentryV3(
        "http://localhost:8444" + mod.PATH,
        account_id="account",
        instance_id="instance",
        access_key="endpoint",
        secret_key="secret",
    )


@pytest.mark.parametrize(
    "result,expected",
    [
        ({"Degraded": False, "Decision": {"DecisionType": 1}}, None),
        ({"Degraded": False, "Decision": {"DecisionType": 2}}, "BLOCK"),
        ({"Decision": {"DecisionType": 1}}, None),
        ({"Degraded": "false", "Decision": {"DecisionType": 1}}, None),
        ({"Degraded": False, "Decision": {"DecisionType": 4}}, None),
        ({"Degraded": False, "Decision": {"DecisionType": True}}, None),
        ({"Degraded": True}, None),
        ({"Decision": {"DecisionType": 2}}, "BLOCK"),
        ({"Decision": {"DecisionType": 0}}, None),
        ({"Decision": {"DecisionType": 3}}, None),
        ({"Decision": {"DecisionType": 99}}, None),
        ({"Decision": {"DecisionType": None}}, None),
        ({"Decision": {"DecisionType": "unknown"}}, None),
        ({"Decision": {"DecisionType": "2"}}, "BLOCK"),
        ({"Decision": {"DecisionType": 2.0}}, "BLOCK"),
    ],
)
def test_decisions(mod, result, expected):
    response = SimpleNamespace(status_code=200, json=lambda: {"Result": result})
    with patch.object(mod.requests, "post", return_value=response) as post:
        value = client(mod).moderate(
            "actual plan",
            role="assistant",
            hook_name="before_tool_call",
            session_info={"SessionID": "session", "RunID": "run"},
            tool_calls=[{"ID": "call"}],
        )
        assert value == (getattr(mod, expected) if expected else None)
        request = post.call_args
        body = json.loads(request.kwargs["data"])
        assert body["SessionID"] == "session"
        assert body["SessionInfo"]["MessageID"]
        assert body["Message"]["ToolCall"] == [{"ID": "call"}]
        assert body["Message"]["MultiPart"][0]["Content"] == "actual plan"
        assert "Version=2025-01-01" in request.args[0]
        assert "clawsentry/request" in request.kwargs["headers"]["Authorization"]
        assert request.kwargs["allow_redirects"] is False


@pytest.mark.parametrize(
    "action,decision,expected",
    [
        ("pass_and_writeback", 1, None),
        ("pass_and_writeback", 2, "BLOCK"),
        ("block_and_writeback", 1, None),
        ("block_and_writeback", 2, "BLOCK"),
        (None, 1, None),
        ("unknown", 1, None),
        ("pass_and_writeback", 4, None),
    ],
)
def test_decision_takes_precedence_over_degraded_action(
    mod, action, decision, expected
):
    result = {
        "Decision": {"DecisionType": decision},
        "Degraded": True,
    }
    if action is not None:
        result["DegradeAction"] = action
    response = SimpleNamespace(status_code=200, json=lambda: {"Result": result})
    with patch.object(mod.requests, "post", return_value=response):
        value = client(mod).moderate("hello", role="user", hook_name="before_dispatch")
    assert value == (getattr(mod, expected) if expected else None)


def test_missing_plan_and_wrong_hook(mod):
    with patch.object(mod.requests, "post") as post:
        assert (
            client(mod).moderate("", role="assistant", hook_name="before_tool_call")
            == mod.MISSING_PLAN
        )
        with pytest.raises(ValueError):
            client(mod).moderate("reply", role="assistant", hook_name="after_model")
        post.assert_not_called()


def test_timeout(mod):
    with patch.object(mod.requests, "post", side_effect=mod.requests.Timeout):
        assert (
            client(mod).moderate("hello", role="user", hook_name="before_dispatch")
            == mod.UNAVAILABLE
        )


@pytest.mark.parametrize("status,api_error", [(503, False), (200, True)])
def test_service_errors_do_not_become_allow(mod, status, api_error):
    response = SimpleNamespace(
        status_code=status,
        json=lambda: {
            "ResponseMetadata": {"Error": {"Code": "ServiceUnavailable"}}
            if api_error
            else {},
            "Result": {"Decision": {"DecisionType": 1}},
        },
    )
    with patch.object(mod.requests, "post", return_value=response):
        assert (
            client(mod).moderate("hello", role="user", hook_name="before_dispatch")
            == mod.UNAVAILABLE
        )


@pytest.mark.parametrize(
    "scheme,port", [("http", ":80"), ("https", ":443"), ("http", ":8444")]
)
def test_official_signer_default_ports(mod, scheme, port):
    from volcengine.base.Request import Request
    from volcengine.Credentials import Credentials

    c = mod.AgentSentryV3(
        scheme + "://sentry" + port + mod.PATH,
        account_id="account",
        instance_id="instance",
        access_key="endpoint",
        secret_key="secret",
    )
    body = b'{"test":"value"}'
    expected = Request()
    expected.set_schema(scheme)
    expected.set_host("sentry" + port)
    expected.set_path(mod.PATH)
    expected.set_method("POST")
    expected.set_query({"Version": "2025-01-01"})
    expected.set_headers(
        {
            "Content-Type": "application/json",
            "Host": "sentry" + port,
            "X-Top-Account-Id": "account",
        }
    )
    expected.set_body(body.decode())
    with patch.object(
        mod.SignerV4, "get_current_format_date", return_value="20260101T000000Z"
    ):
        mod.SignerV4.sign(
            expected, Credentials("endpoint", "secret", "clawsentry", "cn-private")
        )
        assert c._headers(body) == expected.headers
