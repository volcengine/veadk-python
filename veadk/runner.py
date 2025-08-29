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
import os
import asyncio
from typing import Union
from urllib.parse import urlparse
from datetime import datetime

from google.adk.agents import RunConfig
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.agents.run_config import StreamingMode
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.runners import Runner as ADKRunner
from google.genai import types
from google.genai.types import Blob

from veadk.a2a.remote_ve_agent import RemoteVeAgent
from veadk.agent import Agent
from veadk.agents.loop_agent import LoopAgent
from veadk.agents.parallel_agent import ParallelAgent
from veadk.agents.sequential_agent import SequentialAgent
from veadk.evaluation import EvalSetRecorder
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.types import MediaMessage
from veadk.utils.logger import get_logger
from veadk.utils.misc import read_png_to_bytes
from veadk.database.tos.tos_client import TOSClient

logger = get_logger(__name__)


RunnerMessage = Union[
    str,  # single turn text-based prompt
    list[str],  # multiple turn text-based prompt
    MediaMessage,  # single turn prompt with media
    list[MediaMessage],  # multiple turn prompt with media
    list[MediaMessage | str],  # multiple turn prompt with media and text-based prompt
]

VeAgent = Union[Agent, RemoteVeAgent, SequentialAgent, ParallelAgent, LoopAgent]


