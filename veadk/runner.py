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
import os
from types import MethodType
from typing import Union

from google import genai
from google.adk.agents import RunConfig
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.runners import Runner as ADKRunner
from google.genai import types
from google.genai.types import Blob

from veadk.agent import Agent
from veadk.agents.loop_agent import LoopAgent
from veadk.agents.parallel_agent import ParallelAgent
from veadk.agents.sequential_agent import SequentialAgent
from veadk.config import getenv
from veadk.evaluation import EvalSetRecorder
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.types import MediaMessage
from veadk.utils.logger import get_logger
from veadk.utils.misc import formatted_timestamp, read_file_to_bytes

logger = get_logger(__name__)

RunnerMessage = Union[
    str,  # single turn text-based prompt
    list[str],  # multiple turn text-based prompt
    MediaMessage,  # single turn prompt with media
    list[MediaMessage],  # multiple turn prompt with media
    list[MediaMessage | str],  # multiple turn prompt with media and text-based prompt
]


async def pre_run_process(self, process_func, new_message, user_id, session_id):
    if new_message.parts:
        for part in new_message.parts:
            if part.inline_data and self.upload_inline_data_to_tos:
                await process_func(
                    part,
                    self.app_name,
                    user_id,
                    session_id,
                )


def post_run_process(self):
    return


def intercept_new_message(process_func):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(
            self,
            *,
            user_id: str,
            session_id: str,
            new_message: types.Content,
            **kwargs,
        ):
            await pre_run_process(self, process_func, new_message, user_id, session_id)

            async for event in func(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
                **kwargs,
            ):
                yield event

            post_run_process(self)

        return wrapper

    return decorator


def _convert_messages(
    messages: RunnerMessage,
    app_name: str,
    user_id: str,
    session_id: str,
) -> list:
    """Convert VeADK formatted messages to Google ADK formatted messages."""
    if isinstance(messages, str):
        _messages = [types.Content(role="user", parts=[types.Part(text=messages)])]
    elif isinstance(messages, MediaMessage):
        import filetype

        file_data = read_file_to_bytes(messages.media)

        kind = filetype.guess(file_data)
        if kind is None:
            raise ValueError("Unsupported or unknown file type.")

        mime_type = kind.mime

        assert mime_type.startswith(("image/", "video/")), (
            f"Unsupported media type: {mime_type}"
        )

        _messages = [
            types.Content(
                role="user",
                parts=[
                    types.Part(text=messages.text),
                    types.Part(
                        inline_data=Blob(
                            display_name=messages.media,
                            data=file_data,
                            mime_type=mime_type,
                        )
                    ),
                ],
            )
        ]
    elif isinstance(messages, list):
        converted_messages = []
        for message in messages:
            converted_messages.extend(
                _convert_messages(message, app_name, user_id, session_id)
            )
        _messages = converted_messages
    else:
        raise ValueError(f"Unknown message type: {type(messages)}")

    return _messages


async def _upload_image_to_tos(
    part: genai.types.Part, app_name: str, user_id: str, session_id: str
) -> None:
    try:
        if part.inline_data and part.inline_data.display_name and part.inline_data.data:
            from veadk.integrations.ve_tos.ve_tos import VeTOS

            filename = os.path.basename(part.inline_data.display_name)
            object_key = f"{app_name}/{user_id}-{session_id}-{filename}"
            ve_tos = VeTOS()
            tos_url = ve_tos.build_tos_signed_url(object_key=object_key)
            await ve_tos.async_upload_bytes(
                object_key=object_key,
                data=part.inline_data.data,
            )
            part.inline_data.display_name = tos_url
    except Exception as e:
        logger.error(f"Upload to TOS failed: {e}")


