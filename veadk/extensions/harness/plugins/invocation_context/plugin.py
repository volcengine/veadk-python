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

"""Invocation-context plugin for VeADK Runner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from google.adk.models import LlmRequest, LlmResponse
from google.adk.plugins import BasePlugin

from veadk.extensions.harness.modules.invocation_context import (
    HarnessInvocationContextBuilder,
)
from veadk.extensions.harness.plugins._shared.callback_utils import (
    message_from_text,
    run_context_from_callback,
    run_context_from_invocation,
    user_text_from_callback,
)
from veadk.extensions.harness.plugins.content_adapter import (
    append_system_instruction,
    contents_to_messages,
)
from veadk.extensions.harness.schemas import HarnessEvent
from veadk.extensions.harness.stores import HarnessStoreProtocol, InMemoryHarnessStore
from veadk.extensions.harness.utils import stringify_json_value

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext
    from google.adk.agents.invocation_context import InvocationContext
    from google.genai import types


class HarnessInvocationContextPlugin(BasePlugin):
    """Injects task context and guardrails before model calls."""

    def __init__(
        self,
        *,
        context_builder: HarnessInvocationContextBuilder | None = None,
        context_engine: HarnessInvocationContextBuilder | None = None,
        store: HarnessStoreProtocol | None = None,
        profile: str = "default",
    ) -> None:
        super().__init__(name="harness_invocation_context_plugin")
        self.context_builder = (
            context_builder or context_engine or HarnessInvocationContextBuilder()
        )
        self.context_engine = self.context_builder
        self.store = store or InMemoryHarnessStore()
        self.profile = profile

    async def before_model_callback(
        self,
        *,
        callback_context: "CallbackContext",
        llm_request: LlmRequest,
    ) -> LlmResponse | None:
        run_context = run_context_from_callback(
            callback_context,
            profile=self.profile,
        )
        user_text = user_text_from_callback(callback_context)
        history = contents_to_messages(llm_request.contents)
        receipts = self.store.load_receipts(
            run_id=run_context.invocation_id,
            session_id=run_context.session_id,
            limit=8,
        )
        bundle = self.context_builder.prepare_context(
            run_context,
            user_input=user_text,
            history=history,
            receipts=receipts,
            has_tools=bool(llm_request.tools_dict),
        )
        if bundle.header:
            append_system_instruction(llm_request, bundle.header)
            self.store.append_event(
                HarnessEvent(
                    event_type="invocation_context.injected",
                    run_context=run_context,
                    payload={
                        "context_chars": bundle.context_chars,
                        "history_messages": len(history),
                        "receipt_count": len(receipts),
                    },
                )
            )
        return None

    async def on_user_message_callback(
        self,
        *,
        invocation_context: "InvocationContext",
        user_message: "types.Content",
    ) -> "types.Content | None":
        text = stringify_json_value(user_message.model_dump(), max_chars=4000)
        run_context = run_context_from_invocation(
            invocation_context,
            profile=self.profile,
        )
        self.store.append_message(
            run_context.session_id,
            message_from_text("user", text),
        )
        return None
