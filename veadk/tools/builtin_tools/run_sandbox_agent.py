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

import json
import os
import re
from typing import Optional

from google.adk.tools import ToolContext

from veadk.tools.builtin_tools._agentkit import invoke_agentkit_run_code
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_ENV_VAR_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PROTECTED_ENV_VARS = frozenset({"TOOL_USER_SESSION_ID", "USER_SESSION_ID"})


def _merge_execution_env_vars(
    base_env_vars: dict[str, str],
    custom_env_vars: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Validate and merge environment variables for one sandbox execution."""
    merged_env_vars = dict(base_env_vars)
    if not custom_env_vars:
        return merged_env_vars

    for key, value in custom_env_vars.items():
        if not isinstance(key, str) or not _ENV_VAR_NAME_PATTERN.fullmatch(key):
            raise ValueError(
                f"Invalid environment variable name {key!r}. "
                "Names must match [A-Za-z_][A-Za-z0-9_]*."
            )
        if key in _PROTECTED_ENV_VARS:
            raise ValueError(f"Environment variable {key!r} is managed by VeADK.")
        if not isinstance(value, str):
            raise TypeError(f"Environment variable {key!r} must have a string value.")
        if "\x00" in value:
            raise ValueError(f"Environment variable {key!r} contains a null byte.")

        merged_env_vars[key] = value

    return merged_env_vars


def _clean_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences (color codes, etc.)."""
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


def _format_execution_result(result_str: str) -> str:
    """Format execution result and normalize sandbox output."""
    try:
        result_json = json.loads(result_str)

        if not result_json.get("success"):
            message = result_json.get("message", "Unknown error")
            outputs = result_json.get("data", {}).get("outputs", [])
            if outputs and isinstance(outputs[0], dict):
                error_msg = outputs[0].get("ename", "Unknown error")
                return f"Execution failed: {message}, {error_msg}"

        outputs = result_json.get("data", {}).get("outputs", [])
        if not outputs:
            return "No output generated"

        formatted_lines = []
        for output in outputs:
            if output and isinstance(output, dict) and "text" in output:
                text = output["text"]
                text = _clean_ansi_codes(text)
                text = text.replace("\\n", "\n")
                formatted_lines.append(text)

        return "".join(formatted_lines).strip()

    except json.JSONDecodeError:
        return _clean_ansi_codes(result_str)
    except Exception as e:
        logger.warning(f"Error formatting result: {e}, returning raw result")
        return result_str


def _build_agent_command(
    workflow_prompt: str, skills: Optional[list[str]] = None
) -> list[str]:
    cmd = ["python", "agent.py", workflow_prompt]
    if skills:
        cmd.extend(["--skills"] + skills)
    return cmd


def _build_agent_runner_code(
    cmd: list[str],
    timeout: int,
    env_vars: dict[str, str],
    working_dir: str = "/home/gem/veadk_skills",
) -> str:
    effective_timeout = max(1, timeout - 10)
    return f"""
import subprocess
import os
import time
import select
import sys

env = os.environ.copy()
srv_pythonpath = env.get("SRV_PYTHONPATH")
if srv_pythonpath:
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (srv_pythonpath, env.get("PYTHONPATH")) if value
    )
for key, value in {env_vars!r}.items():
    env[key] = value

process = subprocess.Popen(
    {cmd!r},
    cwd={working_dir!r},
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    env=env,
    bufsize=1,
    universal_newlines=True
)

start_time = time.time()
timeout = {effective_timeout}

with open('/tmp/agent.log', 'w') as log_file:
    while True:
        if time.time() - start_time > timeout:
            process.kill()
            log_file.write('log_type=stderr request_id=x function_id=y revision_number=1 Process timeout\\n')
            print("Process timeout", end='', file=sys.stderr)
            break

        reads = [process.stdout.fileno(), process.stderr.fileno()]
        ret = select.select(reads, [], [], 1)

        for fd in ret[0]:
            if fd == process.stdout.fileno():
                line = process.stdout.readline()
                if line:
                    log_file.write(f'log_type=stdout request_id=x function_id=y revision_number=1 {{line}}')
                    log_file.flush()
                    print(line, end='')
            if fd == process.stderr.fileno():
                line = process.stderr.readline()
                if line:
                    log_file.write(f'log_type=stderr request_id=x function_id=y revision_number=1 {{line}}')
                    log_file.flush()
                    print(line, end='', file=sys.stderr)

        if process.poll() is not None:
            break

    for line in process.stdout:
        log_file.write(f'log_type=stdout request_id=x function_id=y revision_number=1 {{line}}')
        print(line, end='')
    for line in process.stderr:
        log_file.write(f'log_type=stderr request_id=x function_id=y revision_number=1 {{line}}')
        print(line, end='', file=sys.stderr)
"""


def run_sandbox_agent(
    workflow_prompt: str,
    tool_id: str,
    tool_context: ToolContext = None,
    skills: Optional[list[str]] = None,
    timeout: int = 900,
    working_dir: str = "/home/gem/veadk_skills",
    extra_env_vars: Optional[dict[str, str]] = None,
) -> str:
    """Run a remote sandbox agent with an explicit tool_id."""
    if tool_context is None:
        raise ValueError("tool_context is required for run_sandbox_agent")

    session_id = tool_context._invocation_context.session.id
    agent_name = tool_context._invocation_context.agent.name
    user_id = tool_context._invocation_context.user_id
    tool_user_session_id = agent_name + "_" + user_id + "_" + session_id
    logger.debug(f"tool_user_session_id: {tool_user_session_id}")

    base_env_vars = {
        "TOOL_USER_SESSION_ID": tool_user_session_id,
    }
    skill_space_id = os.getenv("SKILL_SPACE_ID", "")
    if skill_space_id:
        base_env_vars["SKILL_SPACE_ID"] = skill_space_id
    env_vars = _merge_execution_env_vars(base_env_vars, extra_env_vars)

    logger.debug(
        f"Run sandbox agent in session_id={session_id}, tool_id={tool_id}, timeout={timeout}, skills={skills}"
    )

    cmd = _build_agent_command(workflow_prompt=workflow_prompt, skills=skills)
    code = _build_agent_runner_code(
        cmd=cmd,
        timeout=timeout,
        env_vars=env_vars,
        working_dir=working_dir,
    )
    res = invoke_agentkit_run_code(
        tool_id=tool_id,
        tool_user_session_id=tool_user_session_id,
        code=code,
        timeout=timeout,
        kernel_name="python3",
        tool_state=tool_context.state if tool_context else None,
    )
    # The response can echo the submitted runner code, including custom env values.
    logger.debug("Invoke run sandbox agent completed")

    try:
        return _format_execution_result(res["Result"]["Result"])
    except KeyError as e:
        logger.error(
            f"Error occurred while running sandbox agent: {e}, response is {res}"
        )
        return res
