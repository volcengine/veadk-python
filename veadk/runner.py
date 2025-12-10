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
from veadk.processors.base_run_processor import BaseRunProcessor
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
    """Pre-run hook invoked before agent execution.

    Iterates over all ``parts`` of ``new_message`` and, when a ``part`` contains
    ``inline_data`` and uploading is enabled, calls ``process_func`` to process
    the data (for example, upload to TOS and rewrite with an accessible URL).
    Typically used together with the ``intercept_new_message`` decorator.

    Args:
        self: Runner instance.
        process_func: An async processing function with a signature like
            ``(part, app_name, user_id, session_id)`` used to handle
            ``inline_data`` in the message (e.g., upload to TOS).
        new_message (google.genai.types.Content): Incoming user message.
        user_id (str): User identifier.
        session_id (str): Session identifier.

    Returns:
        None

    Raises:
        Exception: Propagated if ``process_func`` raises and does not handle it.
    """
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
    """Post-run hook executed after agent run.

    This is currently a no-op placeholder and can be extended to perform
    cleanup or finalize logic after a run.

    Args:
        self: Runner instance.

    Returns:
        None

    Raises:
        None
    """
    return


def intercept_new_message(process_func):
    """Create a decorator to insert pre/post hooks around ``run_async`` calls.

    Internally it invokes :func:`pre_run_process` to preprocess the incoming
    message (e.g., upload image/video inline data to TOS), then iterates the
    underlying event stream and finally calls :func:`post_run_process`.

    Args:
        process_func: Async function used to process ``inline_data`` (typically
            ``_upload_image_to_tos``).

    Returns:
        Callable: A decorator that can wrap ``run_async``.

    Raises:
        Exception: May propagate exceptions raised by the wrapped function or
            the pre-processing step.
    """

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
                event_metadata = f"| agent_name: {event.author} , user_id: {user_id} , session_id: {session_id} , invocation_id: {event.invocation_id}"
                if event.get_function_calls():
                    for function_call in event.get_function_calls():
                        logger.debug(f"Function call: {function_call} {event_metadata}")
                elif event.get_function_responses():
                    for function_response in event.get_function_responses():
                        logger.debug(
                            f"Function response: {function_response} {event_metadata}"
                        )
                elif (
                    event.content is not None
                    and event.content.parts
                    and event.content.parts[0].text is not None
                    and len(event.content.parts[0].text.strip()) > 0
                ):
                    final_output = event.content.parts[0].text
                    logger.debug(f"Event output: {final_output} {event_metadata}")

            post_run_process(self)

        return wrapper

    return decorator