class Runner:
    def __init__(
        self,
        agent: VeAgent,
        short_term_memory: ShortTermMemory | None = None,
        plugins: list[BasePlugin] | None = None,
        app_name: str = "veadk_default_app",
        user_id: str = "veadk_default_user",
    ):
        self.app_name = app_name
        self.user_id = user_id

        self.agent = agent

        if not short_term_memory:
            logger.info(
                "No short term memory provided, using a in-memory memory by default."
            )
            self.short_term_memory = ShortTermMemory()
        else:
            self.short_term_memory = short_term_memory

        self.session_service = self.short_term_memory.session_service

        # prevent VeRemoteAgent has no long-term memory attr
        if isinstance(self.agent, Agent):
            self.long_term_memory = self.agent.long_term_memory
        else:
            self.long_term_memory = None

        self.runner = ADKRunner(
            app_name=self.app_name,
            agent=self.agent,
            session_service=self.session_service,
            memory_service=self.long_term_memory,
            plugins=plugins,
        )

    def _build_tos_object_key(
        self, user_id: str, app_name: str, session_id: str, data_path: str
    ) -> str:
        """generate TOS object key"""
        parsed_url = urlparse(data_path)

        if parsed_url.scheme and parsed_url.scheme in ("http", "https", "ftp", "ftps"):
            file_name = os.path.basename(parsed_url.path)
        else:
            file_name = os.path.basename(data_path)

        timestamp: str = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]
        object_key: str = f"{app_name}-{user_id}-{session_id}/{timestamp}-{file_name}"
        return object_key

    def _upload_to_tos(self, data: Union[str, bytes], object_key: str):
        tos_client = TOSClient()
        asyncio.create_task(tos_client.upload(object_key, data))
        tos_client.close()
        return

    def _convert_messages(self, messages, session_id) -> list:
        if isinstance(messages, str):
            messages = [types.Content(role="user", parts=[types.Part(text=messages)])]
        elif isinstance(messages, MediaMessage):
            assert messages.media.endswith(".png"), (
                "The MediaMessage only supports PNG format file for now."
            )
            data = read_png_to_bytes(messages.media)
            try:
                object_key = self._build_tos_object_key(
                    self.user_id, self.app_name, session_id, messages.media
                )
                self._upload_to_tos(data, object_key)
            except Exception as e:
                logger.error(f"Upload to TOS failed: {e}")
                object_key = None

            messages = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part(text=messages.text),
                        types.Part(
                            inline_data=Blob(
                                display_name=object_key,
                                data=data,
                                mime_type="image/png",
                            )
                        ),
                    ],
                )
            ]
        elif isinstance(messages, list):
            converted_messages = []
            for message in messages:
                converted_messages.extend(self._convert_messages(message, session_id))
            messages = converted_messages
        else:
            raise ValueError(f"Unknown message type: {type(messages)}")

        return messages

    async def _run(
        self,
        session_id: str,
        message: types.Content,
        run_config: RunConfig | None = None,
        stream: bool = False,
    ):
        stream_mode = StreamingMode.SSE if stream else StreamingMode.NONE

        if run_config is not None:
            stream_mode = run_config.streaming_mode
        else:
            run_config = RunConfig(streaming_mode=stream_mode)
        try:

            async def event_generator():
                async for event in self.runner.run_async(
                    user_id=self.user_id,
                    session_id=session_id,
                    new_message=message,
                    run_config=run_config,
                ):
                    if event.get_function_calls():
                        for function_call in event.get_function_calls():
                            logger.debug(f"Function call: {function_call}")
                    elif (
                        event.content is not None
                        and event.content.parts
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
        except LlmCallsLimitExceededError as e:
            logger.warning(f"Max number of llm calls limit exceeded: {e}")

        return final_output

    async def run(
        self,
        messages: RunnerMessage,
        session_id: str,
        stream: bool = False,
        run_config: RunConfig | None = None,
        save_tracing_data: bool = False,
    ):
        converted_messages: list = self._convert_messages(messages, session_id)

        await self.short_term_memory.create_session(
            app_name=self.app_name, user_id=self.user_id, session_id=session_id
        )

        logger.info("Begin to process user messages.")

        final_output = ""
        for converted_message in converted_messages:
            final_output = await self._run(
                session_id, converted_message, run_config, stream
            )

        # try to save tracing file
        if save_tracing_data:
            self.save_tracing_file(session_id)

        self._print_trace_id()

        return final_output

    def get_trace_id(self) -> str:
        if not isinstance(self.agent, Agent):
            logger.warning(
                ("The agent is not an instance of VeADK Agent, no trace id provided.")
            )
            return "<unknown_trace_id>"

        if not self.agent.tracers:
            logger.warning(
                "No tracer is configured in the agent, no trace id provided."
            )
            return "<unknown_trace_id>"

        try:
            trace_id = self.agent.tracers[0].trace_id  # type: ignore
            return trace_id
        except Exception as e:
            logger.warning(f"Get tracer id failed as {e}")
            return "<unknown_trace_id>"

    async def run_with_raw_message(
        self,
        message: types.Content,
        session_id: str,
        run_config: RunConfig | None = None,
    ):
        run_config = RunConfig() if not run_config else run_config

        await self.short_term_memory.create_session(
            app_name=self.app_name, user_id=self.user_id, session_id=session_id
        )

        try:

            async def event_generator():
                async for event in self.runner.run_async(
                    user_id=self.user_id,
                    session_id=session_id,
                    new_message=message,
                    run_config=run_config,
                ):
                    if event.get_function_calls():
                        for function_call in event.get_function_calls():
                            logger.debug(f"Function call: {function_call}")
                    elif (
                        event.content is not None
                        and event.content.parts
                        and event.content.parts[0].text is not None
                        and len(event.content.parts[0].text.strip()) > 0
                    ):
                        yield event.content.parts[0].text

            final_output = ""

            async for chunk in event_generator():
                final_output += chunk
        except LlmCallsLimitExceededError as e:
            logger.warning(f"Max number of llm calls limit exceeded: {e}")

        return final_output

    def _print_trace_id(self) -> None:
        if not isinstance(self.agent, Agent):
            logger.warning(
                ("The agent is not an instance of VeADK Agent, no trace id provided.")
            )
            return

        if not self.agent.tracers:
            logger.warning(
                "No tracer is configured in the agent, no trace id provided."
            )
            return

        try:
            trace_id = self.agent.tracers[0].trace_id  # type: ignore
            logger.info(f"Trace id: {trace_id}")
        except Exception as e:
            logger.warning(f"Get tracer id failed as {e}")
            return

    def save_tracing_file(self, session_id: str) -> str:
        if not isinstance(
            self.agent, (Agent, SequentialAgent, ParallelAgent, LoopAgent)
        ):
            logger.warning(
                (
                    "The agent is not an instance of Agent, SequentialAgent, ParallelAgent or LoopAgent, cannot save tracing file."
                )
            )
            return ""

        if not self.agent.tracers:
            logger.warning("No tracer is configured in the agent.")
            return ""

        try:
            dump_path = ""
            for tracer in self.agent.tracers:
                dump_path = tracer.dump(user_id=self.user_id, session_id=session_id)

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
        if not session:
            logger.error(
                f"Session {session_id} not found in session service, cannot save to long-term memory."
            )
            return

        await self.long_term_memory.add_session_to_memory(session)
        logger.info(f"Add session `{session.id}` to long term memory.")

    # [deprecated] we will not host a chat-service in VeADK, so the following two methods are deprecated

    # async def run_with_final_event(
    #     self,
    #     messages: RunnerMessage,
    #     session_id: str,
    # ):
    #     """non-streaming run with final event"""
    #     messages: list = self._convert_messages(messages)

    #     await self.short_term_memory.create_session(
    #         app_name=self.app_name, user_id=self.user_id, session_id=session_id
    #     )

    #     logger.info("Begin to process user messages.")

    #     final_event = ""
    #     async for event in self.runner.run_async(
    #         user_id=self.user_id, session_id=session_id, new_message=messages[0]
    #     ):
    #         if event.get_function_calls():
    #             for function_call in event.get_function_calls():
    #                 logger.debug(f"Function call: {function_call}")
    #         elif (
    #             not event.partial
    #             and event.content.parts[0].text is not None
    #             and len(event.content.parts[0].text.strip()) > 0
    #         ):
    #             final_event = event.model_dump_json(exclude_none=True, by_alias=True)

    #     return final_event

    # async def run_sse(
    #     self,
    #     session_id: str,
    #     prompt: str,
    # ):
    #     message = types.Content(role="user", parts=[types.Part(text=prompt)])

    #     await self.short_term_memory.create_session(
    #         app_name=self.app_name, user_id=self.user_id, session_id=session_id
    #     )

    #     logger.info("Begin to process user messages under SSE method.")

    #     async for event in self.runner.run_async(
    #         user_id=self.user_id,
    #         session_id=session_id,
    #         new_message=message,
    #         run_config=RunConfig(streaming_mode=StreamingMode.SSE),
    #     ):
    #         # Format as SSE data
    #         sse_event = event.model_dump_json(exclude_none=True, by_alias=True)
    #         if event.get_function_calls():
    #             for function_call in event.get_function_calls():
    #                 logger.debug(f"SSE function call event: {sse_event}")
    #         yield f"data: {sse_event}\n\n"
