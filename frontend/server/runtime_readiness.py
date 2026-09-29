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

"""Wait for newly deployed Runtime instances before accepting conversations"""

from threading import Event
from time import monotonic
from typing import Any

from agentkit.sdk.runtime.types import ListRuntimeInstancesRequest


def wait_for_runtime_instances(
    client: Any,
    runtime_id: str,
    minimum: int,
    *,
    cancelled: Event,
    timeout: float = 300,
) -> None:
    # Control-plane Ready can precede the configured instances. A conversation
    # started then may land on a temporary instance and lose its in-memory session.
    if minimum <= 0:
        return
    deadline = monotonic() + timeout
    while True:
        if cancelled.is_set():
            raise RuntimeError("Deployment cancelled")
        if monotonic() >= deadline:
            raise RuntimeError("Runtime 实例未在时限内就绪，请在控制台检查实例状态")
        response = client.list_runtime_instances(
            ListRuntimeInstancesRequest(RuntimeId=runtime_id)
        )
        ready = {
            item.instance_name
            for item in response.instance_items or []
            if item.runtime_id == runtime_id
            and item.instance_status == "Ready"
            and item.instance_name
            # ListRuntimeInstances omits InstanceType. VeFaaS encodes reserved
            # versus elastic instances in the instance name returned here.
            and "-reserved-" in item.instance_name
        }
        if len(ready) >= minimum:
            return
        cancelled.wait(2)
