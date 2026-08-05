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

import pytest
from pydantic import ValidationError

from frontend.server.evaluation_automation.models import (
    OptimizationGroup,
    OptimizationSuggestion,
    RunSseActivity,
)


def test_run_sse_activity_reads_existing_runtime_payload() -> None:
    activity = RunSseActivity.from_proxy(
        {
            "app_name": "support_agent",
            "user_id": "user-1",
            "session_id": "session-1",
        },
        runtime_id="runtime-1",
        region="cn-beijing",
        project_name="support",
        runtime_endpoint="https://runtime.example",
        runtime_authorization="Bearer secret",
    )

    assert activity.key == (
        "runtime-1",
        "support_agent",
        "user-1",
        "session-1",
    )
    assert "secret" not in repr(activity)
    assert "runtimeAuthorization" not in activity.model_dump(by_alias=True)


def test_other_optimization_module_requires_a_custom_name() -> None:
    item = OptimizationSuggestion(suggestion="补充守卫", reason="避免错误输入。")

    with pytest.raises(ValidationError, match="customModule"):
        OptimizationGroup(
            priority="high",
            module="other",
            customModule=None,
            items=[item],
        )

    group = OptimizationGroup(
        priority="high",
        module="other",
        customModule="安全边界",
        items=[item],
    )
    assert group.custom_module == "安全边界"
