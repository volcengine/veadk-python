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

from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from frontend.server.runtime_readiness import wait_for_runtime_instances


def instance(name: str, status: str = "Ready", runtime: str = "r-test"):
    return SimpleNamespace(
        instance_name=f"function-revision-reserved-{name}",
        instance_status=status,
        runtime_id=runtime,
    )


def test_waits_for_all_configured_instances_to_be_ready(monkeypatch):
    client = Mock()
    client.list_runtime_instances.side_effect = [
        SimpleNamespace(instance_items=[]),
        SimpleNamespace(
            instance_items=[
                SimpleNamespace(
                    instance_name="function-revision-elastic-one",
                    instance_status="Ready",
                    runtime_id="r-test",
                )
            ]
        ),
        SimpleNamespace(instance_items=[instance("one", "Starting")]),
        SimpleNamespace(
            instance_items=[instance("one"), instance("other", runtime="r-other")]
        ),
        SimpleNamespace(instance_items=[instance("one"), instance("two")]),
    ]
    cancelled = Mock(spec=Event)
    cancelled.is_set.return_value = False
    cancelled.wait.return_value = False
    wait_for_runtime_instances(client, "r-test", 2, cancelled=cancelled)
    assert client.list_runtime_instances.call_count == 5
    assert cancelled.wait.call_count == 4
    assert client.list_runtime_instances.call_args.args[0].runtime_id == "r-test"


def test_zero_minimum_does_not_wait_for_scale_to_zero_runtime():
    client = Mock()
    wait_for_runtime_instances(client, "r-test", 0, cancelled=Event())
    client.list_runtime_instances.assert_not_called()


def test_cancellation_stops_readiness_wait():
    cancelled = Event()
    cancelled.set()
    client = Mock()
    with pytest.raises(RuntimeError, match="cancelled"):
        wait_for_runtime_instances(client, "r-test", 1, cancelled=cancelled)
    client.list_runtime_instances.assert_not_called()


def test_timeout_is_not_reported_as_success(monkeypatch):
    clock = iter([0, 0, 301])
    monkeypatch.setattr(
        "frontend.server.runtime_readiness.monotonic", lambda: next(clock)
    )
    client = Mock()
    client.list_runtime_instances.return_value = SimpleNamespace(instance_items=[])
    cancelled = Mock(spec=Event)
    cancelled.is_set.return_value = False
    with pytest.raises(RuntimeError, match="实例未在时限内就绪"):
        wait_for_runtime_instances(client, "r-test", 1, cancelled=cancelled)


def test_cloud_errors_are_not_hidden():
    client = Mock()
    client.list_runtime_instances.side_effect = RuntimeError("access denied")
    with pytest.raises(RuntimeError, match="access denied"):
        wait_for_runtime_instances(client, "r-test", 1, cancelled=Event())