def _convert_messages(
    messages: RunnerMessage,
    app_name: str,
    user_id: str,
    session_id: str,
) -> list:
    """Convert a VeADK ``RunnerMessage`` into a list of Google ADK messages.

    Supported inputs:
    - ``str``: Single-turn text prompt.
    - :class:`veadk.types.MediaMessage`: Single-turn multimodal prompt (text + image/video).
    - ``list``: A list of the above types (multi-turn with mixed text and multimodal).

    For multimodal inputs, this reads the local media file bytes and detects
    the MIME type via ``filetype``; only ``image/*`` and ``video/*`` are supported.

    Args:
        messages (RunnerMessage): Input message or list of messages to convert.
        app_name (str): App name (not directly used; kept for consistency with upload path).
        user_id (str): User ID (not directly used; kept for consistency with upload path).
        session_id (str): Session ID (not directly used; kept for consistency with upload path).

    Returns:
        list[google.genai.types.Content]: Converted ADK messages.

    Raises:
        ValueError: If the message type is unknown or media type is unrecognized.
        AssertionError: If the media MIME type is not supported (only image/* and video/*).

    Note:
        This function only performs structural conversion. To upload inline media
        to an object store and rewrite URLs, use it together with
        ``intercept_new_message`` and ``_upload_image_to_tos``.
    """
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
    """Upload inline media data in a message part to TOS and rewrite its URL.

    When ``part.inline_data`` has both ``display_name`` (original filename) and
    ``data`` (bytes), it generates an object storage path based on
    ``app_name``, ``user_id`` and ``session_id``. After upload, it replaces
    ``display_name`` with a signed URL.

    Args:
        part (google.genai.types.Part): Message part containing ``inline_data``.
        app_name (str): App name.
        user_id (str): User ID.
        session_id (str): Session ID.

    Returns:
        None

    Raises:
        None: All exceptions are caught and logged; nothing is propagated.
    """
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
    """VeADK Runner that augments ADK with session, memory, tracing, and media upload.

    This class builds on Google ADK's ``Runner`` and adds:
    - Integration with short-term memory (ShortTermMemory) for auto session management.
    - Optional long-term memory integration and session persistence.
    - New message interception and media upload to TOS.
    - Tracing dump and Trace ID logging.
    - A simplified ``run`` entry that supports multi-turn text/multimodal inputs.

    Attributes:
        user_id (str): Default user ID.
        long_term_memory: Long-term memory service instance, or ``None`` if not set.
        short_term_memory (veadk.memory.short_term_memory.ShortTermMemory | None):
            Short-term memory instance used to auto-create/manage sessions.
        upload_inline_data_to_tos (bool): Whether to upload inline media to TOS while running.
        session_service: Session service instance (may come from short-term memory).
        memory_service: Memory service instance (may come from agent's long-term memory).
        app_name (str): Application name used in session management and object pathing.

    Note:
        This class wraps the parent ``run_async`` at initialization to insert media
        upload and post-run handling. If you override the underlying ``run_async``,
        ensure it remains compatible with this interception logic.
    """

    def __init__(
        self,
        agent: BaseAgent | Agent | None = None,
        short_term_memory: ShortTermMemory | None = None,
        app_name: str | None = None,
        user_id: str = "veadk_default_user",
        upload_inline_data_to_tos: bool = False,
        run_processor: "BaseRunProcessor | None" = None,
        *args,
        **kwargs,
    ) -> None:
        """Initialize a Runner instance.

        Selects the session service based on provided short-term memory or an
        external ``session_service``. If long-term memory or an external
        ``memory_service`` is provided, the passed service is preferred. After
        construction, it injects a message interception layer into the parent's
        ``run_async`` to support inline media upload and post-run handling.

        Args:
            agent (google.adk.agents.base_agent.BaseAgent | veadk.agent.Agent):
                The agent instance used to run interactions.
            short_term_memory (ShortTermMemory | None): Optional short-term memory; if
                not provided and no external `session_service` is supplied, an in-memory
                session service will be created.
            app_name (str): Application name. Defaults to `veadk_default_app`.
            user_id (str): Default user ID. Defaults to `veadk_default_user`.
            upload_inline_data_to_tos (bool): Whether to enable inline media upload. Defaults to `False`.
            run_processor (BaseRunProcessor | None): Optional run processor for intercepting agent execution.
                If not provided, will try to get from agent. If agent doesn't have one, uses NoOpRunProcessor.
            *args: Positional args passed through to `ADKRunner`.
            **kwargs: Keyword args passed through to `ADKRunner`; may include
                ``session_service`` and ``memory_service`` to override defaults.

        Returns:
            None

        Raises:
            None
        """
        self.user_id = user_id
        self.long_term_memory = None
        self.short_term_memory = short_term_memory
        self.upload_inline_data_to_tos = upload_inline_data_to_tos
        credential_service = kwargs.pop("credential_service", None)
        session_service = kwargs.pop("session_service", None)
        memory_service = kwargs.pop("memory_service", None)

        # Handle run_processor: priority is runner arg > agent.run_processor > NoOpRunProcessor
        if run_processor is not None:
            self.run_processor = run_processor
        elif hasattr(agent, "run_processor") and agent.run_processor is not None:  # type: ignore
            self.run_processor = agent.run_processor  # type: ignore
        else:
            from veadk.processors import NoOpRunProcessor

            self.run_processor = NoOpRunProcessor()

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

        # For forward compatibility, we pass app_name to ADKRunner.
        if not kwargs.get("app") and not app_name:
            app_name = "veadk_default_app"

        super().__init__(
            agent=agent,
            session_service=session_service,
            memory_service=memory_service,
            credential_service=credential_service,
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
        run_processor: "BaseRunProcessor | None" = None,
    ):
        """Run a conversation with multi-turn text and multimodal inputs.

        When short-term memory is configured, a session is auto-created as needed.
        Inputs are converted into ADK message format. If ``upload_inline_data_to_tos``
        is ``True``, media upload is enabled temporarily for this run (does not change
        the Runner's global setting).

        Args:
            messages (RunnerMessage): Input messages (``str``, ``MediaMessage`` or a list of them).
            user_id (str): Override default user ID; if empty, uses the constructed ``user_id``.
            session_id (str): Session ID. Defaults to a timestamp-based temporary ID.
            run_config (google.adk.agents.RunConfig | None): Run config; if ``None``, a default
                config is created using the environment var ``MODEL_AGENT_MAX_LLM_CALLS``.
            save_tracing_data (bool): Whether to dump tracing data to disk after the run. Defaults to ``False``.
            upload_inline_data_to_tos (bool): Whether to enable media upload only for this run. Defaults to ``False``.
            run_processor (BaseRunProcessor | None): Optional run processor to use for this run.
                If not provided, uses the runner's default run_processor. Defaults to None.

        Returns:
            str: The textual output from the last event, if present; otherwise an empty string.

        Raises:
            ValueError: If an input contains an unsupported or unrecognized media type.
            AssertionError: If a media MIME type is not among ``image/*`` or ``video/*``.
            Exception: Exceptions from the underlying ADK/Agent execution may propagate.
        """
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

        import uuid

        x_session_id = f"{self.agent.name}_{user_id}_{session_id or uuid.uuid4()}"
        self._inject_header_to_tools(x_session_id=x_session_id)
        final_output = ""
        for converted_message in converted_messages:
            try:

                @(run_processor or self.run_processor).process_run(
                    runner=self, message=converted_message
                )
                async def event_generator():
                    async for event in self.run_async(
                        user_id=user_id,
                        session_id=session_id,
                        new_message=converted_message,
                        run_config=run_config,
                    ):
                        yield event

                async for event in event_generator():
                    if (
                        event.content is not None
                        and event.content.parts
                        and event.content.parts[0].text is not None
                        and len(event.content.parts[0].text.strip()) > 0
                    ):
                        final_output = event.content.parts[0].text
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
        """Get the Trace ID from the current agent's tracer.

        If the agent is not a :class:`veadk.agent.Agent` or no tracer is configured,
        returns ``"<unknown_trace_id>"``.

        Returns:
            str: The Trace ID or ``"<unknown_trace_id>"``.

        Raises:
            None
        """
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
        """Log the current tracer's Trace ID.

        If the agent is not a :class:`veadk.agent.Agent` or no tracer is configured,
        nothing is printed.

        Returns:
            None

        Raises:
            None
        """
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
        """Dump tracing data to disk and return the last written path.

        Only effective when the agent is one of
        Agent/SequentialAgent/ParallelAgent/LoopAgent and a tracer is configured;
        otherwise returns an empty string.

        Args:
            session_id (str): Session ID used to associate the tracing with a session.

        Returns:
            str: The tracing file path; returns an empty string on failure or when no tracer.

        Examples:
            You can save the tracing data to a local file.

            ```python
            import asyncio

            from veadk import Agent, Runner

            agent = Agent()

            runner = Runner(agent=agent)

            session_id = "session"
            asyncio.run(runner.run(messages="Hi!", session_id=session_id))

            path = runner.save_tracing_file(session_id=session_id)
            print(path)
            ```
        """
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
        """Save the current session as part of an evaluation set and return its path.

        Args:
            session_id (str): Session ID.
            eval_set_id (str): Evaluation set identifier. Defaults to ``"default"``.

        Returns:
            str: The exported evaluation set file path.

        Examples:
            You can save the specific session as a evaluation set in Google ADK format.

            ```python
            import asyncio

            from veadk import Agent, Runner

            agent = Agent()

            runner = Runner(agent=agent)

            session_id = "session"
            asyncio.run(runner.run(messages="Hi!", session_id=session_id))

            path = runner.save_eval_set(session_id=session_id)
            print(path)
            ```
        """
        eval_set_recorder = EvalSetRecorder(self.session_service, eval_set_id)
        eval_set_path = await eval_set_recorder.dump(
            self.app_name, self.user_id, session_id
        )
        return eval_set_path

    async def save_session_to_long_term_memory(
        self, session_id: str, user_id: str = "", app_name: str = "", **kwargs
    ) -> None:
        """Save the specified session to long-term memory.

        If ``long_term_memory`` is not configured, the function logs a warning and returns.
        It fetches the session from the session service and then calls the long-term memory's
        ``add_session_to_memory`` for persistence.

        Args:
            session_id (str): Session ID.
            user_id (str): Optional; override default user ID. If empty, uses ``self.user_id``.
            app_name (str): Optional; override default app name. If empty, uses ``self.app_name``.

        Examples:
            You can save a specific session to long-term memory.

            ```python
            import asyncio

            from veadk import Agent, Runner
            from veadk.memory import LongTermMemory

            APP_NAME = "app"

            agent = Agent(long_term_memory=LongTermMemory(backend="local", app_name=APP_NAME))

            session_id = "session"
            runner = Runner(agent=agent, app_name=APP_NAME)

            asyncio.run(runner.run(messages="Hi!", session_id=session_id))

            asyncio.run(runner.save_session_to_long_term_memory(session_id=session_id))
            ```
        """
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

        await self.long_term_memory.add_session_to_memory(session, kwargs=kwargs)
        logger.info(f"Add session `{session.id}` to long term memory.")

    def _inject_header_to_tools(self, x_session_id: str):
        """Auto inject header to McpToolset"""
        from google.adk.tools.mcp_tool import McpToolset

        for tool in self.agent.tools:
            if isinstance(tool, McpToolset):
                original_provider = tool._header_provider
                tool._header_provider = lambda ctx, sid=x_session_id: {
                    **(original_provider(ctx) if original_provider else {}),
                    "x-session-id": sid,
                }
                logger.debug(f"Injected session context to McpToolset: {x_session_id}")
