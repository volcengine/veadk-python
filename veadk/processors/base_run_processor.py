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

"""Base run processor for intercepting and processing agent execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, AsyncGenerator, Callable

if TYPE_CHECKING:
    from google.genai import types
    from veadk.runner import Runner


class BaseRunProcessor(ABC):
    """Abstract base class for runtime processors.

    A run processor can intercept and modify the agent execution flow by wrapping
    the event generator function. This is useful for implementing cross-cutting
    concerns such as:
    - Authentication flows (e.g., OAuth2)
    - Request/response logging
    - Error handling and retry logic
    - Performance monitoring
    - Custom event filtering or transformation

    The processor uses a decorator pattern to wrap the event generator, allowing
    it to:
    1. Intercept events from runner.run_async
    2. Process or modify events
    3. Inject additional events (e.g., authentication requests)
    4. Control the execution flow (e.g., retry loops)

    Example:
        class MyProcessor(BaseRunProcessor):
            def process_run(self, runner, message, **kwargs):
                def decorator(event_generator_func):
                    async def wrapper():
                        # Pre-processing
                        async for event in event_generator_func():
                            # Process each event
                            yield event
                        # Post-processing
                    return wrapper
                return decorator
    """

    @abstractmethod
    def process_run(
        self,
        runner: Runner,
        message: types.Content,
        **kwargs: Any,
    ) -> Callable[[Callable[[], AsyncGenerator]], Callable[[], AsyncGenerator]]:
        """Process the agent run by wrapping the event generator.

        This method returns a decorator that wraps the event generator function.
        The decorator can intercept events, modify them, or inject new events.

        Args:
            runner: The Runner instance executing the agent.
            message: The initial message to send to the agent.
            **kwargs: Additional keyword arguments that may be needed by specific
                     implementations (e.g., task_updater for status updates).

        Returns:
            A decorator function that takes an event generator function and returns
            a wrapped event generator function.

        Example:
            @processor.process_run(runner=runner, message=message)
            async def event_generator():
                async for event in runner.run_async(...):
                    yield event
        """
        pass


class NoOpRunProcessor(BaseRunProcessor):
    """No-op run processor that doesn't modify the event generator.

    This is the default processor used when no specific processing is needed.
    It simply passes through all events without any modification.
    """

    def process_run(
        self,
        runner: Runner,
        message: types.Content,
        **kwargs: Any,
    ) -> Callable[[Callable[[], AsyncGenerator]], Callable[[], AsyncGenerator]]:
        """Return a decorator that does nothing.

        Args:
            runner: The Runner instance (unused).
            message: The initial message (unused).
            **kwargs: Additional keyword arguments (unused).

        Returns:
            A decorator that returns the original function unchanged.
        """

        def decorator(
            event_generator_func: Callable[[], AsyncGenerator]
        ) -> Callable[[], AsyncGenerator]:
            return event_generator_func

        return decorator
