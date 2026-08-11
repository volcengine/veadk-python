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

"""Select and identify the transient and snapshot-backed Sandbox Tools."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxToolPair:
    """The two Tool ids serving one Studio Sandbox agent kind."""

    transient: str = ""
    persistent: str = ""

    @property
    def configured(self) -> tuple[str, ...]:
        """Return configured ids once, in transient then persistent order."""
        return tuple(dict.fromkeys(filter(None, (self.transient, self.persistent))))

    def select(self, persistent: bool) -> str:
        """Return the Tool id required by the requested persistence mode."""
        return self.persistent if persistent else self.transient

    def is_persistent(self, tool_id: str) -> bool:
        """Whether a Session belongs to the snapshot-backed Tool."""
        return bool(self.persistent and tool_id == self.persistent)
