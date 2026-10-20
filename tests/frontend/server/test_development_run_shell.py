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
import json
import shlex

import pytest

from frontend.server.intelligent_development_runs.shell import command_wrapper


@pytest.mark.asyncio
async def test_lost_submission_response_does_not_repeat_remote_effect(tmp_path):
    root = tmp_path / "receipt"
    output = tmp_path / "effect"
    program = f"from pathlib import Path; import json,time; p=Path({str(output)!r}); p.write_text(p.read_text()+'x' if p.exists() else 'x'); time.sleep(0.1); print(json.dumps({{'ok':True}}))"
    command = command_wrapper(str(root), f"python3 -c {shlex.quote(program)}", 5)
    first = await asyncio.create_subprocess_shell(command)
    duplicate = await asyncio.create_subprocess_shell(command)
    await asyncio.gather(first.wait(), duplicate.wait())
    retry = await asyncio.create_subprocess_shell(command)
    assert await retry.wait() == 0
    assert output.read_text() == "x"
    receipt = json.loads((root / "result.json").read_text())
    assert receipt["status"] == "completed" and receipt["exitCode"] == 0
    assert json.loads(receipt["output"]) == {"ok": True}


@pytest.mark.asyncio
async def test_stop_before_delayed_submission_prevents_execution(tmp_path):
    root = tmp_path / "receipt"
    root.mkdir()
    (root / "stop").touch()
    effect = tmp_path / "effect"
    process = await asyncio.create_subprocess_shell(
        command_wrapper(str(root), f"touch {shlex.quote(str(effect))}", 5)
    )
    assert await process.wait() == 0
    assert not effect.exists()
    assert json.loads((root / "result.json").read_text())["status"] == "cancelled"


@pytest.mark.asyncio
async def test_stop_running_command_terminates_group_and_records_receipt(tmp_path):
    root = tmp_path / "receipt"
    process = await asyncio.create_subprocess_shell(
        command_wrapper(str(root), "sleep 30", 35)
    )

    async def stop_running_command():
        while not (root / "output").exists():
            await asyncio.sleep(0.01)
        (root / "stop").touch()
        return await process.wait()

    assert await asyncio.wait_for(stop_running_command(), 3) == 0
    receipt = json.loads((root / "result.json").read_text())
    assert receipt["status"] == "cancelled" and receipt["exitCode"] != 0
