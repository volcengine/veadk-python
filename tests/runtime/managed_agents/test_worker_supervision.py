"""Run the real shell supervisor and health server with a controlled worker."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("stop_mode", ["terminate", "worker_failure"])
@pytest.mark.parametrize("entrypoint_mode", ["worker", "claimed"])
def test_supervisor_starts_listener_and_propagates_worker_exit(
    tmp_path, stop_mode, entrypoint_mode
):
    executable = tmp_path / "python-controlled"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import os,sys,time\nfrom pathlib import Path\n"
        "root=Path(os.environ['TEST_RECORD_DIR'])\n"
        "role='listener' if sys.argv[2].endswith('.health') else 'worker'\n"
        "(root / (role+'.pid')).write_text(str(os.getpid()))\n"
        "(root / (role+'.args')).write_text(' '.join(sys.argv[1:]))\n"
        "if role=='listener': os.execv(sys.executable,[sys.executable]+sys.argv[1:])\n"
        "while not (root/'fail').exists(): time.sleep(0.02)\n"
        "sys.exit(23)\n"
    )
    executable.chmod(0o755)
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    env = dict(
        os.environ,
        TEST_RECORD_DIR=str(tmp_path),
        MANAGED_AGENTS_PYTHON=str(executable),
        MA_RUNTIME_PORT=str(port),
        MA_RUNTIME_HOST="127.0.0.1",
        MANAGED_AGENT_ENTRYPOINT_MODE=entrypoint_mode,
    )
    env.pop("AGENTKIT_RUNTIME_PORT", None)
    env.pop("AGENTKIT_RUNTIME_HOST", None)
    process = subprocess.Popen(
        [
            "bash",
            str(ROOT / "docker/managed-agents/run-runtime.sh"),
            "--worker-id",
            "test-worker",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(trust_env=False, timeout=0.5) as client:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                assert process.poll() is None, "Supervisor exited during startup"
                try:
                    if (
                        client.get(f"http://127.0.0.1:{port}/ping")
                    ).status_code == 200 and (tmp_path / "worker.args").exists():
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.05)
            else:
                raise AssertionError("Listener and worker did not start")
        expected_mode = (
            "--managed-agent-worker"
            if entrypoint_mode == "worker"
            else "--managed-agent-work-item"
        )
        assert (
            (tmp_path / "worker.args").read_text()
            == f"-m veadk.runtime.managed_agents.worker {expected_mode} --worker-id test-worker"
        )
        if stop_mode == "terminate":
            process.terminate()
            expected = 143
        else:
            (tmp_path / "fail").touch()
            expected = 23
        assert process.wait(timeout=10) == expected
        for role in ("listener", "worker"):
            with pytest.raises(ProcessLookupError):
                os.kill(int((tmp_path / f"{role}.pid").read_text()), 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        for role in ("listener", "worker"):
            path = tmp_path / f"{role}.pid"
            if path.exists():
                try:
                    os.kill(int(path.read_text()), 9)
                except ProcessLookupError:
                    pass
