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

"""Buffer credential boundaries before any streamed text reaches SQLite."""

from dataclasses import replace

from veadk.cli.codex_app_server import CodexAppServerEvent


class TaskTextProjection:
    def __init__(self, secrets: tuple[str, ...]) -> None:
        self.secrets = tuple(value for value in secrets if value)
        self.pending: dict[str, str] = {}
        self.visible: dict[str, str] = {}
        self.events: dict[str, CodexAppServerEvent] = {}

    def apply(
        self, event: CodexAppServerEvent, turn_id: str, *, snapshot_only: bool = False
    ) -> CodexAppServerEvent:
        item_id = event.item_id or f"assistant:{turn_id}"
        self.events[item_id] = event
        prior = self.pending.get(item_id, "")
        is_delta = event.kind in {"text", "tool_output"}
        text = prior + event.text if is_delta else event.text
        if not is_delta and prior.startswith(text):
            text = prior
        self.pending[item_id] = text
        final = event.kind == "assistant_final" or (
            event.kind in {"text_snapshot", "commentary", "thinking"}
            and event.status == "done"
        )
        if snapshot_only:
            return replace(
                event, item_id=item_id, text=self._public(text, final), turn_id=turn_id
            )
        return self._emit(event, item_id, self._public(text, final), turn_id)

    def _emit(
        self, event: CodexAppServerEvent, item_id: str, visible: str, turn_id: str
    ) -> CodexAppServerEvent:
        prior = self.visible.get(item_id)
        self.visible[item_id] = visible
        # The first native snapshot replaces previously persisted text on recovery.
        # Subsequent stable suffixes avoid storing the whole answer for each token.
        if (prior is not None and visible.startswith(prior)) or (
            prior is None and event.kind in {"text", "tool_output"}
        ):
            return replace(
                event,
                kind="tool_output" if event.kind.startswith("tool_output") else "text",
                item_id=item_id,
                text=visible[len(prior or "") :],
                turn_id=turn_id,
            )
        return replace(
            event,
            kind="tool_output_snapshot"
            if event.kind.startswith("tool_output")
            else "text_snapshot",
            item_id=item_id,
            text=visible,
            turn_id=turn_id,
        )

    def _public(self, text: str, final: bool) -> str:
        end = (
            len(text)
            if final
            else max(0, len(text) - max(map(len, self.secrets), default=1) + 1)
        )
        for secret in self.secrets:
            position = text.find(secret)
            while position >= 0:
                if position < end < position + len(secret):
                    end = position
                position = text.find(secret, position + 1)
        visible = text[:end]
        for secret in sorted(self.secrets, key=len, reverse=True):
            visible = visible.replace(secret, "***")
        return visible

    def finish(self, turn_id: str) -> list[CodexAppServerEvent]:
        return [
            replace(
                self.events[item],
                kind="tool_output_snapshot"
                if self.events[item].kind.startswith("tool_output")
                else "text_snapshot",
                item_id=item,
                text=self._public(text, True),
                turn_id=turn_id,
            )
            for item, text in self.pending.items()
        ]
