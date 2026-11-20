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

"""Hermetic tests for the ``image_generate`` built-in tool."""

from unittest.mock import MagicMock

import pytest

from veadk.tools.builtin_tools import image_generate as tool


@pytest.mark.asyncio
async def test_per_image_error_does_not_abort_the_rest_of_the_batch(monkeypatch):
    async def fake_call_image_api(item, model_name, timeout):
        return {
            "data": [
                {"url": "https://example.com/1.png"},
                {"error": {"code": "OutputImageSensitiveContentDetected"}},
                {"url": "https://example.com/3.png"},
            ]
        }

    monkeypatch.setattr(tool, "_call_image_api", fake_call_image_api)

    success, errors, details = await tool.handle_single_task(
        0,
        {"prompt": "a cat"},
        30,
        MagicMock(state={}),
        "doubao-seedream",
    )

    assert success == [
        {"task_0_image_0": "https://example.com/1.png"},
        {"task_0_image_2": "https://example.com/3.png"},
    ]
    assert errors == ["task_0_image_1"]
    assert details == [
        {
            "task_idx": 0,
            "image_name": "task_0_image_1",
            "error": {"code": "OutputImageSensitiveContentDetected"},
        }
    ]
