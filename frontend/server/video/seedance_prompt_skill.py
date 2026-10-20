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

"""Seedance 2.5 prompt skill snippets for Studio video creation.

The snippets are intentionally separate from ``prompts.py`` so product and SA
prompt expertise can evolve without weakening the JSON contract and server-side
parameter policy enforced by the prompt enhancer.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_CORE_PROMPT_FORMULA = """
Seedance 2.5 prompt skill:
- Build the enhanced_prompt with subject + action/event + scene/environment +
  visual style + camera movement/cut + audio when relevant.
- Turn abstract intent into observable details: visible action, spatial
  relationship, lighting, material, expression, gaze, breathing, sound, and
  camera behavior.
- Use generation controls only to plan visible composition and pacing. Do not
  ask the model to change API-only parameters inside enhanced_prompt.
- Keep the enhanced_prompt directly usable by Seedance 2.5, concise enough to
  execute, and specific enough to reduce identity drift, flicker, and omitted
  events.
"""

_REFERENCE_MATERIAL_GUIDE = """
Reference material skill:
- Map every uploaded material explicitly. Use phrases such as:
  @Image 1 defines the subject appearance, clothing, structure, or material.
  @Video 1 defines motion, camera movement, pacing, blocking, or audio rhythm.
- State what not to use from each reference when backgrounds, people,
  compositions, or styles could leak into the generated video.
- Bind each distinct character, product, prop, and scene separately. Avoid
  vague mappings such as "Images 1-4 define four characters respectively".
- When many references exist, group them by characters, props, scenes, motion,
  and audio, then select only the relevant references for each scene.
"""

_LONG_VIDEO_GUIDE = """
Long-video skill:
- For videos near 30 seconds, organize the prompt into consecutive stages.
- Each stage should contain one primary state change and a directly visible end state,
  such as character position, prop ownership, scene state, or camera composition.
- Prefer stage ranges for narrative pacing. Use exact timestamps only for a
  critical handoff, entrance, exit, transition, or explicit beat.
- Keep character identity, clothing, number of subjects, prop ownership,
  spatial direction, and audio relationships consistent across stages.
"""

_TASK_GUIDES = {
    "auto": """
Task routing skill:
- If the user selected auto, infer the task from media and wording, then write
  the enhanced_prompt for the resolved task instead of describing the routing.
""",
    "text_to_video": """
Text-to-video skill:
- Preserve the user's creative intent while enriching subject, action, scene,
  camera, light, texture, atmosphere, and useful audio.
- If duration is short, focus on one clear event. If duration is long, use
  staged progression with visible end states.
""",
    "reference_to_video": """
Reference-to-video skill:
- Treat media as guidance for a new video, not as a source to edit directly.
- Define each reference role and exclusion, then describe the new scene, event,
  visual style, camera treatment, and audio.
""",
    "video_editing": """
Video-editing skill:
- @Video 1 is the sole editing master. It defines characters, scene, actions,
  composition, camera movement, occlusion, audio, and event order.
- Define edit goal, source video role, target material role when present,
  edit scope, and content to preserve.
- Modify only the requested object, region, time range, or audio category.
  Preserve everything else from @Video 1, including timing, motion, identity,
  lighting, camera, dialogue, ambience, and event order.
""",
    "video_extension": """
Video-extension skill:
- Continue naturally from the final moment of Video 1. Do not restart the story
  or reintroduce the subject from scratch.
- Preserve boundary frame continuity, motion trend, camera direction, lighting,
  subject identity, scene logic, and audio continuity.
""",
    "first_last_frame": """
First/last-frame skill:
- Treat the first and last images as exact frame anchors, not loose inspiration.
- Describe a natural motion path from the first anchor to the last anchor while
  preserving identity, structure, lighting, framing, and spatial continuity.
""",
}


def build_seedance_skill_context(
    task_type: str,
    input_data: Mapping[str, Any],
) -> str:
    """Return task-aware Seedance 2.5 prompt skill context.

    This context is advisory prompt expertise. The canonical task schema and
    parameter policy remain enforced in ``prompts.py`` after the model responds.
    """

    blocks = [_CORE_PROMPT_FORMULA, _TASK_GUIDES.get(task_type, _TASK_GUIDES["auto"])]
    if _has_reference_material(input_data) or task_type in {
        "reference_to_video",
        "video_editing",
        "video_extension",
        "first_last_frame",
    }:
        blocks.append(_REFERENCE_MATERIAL_GUIDE)
    if _selected_duration(input_data) >= 20:
        blocks.append(_LONG_VIDEO_GUIDE)
    return "\n\n".join(block.strip() for block in blocks if block.strip())


def _has_reference_material(input_data: Mapping[str, Any]) -> bool:
    return bool(
        input_data.get("has_video")
        or input_data.get("has_image")
        or input_data.get("has_first_frame")
        or input_data.get("has_last_frame")
        or _positive_int(input_data.get("video_count"))
        or _positive_int(input_data.get("image_count"))
    )


def _selected_duration(input_data: Mapping[str, Any]) -> int:
    value = input_data.get("selected_duration", 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
