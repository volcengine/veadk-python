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

import asyncio
import sys
from typing import Callable


from veadk.tracing.telemetry.telemetry import (
    trace_call_llm,
    trace_send_data,
    trace_tool_call,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def patch_asyncio():
    """Patch asyncio to ignore 'Event loop is closed' error.

    After invoking MCPToolset, we met the `RuntimeError: Event loop is closed` error. Related issue see:
    - https://github.com/google/adk-python/issues/1429
    - https://github.com/google/adk-python/pull/1420
    """
    original_del = asyncio.base_subprocess.BaseSubprocessTransport.__del__

    def patched_del(self):
        try:
            original_del(self)
        except RuntimeError as e:
            if "Event loop is closed" not in str(e):
                raise

    asyncio.base_subprocess.BaseSubprocessTransport.__del__ = patched_del

    from anyio._backends._asyncio import CancelScope

    original_cancel_scope_exit = CancelScope.__exit__

    def patched_cancel_scope_exit(self, exc_type, exc_val, exc_tb):
        try:
            return original_cancel_scope_exit(self, exc_type, exc_val, exc_tb)
        except RuntimeError as e:
            if (
                "Attempted to exit cancel scope in a different task than it was entered in"
                in str(e)
            ):
                return False
            raise

    CancelScope.__exit__ = patched_cancel_scope_exit


def patch_google_adk_telemetry() -> None:
    trace_functions = {
        "trace_tool_call": trace_tool_call,
        "trace_call_llm": trace_call_llm,
        "trace_send_data": trace_send_data,
    }

    for mod_name, mod in sys.modules.items():
        if mod_name.startswith("google.adk"):
            for var_name in dir(mod):
                var = getattr(mod, var_name, None)
                if var_name in trace_functions.keys() and isinstance(var, Callable):
                    setattr(mod, var_name, trace_functions[var_name])
                    logger.debug(
                        f"Patch {mod_name} {var_name} with {trace_functions[var_name]}"
                    )
