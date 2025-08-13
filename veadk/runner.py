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
from typing import Union

from google.adk.agents import RunConfig
from google.adk.agents.run_config import StreamingMode
from google.adk.runners import Runner as ADKRunner
from google.genai import types
from google.genai.types import Blob

from veadk.a2a.remote_ve_agent import RemoteVeAgent
from veadk.agent import Agent
from veadk.evaluation import EvalSetRecorder
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.types import MediaMessage
from veadk.utils.logger import get_logger
from veadk.utils.misc import read_png_to_bytes

logger = get_logger(__name__)


RunnerMessage = Union[
    str,  # single turn text-based prompt
    list[str],  # multiple turn text-based prompt
    MediaMessage,  # single turn prompt with media
    list[MediaMessage],  # multiple turn prompt with media
    list[MediaMessage | str],  # multiple turn prompt with media and text-based prompt
]


class Runner:
    def __init__(
        self,
        agent: Agent | RemoteVeAgent,
        short_term_memory: ShortTermMemory,
        app_name: str = "veadk_default_app",
        user_id: str = "veadk_default_user",
    ):
        # basic settings
        self.app_name = app_name
        self.user_id = user_id

        # agent settings
        self.agent = agent

        self.short_term_memory = short_term_memory
        self.session_service = short_term_memory.session_service

        if isinstance(self.agent, Agent):
            self.long_term_memory = self.agent.long_term_memory
        else:
            self.long_term_memory = None

        # maintain a in-memory runner for fast inference
        self.runner = ADKRunner(
            app_name=self.app_name,
            agent=self.agent,
            session_service=self.session_service,
            memory_service=self.long_term_memory,
        )

        if getattr(self.agent, "tracers", None):
            for tracers in self.agent.tracers:
                tracers.set_app_name(self.app_name)

    def _convert_messages(self, messages) -> list:
        if isinstance(messages, str):
            messages = [types.Content(role="user", parts=[types.Part(text=messages)])]
        elif isinstance(messages, MediaMessage):
            assert messages.media.endswith(".png"), (
                "The MediaMessage only supports PNG format file for now."
            )
            messages = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part(text=messages.text),
                        types.Part(
                            inline_data=Blob(
                                display_name=messages.media,
                                data=read_png_to_bytes(messages.media),
                                mime_type="image/png",
                            )
                        ),
                    ],
                )
            ]
        elif isinstance(messages, list):
            converted_messages = []
            for message in messages:
                converted_messages.extend(self._convert_messages(message))
            messages = converted_messages
        else:
            raise ValueError(f"Unknown message type: {type(messages)}")

        return messages

    async def _run(
        self,
        session_id: str,
        message: types.Content,
        stream: bool = False,
    ):
        stream_mode = StreamingMode.SSE if stream else StreamingMode.NONE

        async def event_generator():
            async for event in self.runner.run_async(
                user_id=self.user_id,
                session_id=session_id,
                new_message=message,
                run_config=RunConfig(streaming_mode=stream_mode),
            ):
                if event.get_function_calls():
                    for function_call in event.get_function_calls():
                        logger.debug(f"Function call: {function_call}")
                elif (
                    event.content is not None
                    and event.content.parts[0].text is not None
                    and len(event.content.parts[0].text.strip()) > 0
                ):
                    yield event.content.parts[0].text

        final_output = ""
        async for chunk in event_generator():
            if stream:
                print(chunk, end="", flush=True)
            final_output += chunk
        if stream:
            print()  # end with a new line

        return final_output

    async def run(
        self,
        messages: RunnerMessage,
        session_id: str,
        stream: bool = False,
    ):
        messages: list = self._convert_messages(messages)

        await self.short_term_memory.create_session(
            app_name=self.app_name, user_id=self.user_id, session_id=session_id
        )

        logger.info("Begin to process user messages.")

        final_output = ""
        for message in messages:
            final_output = await self._run(session_id, message, stream)

        # try to save tracing file
        if isinstance(self.agent, Agent):
            self.save_tracing_file(session_id)

        return final_output

    def save_tracing_file(self, session_id: str) -> str:
        if not self.agent.tracers:
            return

        try:
            dump_path = ""
            for tracer in self.agent.tracers:
                dump_path = tracer.dump(self.user_id, session_id)

            return dump_path
        except Exception as e:
            logger.error(f"Failed to save tracing file: {e}")
            return ""

    async def save_eval_set(self, session_id: str, eval_set_id: str = "default") -> str:
        eval_set_recorder = EvalSetRecorder(self.session_service, eval_set_id)
        eval_set_path = await eval_set_recorder.dump(
            self.app_name, self.user_id, session_id
        )
        return eval_set_path

    async def save_session_to_long_term_memory(self, session_id: str) -> None:
        if not self.long_term_memory:
            logger.warning("Long-term memory is not enabled. Failed to save session.")
            return

        session = await self.session_service.get_session(
            app_name=self.app_name,
            user_id=self.user_id,
            session_id=session_id,
        )
        await self.long_term_memory.add_session_to_memory(session)
        logger.info(f"Add session `{session.id}` to long-term memory.")

    async def run_with_final_event(
        self,
        messages: RunnerMessage,
        session_id: str,
    ):
        """non-streaming run with final event"""
        messages: list = self._convert_messages(messages)

        await self.short_term_memory.create_session(
            app_name=self.app_name, user_id=self.user_id, session_id=session_id
        )

        logger.info("Begin to process user messages.")

        final_event = ""
        async for event in self.runner.run_async(
            user_id=self.user_id, session_id=session_id, new_message=messages[0]
        ):
            if event.get_function_calls():
                for function_call in event.get_function_calls():
                    logger.debug(f"Function call: {function_call}")
            elif (
                not event.partial
                and event.content.parts[0].text is not None
                and len(event.content.parts[0].text.strip()) > 0
            ):
                final_event = event.model_dump_json(exclude_none=True, by_alias=True)

        return final_event

    async def run_sse(
        self,
        session_id: str,
        prompt: str,
    ):
        message = types.Content(role="user", parts=[types.Part(text=prompt)])

        await self.short_term_memory.create_session(
            app_name=self.app_name, user_id=self.user_id, session_id=session_id
        )

        logger.info("Begin to process user messages under SSE method.")

        async for event in self.runner.run_async(
            user_id=self.user_id,
            session_id=session_id,
            new_message=message,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        ):
            # Format as SSE data
            sse_event = event.model_dump_json(exclude_none=True, by_alias=True)
            if event.get_function_calls():
                for function_call in event.get_function_calls():
                    logger.debug(f"SSE function call event: {sse_event}")
            yield f"data: {sse_event}\n\n"
