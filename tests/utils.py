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

import random
import uuid

from google.adk.events import Event
from google.adk.sessions import Session
from google.genai import types


def generate_events(length: int) -> list[Event]:
    event_list = []
    for i in range(length):
        random_chinese = "".join(
            chr(random.randint(0x4E00, 0x9FA5)) for _ in range(random.randint(10, 100))
        )
        event = Event(
            invocation_id=str(uuid.uuid4()),
            author="test_agent",
            content=types.Content(
                parts=[types.Part(text=random_chinese)],
                role=["user", "model"][i % 2],
            ),
        )
        event_list.append(event)
    return event_list


def generate_session(
    events: list[Event],
    app_name: str = "app",
    user_id: str = "user",
    session_id: str = "0",
) -> Session:
    return Session(
        id=session_id,
        app_name=app_name,
        user_id=user_id,
        state={},
        events=events,
    )


def generate_sessions():
    pass
