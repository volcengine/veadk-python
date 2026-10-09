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

"""Extra tool-schema text must not break retention of escaped reader evidence."""

import pytest
from test_native_search_budget import (
    test_native_distinct_searches_stay_within_request_budget as run_scenario,
)
from veadk.context.tool_results import _ContextReader


@pytest.mark.asyncio
@pytest.mark.parametrize("description_bytes", [0, 128, 1024])
async def test_escaped_evidence_retention_with_schema_overhead(
    tmp_path, monkeypatch, description_bytes
):
    original = _ContextReader._get_declaration

    def declare(self):
        value = original(self)
        value.description += "x" * description_bytes
        return value

    monkeypatch.setattr(_ContextReader, "_get_declaration", declare)
    await run_scenario(tmp_path, escaped=True, parallel=False)
