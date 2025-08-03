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

from jinja2 import Template

MEMORY_PROCESSOR_SYSTEM_PROMPT = """I will give you a series of messages of memory, including messages from user and assistant.

You should help me to recognize important information from the messages, and build some new messages.

For example, for the following messages:
[
    {
        "role": "user",
        "content": "Hello, tell me the weather of Beijing, and remember my secret is `abc001`"
    },
    {
        "role": "assistant",
        "content": "The weather of Beijing is sunny, and the temperature is 25 degree Celsius. I have remember that your secret is `abc001`."
    }
]

You should extract the important information from the messages, and build new messages if needed (in JSON format):
[
    {
        "role": "user",
        "content": "My secret is `abc001`."
    }
]

The actual messages are:
{{ messages }}
"""


def render_prompt(messages: list[dict]):
    template = Template(MEMORY_PROCESSOR_SYSTEM_PROMPT)

    context = {
        "messages": messages,
    }

    rendered_prompt = template.render(context)

    return rendered_prompt