class Runner(ADKRunner):
    def __init__(
        self,
        agent: BaseAgent | Agent,
        short_term_memory: ShortTermMemory | None = None,
        app_name: str = "veadk_default_app",
        user_id: str = "veadk_default_user",
        upload_inline_data_to_tos: bool = False,
        *args,
        **kwargs,
    ) -> None:
        self.user_id = user_id
        self.long_term_memory = None
        self.short_term_memory = short_term_memory
        self.upload_inline_data_to_tos = upload_inline_data_to_tos

        session_service = kwargs.pop("session_service", None)
        memory_service = kwargs.pop("memory_service", None)

        if session_service:
            if short_term_memory:
                logger.warning(
                    "Short term memory is enabled, but session service is also provided. We will use session service from runner argument."
                )

        if not session_service:
            if short_term_memory:
                session_service = short_term_memory.session_service
                logger.debug(
                    f"Use session service {session_service} from short term memory."
                )
            else:
                logger.warning(
                    "No short term memory or session service provided, use an in-memory one instead."
                )
                short_term_memory = ShortTermMemory()
                self.short_term_memory = short_term_memory
                session_service = short_term_memory.session_service

        if memory_service:
            if hasattr(agent, "long_term_memory") and agent.long_term_memory:  # type: ignore
                self.long_term_memory = agent.long_term_memory  # type: ignore
                logger.warning(
                    "Long term memory in agent is enabled, but memory service is also provided. We will use memory service from runner argument."
                )

        if not memory_service:
            if hasattr(agent, "long_term_memory") and agent.long_term_memory:  # type: ignore
                self.long_term_memory = agent.long_term_memory  # type: ignore
                memory_service = agent.long_term_memory  # type: ignore
            else:
                logger.info("No long term memory provided.")

        super().__init__(
            agent=agent,
            session_service=session_service,
            memory_service=memory_service,
            app_name=app_name,
            *args,
            **kwargs,
        )

        self.run_async = MethodType(
            intercept_new_message(_upload_image_to_tos)(super().run_async), self
        )

    async def run(
        self,
        messages: RunnerMessage,
        user_id: str = "",
        session_id: str = f"tmp-session-{formatted_timestamp()}",
        run_config: RunConfig | None = None,
        save_tracing_data: bool = False,
        upload_inline_data_to_tos: bool = False,
    ):
        if upload_inline_data_to_tos:
            _upload_inline_data_to_tos = self.upload_inline_data_to_tos
            self.upload_inline_data_to_tos = upload_inline_data_to_tos

        if not run_config:
            run_config = RunConfig(
                # streaming_mode=stream_mode,
                max_llm_calls=int(getenv("MODEL_AGENT_MAX_LLM_CALLS", 100)),
            )
        logger.info(f"Run config: {run_config}")

        user_id = user_id or self.user_id

        converted_messages: list = _convert_messages(
            messages, self.app_name, user_id, session_id
        )

        if self.short_term_memory:
            session = await self.short_term_memory.create_session(
                app_name=self.app_name, user_id=user_id, session_id=session_id
            )
            assert session, (
                f"Failed to create session with app_name={self.app_name}, user_id={user_id}, session_id={session_id}, "
            )
            logger.debug(
                f"Auto create session: {session.id}, user_id: {session.user_id}, app_name: {self.app_name}"
            )

        final_output = ""
        for converted_message in converted_messages:
            try:
                async for event in self.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=converted_message,
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
                        final_output = event.content.parts[0].text
                        logger.debug(f"Event output: {final_output}")
            except LlmCallsLimitExceededError as e:
                logger.warning(f"Max number of llm calls limit exceeded: {e}")
                final_output = ""

        # try to save tracing file
        if save_tracing_data:
            self.save_tracing_file(session_id)

        self._print_trace_id()

        if upload_inline_data_to_tos:
            self.upload_inline_data_to_tos = _upload_inline_data_to_tos  # type: ignore

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

    async def save_session_to_long_term_memory(
        self, session_id: str, user_id: str = "", app_name: str = ""
    ) -> None:
        if not self.long_term_memory:
            logger.warning("Long-term memory is not enabled. Failed to save session.")
            return

        if not user_id:
            user_id = self.user_id

        if not app_name:
            app_name = self.app_name

        session = await self.session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )

        if not session:
            logger.error(
                f"Session {session_id} (app_name={app_name}, user_id={user_id}) not found in session service, cannot save to long-term memory."
            )
            return

        await self.long_term_memory.add_session_to_memory(session)
        logger.info(f"Add session `{session.id}` to long term memory.")
