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

"""Run context contracts with synthetic credentials and isolated configuration.

Usage: python tests/run_context_compression_gate.py [pytest arguments]
Install the project and test dependencies in the selected interpreter first.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT"}
    }
    env.update(
        {
            "PYTHONPATH": str(repo),
            "PYTHON_DOTENV_DISABLED": "1",
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
            "HF_HUB_OFFLINE": "1",
            "DO_NOT_TRACK": "1",
            "OTEL_SDK_DISABLED": "true",
            "MODEL_AGENT_API_KEY": "offline-test",
        }
    )
    tests = [
        "tests/context",
        "tests/models",
        "tests/test_agent.py",
        "tests/test_context_release_gate.py",
        "tests/test_ci_failure_summary.py",
        "tests/agent/test_workflow_execution.py",
        "tests/agent/test_workflow_agent_contract.py",
        "tests/agent/test_parallel_cleanup.py",
        "tests/cli/test_generated_agent_request_models.py",
        "tests/cli/test_generated_agent_planner.py",
        "tests/cli/test_generated_agent_backend_codegen.py",
        "tests/integrations/agentkit/test_app.py",
    ]
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--rootdir",
        str(repo),
        "-p",
        "no:cacheprovider",
        "--tb=short",
        "--show-capture=no",
        *[str(repo / name) for name in tests],
        *sys.argv[1:],
    ]
    with tempfile.TemporaryDirectory(prefix="veadk-context-gate-") as cwd:
        # These contracts use fake providers. An accidental SDK default must
        # fail locally, never contact a real model or tracing service in CI.
        Path(cwd, "sitecustomize.py").write_text(
            "import sys\n"
            "def deny_network(event, args):\n"
            "    if event in {'socket.connect', 'socket.connect_ex', 'socket.getaddrinfo'}:\n"
            "        raise RuntimeError('offline_network_denied')\n"
            "sys.addaudithook(deny_network)\n"
        )
        env["PYTHONPATH"] = os.pathsep.join((cwd, str(repo)))
        return subprocess.run(command, cwd=cwd, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
