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

import functools
import json

from google.adk.events.event import Event
from google.adk.sessions import Session
from google.genai.types import Content, Part
from litellm import completion

from veadk.config import getenv
from veadk.prompts.prompt_memory_processor import render_prompt
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class ShortTermMemoryProcessor:
    def __init__(self) -> None: ...

    def patch(self):
        """Patch the `get_session` function"""

        def intercept_get_session(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                session = await func(*args, **kwargs)
                if session:
                    abstracted_session = self.after_load_session(session)
                else:
                    abstracted_session = session
                return abstracted_session

            return wrapper

        return intercept_get_session

    def after_load_session(self, session: Session) -> Session:
        messages = []
        for event in session.events:
            content = event.content
            if not content or not content.parts:
                continue
            message = {
                "role": content.role,
                "content": content.parts[0].text,
            }
            messages.append(message)

        prompt = render_prompt(messages=messages)

        res = completion(
            model=getenv("MODEL_AGENT_PROVIDER") + "/" + getenv("MODEL_AGENT_NAME"),
            base_url=getenv("MODEL_AGENT_API_BASE"),
            api_key=getenv("MODEL_AGENT_API_KEY"),
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )
        logger.debug(f"Response from memory optimization model: {res}")

        extracted_messages = json.loads(res.choices[0].message.content)  # type: ignore
        logger.debug(f"Abstracted messages: {extracted_messages}")

        session.events = []
        for message in extracted_messages:
            session.events.append(
                Event(
                    author="memory_optimizer",
                    content=Content(
                        role=message["role"],
                        parts=[
                            Part(
                                text=message["content"],
                            )
                        ],
                    ),
                )
            )
        return session
