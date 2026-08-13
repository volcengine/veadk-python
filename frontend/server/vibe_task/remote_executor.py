# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
# Licensed under the Apache License, Version 2.0 (the "License");

from __future__ import annotations

import base64
import json
import shlex

from ..sandbox_remote import SandboxRemoteTransport
from .runner import CommandResult
from .sandbox import VibeSandboxStore


class VibeRemoteExecutor:
    """Execute typed argv in an owner-authorized task workspace."""

    def __init__(self, store: VibeSandboxStore) -> None:
        self.store = store

    async def __call__(
        self,
        owner_id: str,
        task_id: str,
        argv: tuple[str, ...],
        cwd: str,
        timeout: int,
    ) -> CommandResult:
        session = await self.store.find(owner_id, task_id)
        expected = f"/home/gem/workspace/{task_id}"
        if cwd != expected:
            raise ValueError("validation cwd must be the task workspace")
        if not argv or any(not isinstance(item, str) or "\x00" in item for item in argv):
            raise ValueError("validation argv is invalid")
        encoded = base64.b64encode(json.dumps(argv).encode()).decode()
        source = (
            "import base64,json,os,subprocess;"
            f"argv=json.loads(base64.b64decode({encoded!r}));"
            "env=os.environ.copy();secret='/home/gem/.vibe/task/secrets/active.json';"
            "data=json.load(open(secret,encoding='utf-8')) if os.path.isfile(secret) else {};"
            "env.update({k:v for k,v in {'VOLCENGINE_ACCESS_KEY':data.get('accessKeyId'),'VOLCENGINE_SECRET_KEY':data.get('secretAccessKey'),'VOLCENGINE_SESSION_TOKEN':data.get('sessionToken')}.items() if v});"
            f"r=subprocess.run(argv,cwd={cwd!r},env=env,capture_output=True,text=True,"
            f"timeout={timeout!r},check=False);"
            "print(json.dumps({'exitCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},ensure_ascii=False))"
        )
        payload = await SandboxRemoteTransport(session.endpoint).exec_json(
            f"python3 -c {shlex.quote(source)}", timeout=timeout + 10
        )
        exit_code = payload.get("exitCode")
        stdout = payload.get("stdout", "")
        stderr = payload.get("stderr", "")
        if (
            isinstance(exit_code, bool)
            or not isinstance(exit_code, int)
            or not isinstance(stdout, str)
            or not isinstance(stderr, str)
        ):
            raise ValueError("validation command returned invalid result")
        return CommandResult(exit_code, stdout, stderr)
