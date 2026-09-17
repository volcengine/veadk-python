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

"""Reconcile delivery commands across HTTP loss and executor restarts.

The native command ID supports wait. A remote receipt and exclusive lock close
the gap before that ID is received: submitting the same wrapper cannot execute
the underlying command twice. An abandoned receipt requires intervention.
"""

from __future__ import annotations

import asyncio
import json
import shlex
from typing import TYPE_CHECKING, Any

from .models import Run
from .repository import RunRepository

if TYPE_CHECKING:
    from frontend.server.sandbox_remote import SandboxRemoteTransport


class CommandUnconfirmed(RuntimeError):
    pass


def command_wrapper(root: str, command: str, timeout: int) -> str:
    # No credentials or user content are embedded here. The command names only
    # the delivery worker and its private request path.
    source = f"""
import fcntl,json,os,signal,subprocess,time
root={root!r}
os.makedirs(root,mode=0o700,exist_ok=True)
lock=open(root+'/lock','a')
try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError: raise SystemExit(0)
if os.path.exists(root+'/result.json'): raise SystemExit(0)
if os.path.exists(root+'/started'): raise SystemExit(2)
open(root+'/started','x').close()
result={{'status':'cancelled','exitCode':None,'output':''}}
if not os.path.exists(root+'/stop'):
 with open(root+'/output','w+b') as output:
  process=subprocess.Popen({command!r},shell=True,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
  deadline=time.monotonic()+{timeout!r}
  cancelled=False
  while process.poll() is None:
   if os.path.exists(root+'/stop') or time.monotonic()>=deadline or output.tell()>16*1024*1024:
    cancelled=True
    os.killpg(process.pid,signal.SIGTERM)
    try: process.wait(timeout=3)
    except subprocess.TimeoutExpired:
     os.killpg(process.pid,signal.SIGKILL)
     process.wait()
    break
   time.sleep(0.2)
  output.seek(0)
  result={{'status':'cancelled' if cancelled else 'completed','exitCode':process.returncode,'output':output.read(16*1024*1024).decode('utf-8',errors='replace')}}
with open(root+'/result.tmp','w') as stream:
 json.dump(result,stream)
 stream.flush()
 os.fsync(stream.fileno())
os.replace(root+'/result.tmp',root+'/result.json')
"""
    return f"python3 -c {shlex.quote(source)}"


class RunShell:
    def __init__(
        self,
        repository: RunRepository,
        run: Run,
        token: str,
        transport: SandboxRemoteTransport,
        root: str,
    ):
        self.repository, self.run, self.token, self.transport, self.root = (
            repository,
            run,
            token,
            transport,
            root,
        )

    async def _state(self) -> dict[str, Any]:
        source = (
            "import json,os\n"
            f"root={self.root!r}\n"
            "path=root+'/result.json'\n"
            "if os.path.exists(path):\n"
            " with open(path) as stream: result=json.load(stream)\n"
            "else: result={'status':'pending'}\n"
            "print(json.dumps(result))\n"
        )
        return await self.transport.exec_json(
            f"python3 -c {shlex.quote(source)}", timeout=15
        )

    async def stop(self) -> None:
        source = f"import os; os.makedirs({self.root!r},mode=0o700,exist_ok=True); open({self.root + '/stop'!r},'a').close()"
        await self.transport.exec_text(f"python3 -c {shlex.quote(source)}", timeout=15)

    async def execute(self, command: str, *, timeout: int) -> dict[str, Any]:
        owner, run_id = self.run.owner_id, self.run.id
        current = await self.repository.get(owner, run_id)
        key = self.root.rsplit("/", 1)[-1]
        command_id = str(current.checkpoint.get(key, ""))
        state = await self._state()
        if state.get("status") == "pending" and not command_id:
            if current.stop_requested:
                await self.stop()
            # Retrying this wrapper is safe even if the first HTTP response was
            # lost: its remote lock + started marker prevent duplicate execution.
            await self.repository.checkpoint(
                owner, run_id, self.token, **{f"{key}_submitted": True}
            )
            data = await self.transport.start_command(
                command_wrapper(self.root, command, timeout), hard_timeout=timeout + 15
            )
            command_id = str(data.get("session_id") or "")
            if command_id:
                await self.repository.checkpoint(
                    owner, run_id, self.token, **{key: command_id}
                )
        for _ in range(timeout + 20):
            current = await self.repository.get(owner, run_id)
            await self.repository.heartbeat(owner, run_id, self.token)
            if current.stop_requested:
                await self.stop()
            state = await self._state()
            if state.get("status") != "pending":
                break
            if command_id:
                await self.transport.wait_command(command_id)
            else:
                await asyncio.sleep(1)
        else:
            raise CommandUnconfirmed("Delivery command has no confirmed receipt")
        if state.get("status") != "completed" or state.get("exitCode") != 0:
            raise CommandUnconfirmed("Delivery command did not complete successfully")
        try:
            result = json.loads(state["output"])
        except (KeyError, ValueError, TypeError) as error:
            raise CommandUnconfirmed("Delivery command result is invalid") from error
        if not isinstance(result, dict):
            raise CommandUnconfirmed("Delivery command result is invalid")
        return result

    async def confirm_stopped(self) -> bool:
        await self.stop()
        state = await self._state()
        return state.get("status") in {"completed", "cancelled"}
