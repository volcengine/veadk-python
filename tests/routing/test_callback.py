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

from types import SimpleNamespace

import pytest
from google.adk.models.llm_request import LlmRequest

from veadk.routing.callback import build_before_model_callback
from veadk.routing.context import get_turn_context


@pytest.mark.asyncio
async def test_callback_does_not_classify_outside_routed_execution():
    callback = build_before_model_callback(None, None, None)
    request = LlmRequest(model="original")
    assert await callback(SimpleNamespace(), request) is None
    assert request.model == "original"
    assert get_turn_context() is None
