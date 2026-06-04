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

"""Demo agent showcasing A2UI (agent-driven UI).

Run it with the bundled web UI:

    veadk frontend --agents-dir examples

then open http://127.0.0.1:8000 and ask e.g. "show me a flight status card".
"""

from veadk import Agent
from veadk.utils.pdf_to_images import pdf_to_images_before_model_callback

INSTRUCTION = """You are a helpful assistant that can render rich UI.

When the answer is naturally visual or structured (a status card, a summary, a
list of options, a small form), reply by calling the `send_a2ui_json_to_client`
tool with A2UI JSON built ONLY from the components in the provided catalog
(Card, Column, Row, Text, Icon, Button, Divider, ...). Put a `Card` at the root,
lay content out with `Column`/`Row`, and use `Text` with a `variant` for
headings. For everything else, just answer in plain text.
"""

agent = Agent(
    name="a2ui_agent",
    description="Demo agent that replies with A2UI rich UI.",
    instruction=INSTRUCTION,
    enable_a2ui=True,
    # Uploaded PDFs are rendered to page images so the vision model can read
    # them. The default model (doubao-seed-1.6) is vision-capable.
    before_model_callback=pdf_to_images_before_model_callback,
)

# Required by the Google ADK agent loader.
root_agent = agent
