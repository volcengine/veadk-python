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

import pytest

from frontend.server.evaluation_automation.datasets import ensure_feedback_sets


@pytest.mark.asyncio
async def test_ensure_feedback_sets_uses_two_runtime_defaults():
    from types import SimpleNamespace

    class Repository:
        async def ensure_defaults(self):
            return [SimpleNamespace(name="Good Case"), SimpleNamespace(name="Bad Case")]

    assert await ensure_feedback_sets(Repository()) == ["Good Case", "Bad Case"]
