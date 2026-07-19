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

"""A frontend-ready Agent that understands common multimodal attachments."""

from veadk import Agent
from veadk.consts import DEFAULT_MODEL_AGENT_NAME
from veadk.tools.builtin_tools.image_generate import image_generate
from veadk.tools.builtin_tools.video_generate import video_generate

INSTRUCTION = """You are a multimodal analysis assistant.

The user may attach images, TXT or Markdown documents, PDFs, and videos. Inspect
every attachment that is available in the request and answer in the user's
language.

- For images, describe relevant visual details and read visible text when useful.
- For TXT or Markdown, summarize or answer from the document content.
- For PDFs, explain the structure and key findings and cite page numbers when the
  input exposes them.
- For videos, describe the timeline, important scenes, actions, and visible text.
- When several attachments are present, compare and connect their information.
- When the user asks to create an image, call `image_generate`.
- When the user asks to create a video, call `video_generate`.

Distinguish observations from inferences. Never claim to have inspected content
that is unavailable or unreadable; explain the limitation instead.
"""

agent = Agent(
    name="multimodal_agent",
    description="Analyzes multimodal files and generates images or videos.",
    instruction=INSTRUCTION,
    model_name=DEFAULT_MODEL_AGENT_NAME,
    tools=[image_generate, video_generate],
)

# Required by the Google ADK agent loader.
root_agent = agent
