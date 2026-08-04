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

"""Tests for Runner content adapters."""

from google.adk.models import LlmRequest

from veadk.extensions.harness.plugins.content_adapter import append_system_instruction


def test_append_system_instruction_replaces_previous_harness_context():
    request = LlmRequest()
    request.config.system_instruction = (
        "Base instruction.\n\n"
        "[Harness Context]\n"
        "task_goal: old\n"
        "[/Harness Context]\n\n"
        "Keep this line."
    )

    append_system_instruction(
        request,
        "[Harness Context]\ntask_goal: new\n[/Harness Context]",
    )

    instruction = request.config.system_instruction
    assert isinstance(instruction, str)
    assert instruction.count("[Harness Context]") == 1
    assert "task_goal: old" not in instruction
    assert "task_goal: new" in instruction
    assert "Base instruction." in instruction
    assert "Keep this line." in instruction


def test_append_system_instruction_replaces_only_matching_harness_block():
    request = LlmRequest()
    request.config.system_instruction = (
        "Base instruction.\n\n"
        "[Harness Context]\n"
        "task_goal: current\n"
        "[/Harness Context]\n\n"
        "[Harness Long Run Control]\n"
        "model_calls_so_far: 8\n"
        "[/Harness Long Run Control]"
    )

    append_system_instruction(
        request,
        "[Harness Long Run Control]\nmodel_calls_so_far: 9\n"
        "[/Harness Long Run Control]",
    )

    instruction = request.config.system_instruction
    assert isinstance(instruction, str)
    assert instruction.count("[Harness Context]") == 1
    assert instruction.count("[Harness Long Run Control]") == 1
    assert "task_goal: current" in instruction
    assert "model_calls_so_far: 8" not in instruction
    assert "model_calls_so_far: 9" in instruction
