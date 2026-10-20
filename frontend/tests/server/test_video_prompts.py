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

import json

import pytest
from pydantic import ValidationError

from frontend.server.video.models import PromptEnhanceRequest, VideoTaskCreateRequest
from frontend.server.video.prompts import (
    ASPECT_RATIOS,
    TASK_TYPES,
    PromptValidationError,
    apply_parameter_policy,
    build_enhancement_input,
    build_enhancement_messages,
    infer_task_type,
    parameter_policy,
    parse_enhancement_output,
)
from frontend.server.video.seedance_prompt_skill import build_seedance_skill_context


def _valid_output(task_type: str = "text_to_video") -> dict:
    return {
        "task_type": task_type,
        "lock_mode": (
            "unlocked"
            if task_type in {"text_to_video", "reference_to_video"}
            else "locked"
        ),
        "intent_confidence": 0.92,
        "reasoning_summary": "The selected task matches the supplied assets.",
        "enhanced_prompt": "A stable cinematic scene with a clear action arc.",
        "asset_mapping": [],
        "param_policy": parameter_policy(task_type),
        "risk_flags": [],
        "rewrite_notes": ["Clarified motion and camera behavior."],
    }


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "selected_task_mode": "video_editing",
                "raw_prompt": "continue the clip",
                "has_video": True,
                "has_first_frame": True,
            },
            "video_editing",
        ),
        (
            {"raw_prompt": "make a transition", "has_first_frame": True},
            "first_last_frame",
        ),
        (
            {
                "raw_prompt": "继续这个视频并替换最后一幕",
                "has_video": True,
            },
            "video_extension",
        ),
        (
            {"raw_prompt": "替换人物的外套", "has_video": True},
            "video_editing",
        ),
        (
            {"raw_prompt": "create a new campaign", "has_image": True},
            "reference_to_video",
        ),
        ({"raw_prompt": "a paper bird takes flight"}, "text_to_video"),
    ],
)
def test_infer_task_type_priority(payload, expected):
    assert infer_task_type(payload) == expected


def test_build_messages_contains_system_strategy_and_json_input():
    input_data = build_enhancement_input(
        "让镜头继续向后拉",
        has_video=True,
        video_count=1,
        selected_duration=10,
    )

    messages = build_enhancement_messages(input_data)

    assert [message["role"] for message in messages] == ["system", "user"]
    assert "video_editing" in messages[0]["content"]
    assert "first_last_frame" in messages[0]["content"]
    assert all(
        mode in messages[0]["content"]
        for mode in (
            "text_to_video",
            "reference_to_video",
            "video_editing",
            "video_extension",
            "first_last_frame",
        )
    )
    assert json.loads(messages[1]["content"]) == input_data


def test_build_messages_include_seedance_skill_context_for_long_video():
    input_data = build_enhancement_input(
        "Create a cinematic product launch story.",
        selected_task_mode="text_to_video",
        selected_duration=30,
    )

    messages = build_enhancement_messages(input_data)
    system_prompt = messages[0]["content"]

    assert "Seedance 2.5 prompt skill context" in system_prompt
    assert "subject + action/event + scene/environment" in system_prompt
    assert "consecutive stages" in system_prompt
    assert "directly visible end state" in system_prompt


def test_build_messages_include_reference_material_mapping_guidance():
    input_data = build_enhancement_input(
        "Create a new campaign video using the product reference.",
        selected_task_mode="reference_to_video",
        has_image=True,
        image_count=1,
    )

    messages = build_enhancement_messages(input_data)
    system_prompt = messages[0]["content"]

    assert "@Image 1 defines" in system_prompt
    assert "what not to use" in system_prompt
    assert "not as a source to edit directly" in system_prompt


def test_seedance_skill_context_selects_video_editing_guidance():
    input_data = build_enhancement_input(
        "Replace the logo on the jacket and keep everything else unchanged.",
        selected_task_mode="video_editing",
        has_video=True,
        video_count=1,
    )

    context = build_seedance_skill_context("video_editing", input_data)

    assert "@Video 1 is the sole editing master" in context
    assert "edit scope" in context
    assert "content to preserve" in context


@pytest.mark.parametrize(
    ("task_type", "expected"),
    [
        (
            "text_to_video",
            {
                "ratio": "16:9",
                "resolution": "720p",
                "duration": 8,
                "output_format": "mp4",
                "generate_audio": True,
            },
        ),
        (
            "reference_to_video",
            {
                "ratio": "16:9",
                "resolution": "720p",
                "duration": 8,
                "output_format": "mp4",
                "generate_audio": True,
            },
        ),
        (
            "video_editing",
            {
                "ratio": "adaptive",
                "resolution": "720p",
                "duration": -1,
                "output_format": "mov",
                "generate_audio": True,
            },
        ),
        (
            "video_extension",
            {
                "ratio": "adaptive",
                "resolution": "720p",
                "duration": 8,
                "output_format": "mov",
                "generate_audio": True,
            },
        ),
        (
            "first_last_frame",
            {
                "ratio": "adaptive",
                "resolution": "720p",
                "duration": 8,
                "output_format": "mp4",
                "generate_audio": True,
            },
        ),
    ],
)
def test_apply_parameter_policy_for_all_modes(task_type, expected):
    assert (
        apply_parameter_policy(
            task_type,
            ratio="16:9",
            resolution="720p",
            duration=8,
        )
        == expected
    )


