# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

from __future__ import annotations

import pytest

from frontend.service.studio_scheduler import http_app


@pytest.mark.asyncio
async def test_timer_accepts_byteplus_json_string_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def execute_ready_runs() -> dict[str, int]:
        calls.append("execute")
        return {
            "scanned": 0,
            "queued": 0,
            "started": 1,
            "stale": 0,
            "skipped": 0,
            "failed": 0,
        }

    monkeypatch.setattr(http_app, "execute_ready_runs", execute_ready_runs)

    result = await http_app.handle_timer(
        '{"source":"veadk-studio-cronjobs","phase":"execute"}'
    )

    assert calls == ["execute"]
    assert result["started"] == 1


@pytest.mark.asyncio
async def test_timer_keeps_volcengine_object_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def dispatch_current_minute() -> dict[str, int]:
        return {
            "scanned": 1,
            "queued": 1,
            "started": 0,
            "stale": 0,
            "skipped": 0,
            "failed": 0,
        }

    monkeypatch.setattr(http_app, "dispatch_current_minute", dispatch_current_minute)

    result = await http_app.handle_timer({"phase": "scan"})

    assert result["queued"] == 1


def test_timer_rejects_non_object_json_string() -> None:
    with pytest.raises(ValueError, match="must be a JSON object"):
        http_app._timer_event('"execute"')
