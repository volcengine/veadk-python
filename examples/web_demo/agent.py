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

"""A minimal, spec-conforming agent for the VeADK Web UI.

Launch convention (same as `adk web`): run `veadk frontend` from the directory
*above* the agent folders. Every subdirectory whose name is a valid Python
module and that exposes a module-level ``root_agent`` becomes a selectable app
in the UI's dropdown (it is returned by ``/list-apps``).

    cd examples
    veadk frontend            # lists web_demo (and the other agent folders)
"""

from veadk import Agent
from veadk.utils.pdf_to_images import pdf_to_images_before_model_callback

agent = Agent(
    name="web_demo",
    description="A general-purpose assistant demo for VeADK Web.",
    instruction=(
        "You are a helpful assistant. Answer clearly and concisely in the "
        "user's language."
    ),
    before_model_callback=pdf_to_images_before_model_callback,
)

# Required by the ADK agent loader.
root_agent = agent