@pytest.mark.parametrize("duration", [4, 8, 30])
@pytest.mark.parametrize("resolution", ["480p", "720p"])
@pytest.mark.parametrize("ratio", sorted(ASPECT_RATIOS))
@pytest.mark.parametrize("task_type", TASK_TYPES)
def test_video_parameter_contract_matrix(
    task_type: str,
    ratio: str,
    resolution: str,
    duration: int,
):
    input_data = build_enhancement_input(
        "Create a coherent cinematic sequence.",
        selected_task_mode=task_type,
        selected_ratio=ratio,
        selected_resolution=resolution,
        selected_duration=duration,
    )

    assert infer_task_type(input_data) == task_type
    assert input_data["selected_ratio"] == ratio
    assert input_data["selected_resolution"] == resolution
    assert input_data["selected_duration"] == duration

    expected_policies = {
        "text_to_video": (ratio, duration, "mp4"),
        "reference_to_video": (ratio, duration, "mp4"),
        "video_editing": ("adaptive", -1, "mov"),
        "video_extension": ("adaptive", duration, "mov"),
        "first_last_frame": ("adaptive", duration, "mp4"),
    }
    expected_ratio, expected_duration, expected_format = expected_policies[task_type]

    assert apply_parameter_policy(
        task_type,
        ratio=ratio,
        resolution=resolution,
        duration=duration,
    ) == {
        "ratio": expected_ratio,
        "resolution": resolution,
        "duration": expected_duration,
        "output_format": expected_format,
        "generate_audio": True,
    }


@pytest.mark.parametrize("duration", [3, 31])
def test_video_duration_contract_rejects_values_outside_supported_range(duration):
    with pytest.raises(PromptValidationError, match="between 4 and 30"):
        build_enhancement_input("test", selected_duration=duration)

    with pytest.raises(PromptValidationError, match="between 4 and 30"):
        apply_parameter_policy(
            "text_to_video",
            ratio="16:9",
            resolution="720p",
            duration=duration,
        )


@pytest.mark.parametrize("duration", [4, 30])
def test_video_request_models_accept_user_duration_boundaries(duration):
    assert PromptEnhanceRequest(prompt="test", duration_seconds=duration)
    assert VideoTaskCreateRequest(
        enhanced_prompt="test",
        resolved_task_mode="text_to_video",
        duration_seconds=duration,
    )


def test_video_request_models_reject_invalid_duration_sentinels():
    with pytest.raises(ValidationError):
        PromptEnhanceRequest(prompt="test", duration_seconds=3)
    with pytest.raises(ValidationError):
        VideoTaskCreateRequest(
            enhanced_prompt="test",
            resolved_task_mode="text_to_video",
            duration_seconds=-1,
        )

    request = VideoTaskCreateRequest(
        enhanced_prompt="test",
        resolved_task_mode="video_editing",
        duration_seconds=-1,
    )
    assert request.duration_seconds == -1


def test_parse_output_accepts_json_and_validates_assets():
    output = _valid_output("reference_to_video")
    output["asset_mapping"] = [
        {
            "asset_name": "Image 1",
            "asset_type": "image",
            "role": "reference_image",
            "purpose": "Guide the subject styling.",
        }
    ]

    assert parse_enhancement_output(json.dumps(output)) == output


def test_parse_output_ignores_unknown_model_risk_flags():
    output = _valid_output()
    output["risk_flags"] = ["prompt_too_short", "cinematic_motion_risk"]

    parsed = parse_enhancement_output(output)

    assert parsed["risk_flags"] == ["prompt_too_short"]


def test_parse_output_rejects_non_string_risk_flags():
    output = _valid_output()
    output["risk_flags"] = [1]

    with pytest.raises(PromptValidationError, match="must contain strings"):
        parse_enhancement_output(output)


@pytest.mark.parametrize(
    ("selected_mode", "reported_mode", "reported_lock"),
    [
        ("reference_to_video", "reference_to_video", "locked"),
        ("first_last_frame", "reference_to_video", "unlocked"),
    ],
)
def test_parse_output_normalizes_explicit_mode_metadata(
    selected_mode: str,
    reported_mode: str,
    reported_lock: str,
):
    output = _valid_output(reported_mode)
    output["lock_mode"] = reported_lock
    output["param_policy"] = {"model_metadata": "not authoritative"}

    parsed = parse_enhancement_output(output, selected_task_mode=selected_mode)

    assert parsed["task_type"] == selected_mode
    assert parsed["lock_mode"] == (
        "unlocked"
        if selected_mode in {"text_to_video", "reference_to_video"}
        else "locked"
    )
    assert parsed["param_policy"] == parameter_policy(selected_mode)


def test_parse_output_rejects_unknown_task_type_in_auto_mode():
    output = _valid_output()
    output["task_type"] = "unsupported"

    with pytest.raises(PromptValidationError, match="Unsupported task type"):
        parse_enhancement_output(output)


def test_parse_output_rejects_asset_role_type_mismatch():
    output = _valid_output("video_editing")
    output["asset_mapping"] = [
        {
            "asset_name": "Video 1",
            "asset_type": "image",
            "role": "reference_video",
            "purpose": "Primary edit source.",
        }
    ]

    with pytest.raises(PromptValidationError, match="does not match its role"):
        parse_enhancement_output(output)


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        json.dumps({"task_type": "text_to_video"}),
        json.dumps({**_valid_output(), "unexpected": True}),
    ],
)
def test_invalid_schema(raw):
    with pytest.raises(PromptValidationError):
        parse_enhancement_output(raw)


def test_parse_output_rejects_non_object_value():
    with pytest.raises(PromptValidationError, match="JSON text or an object"):
        parse_enhancement_output([])


def test_build_input_rejects_unsupported_resolution():
    with pytest.raises(PromptValidationError, match="480p or 720p"):
        build_enhancement_input("test", selected_resolution="1080p")
