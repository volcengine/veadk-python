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

"""Public lifecycle wrapper for the private Harness Sidecar runtime artifact."""

from __future__ import annotations

import atexit
import json
import os
import queue
import shlex
import shutil
import subprocess
import tempfile
import threading
import urllib.parse
import warnings
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .failover_proxy import StableHttpRelay
from .runtime_gateway_proxy import RuntimeGatewayHttpRelay
from .sidecar_config import (
    HarnessSidecarConfig,
    SidecarBindingSpec,
    resolve_sidecar_config,
)

RUNTIME_EXECUTABLE = "agentkit-harness-sidecar-runtime"
INSTALL_HINT = "run inside an AgentKit managed cloud runtime"
_SIDECAR_TELEMETRY_ENV = {
    "ENABLE_APMPLUS": "false",
    "ENABLE_COZELOOP": "false",
    "ENABLE_TLS": "false",
    "OTEL_SDK_DISABLED": "true",
}


class HarnessSidecarError(RuntimeError):
    pass


class HarnessSidecarRuntimeUnavailable(HarnessSidecarError):
    pass


@dataclass
class SidecarBinding:
    config: HarnessSidecarConfig
    spec: SidecarBindingSpec
    process: subprocess.Popen[str] | None = None
    config_path: Path | None = None
    stderr_lines: list[str] = field(default_factory=list)
    _environ: MutableMapping[str, str] | None = field(default=None, repr=False)
    _previous_env: dict[str, str | None] = field(default_factory=dict, repr=False)
    _relays: list[StableHttpRelay | RuntimeGatewayHttpRelay] = field(
        default_factory=list, repr=False
    )
    _relay_env_keys: set[str] = field(default_factory=set, repr=False)
    _state_lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _monitor_thread: threading.Thread | None = field(default=None, repr=False)
    _runtime_exit_code: int | None = field(default=None, init=False, repr=False)
    _stopped: bool = field(default=False, init=False, repr=False)

    @property
    def env(self) -> dict[str, str]:
        return dict(self.spec.env)

    def apply_env(
        self, environ: MutableMapping[str, str] | None = None
    ) -> dict[str, str]:
        target = environ if environ is not None else os.environ
        if self._environ is None:
            self._environ = target
            self._previous_env = {key: target.get(key) for key in self.spec.env}
        for key, value in self.spec.env.items():
            target[key] = value
        return self.env

    def stop(self) -> None:
        with self._state_lock:
            if self._stopped:
                return
            self._stopped = True
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.config_path is not None:
            self.config_path.unlink(missing_ok=True)
        for relay in self._relays:
            relay.close()
        self._relays.clear()
        if self._environ is not None:
            for key, previous in self._previous_env.items():
                if self._environ.get(key) != self.spec.env.get(key):
                    continue
                if previous is None:
                    self._environ.pop(key, None)
                else:
                    self._environ[key] = previous
        self._environ = None

    def _configure_failover_relays(self, runtime_env: Mapping[str, str]) -> None:
        if self.config.transport == "apig_runtime_port":
            self._configure_runtime_gateway_relay(runtime_env)
            return
        try:
            model_upstream = (
                self.config.model_proxy.upstream_base_url
                or runtime_env.get(self.config.model_proxy.upstream_base_url_env)
            )
            if self.spec.model_proxy_url and model_upstream:
                relay = StableHttpRelay(self.spec.model_proxy_url, model_upstream)
                self._relays.append(relay)
                self.spec.model_proxy_url = relay.url
                if "MODEL_AGENT_API_BASE" in self.spec.env:
                    self.spec.env["MODEL_AGENT_API_BASE"] = relay.url
                    self._relay_env_keys.add("MODEL_AGENT_API_BASE")

            mcp_upstreams = list(self.config.mcp_gateway.upstreams)
            if not mcp_upstreams:
                mcp_upstreams = _csv_urls(
                    runtime_env.get(self.config.mcp_gateway.upstreams_env)
                )
            if self.spec.mcp_urls and len(self.spec.mcp_urls) == len(mcp_upstreams):
                relay_urls: list[str] = []
                for sidecar_url, direct_url in zip(
                    self.spec.mcp_urls, mcp_upstreams, strict=True
                ):
                    relay = StableHttpRelay(sidecar_url, direct_url)
                    self._relays.append(relay)
                    relay_urls.append(relay.url)
                self.spec.mcp_urls = relay_urls
                if "MCP_URLS" in self.spec.env:
                    self.spec.env["MCP_URLS"] = ",".join(relay_urls)
                    self._relay_env_keys.add("MCP_URLS")
        except Exception:
            for relay in self._relays:
                relay.close()
            self._relays.clear()
            self._relay_env_keys.clear()
            raise

    def _configure_runtime_gateway_relay(self, runtime_env: Mapping[str, str]) -> None:
        endpoint = str(
            runtime_env.get(self.config.runtime_gateway_endpoint_env) or ""
        ).strip()
        api_key = str(
            runtime_env.get(self.config.runtime_gateway_api_key_env) or ""
        ).strip()
        if not endpoint:
            raise HarnessSidecarError("Runtime Gateway endpoint is not configured")
        if not api_key:
            raise HarnessSidecarError("Runtime Gateway API key is not configured")
        if not self.spec.model_proxy_url:
            raise HarnessSidecarError("Sidecar model proxy discovery is missing")
        source_path = urllib.parse.urlsplit(self.spec.model_proxy_url).path
        relay = RuntimeGatewayHttpRelay(
            endpoint,
            source_path=source_path,
            api_key=api_key,
            target_port=self.config.model_proxy.port,
            timeout_seconds=self.config.runtime_gateway_timeout_seconds,
        )
        self._relays.append(relay)
        self.spec.model_proxy_url = relay.url
        if "MODEL_AGENT_API_BASE" in self.spec.env:
            self.spec.env["MODEL_AGENT_API_BASE"] = relay.url
            self._relay_env_keys.add("MODEL_AGENT_API_BASE")

        if not self.config.mcp_gateway.enabled:
            return
        if not self.spec.mcp_urls:
            raise HarnessSidecarError("Sidecar MCP gateway discovery is missing")
        relay_urls: list[str] = []
        for sidecar_url in self.spec.mcp_urls:
            source_path = urllib.parse.urlsplit(sidecar_url).path
            mcp_relay = RuntimeGatewayHttpRelay(
                endpoint,
                source_path=source_path,
                api_key=api_key,
                target_port=self.config.mcp_gateway.port,
                timeout_seconds=self.config.runtime_gateway_timeout_seconds,
            )
            self._relays.append(mcp_relay)
            relay_urls.append(mcp_relay.url)
        self.spec.mcp_urls = relay_urls
        # Keep the Toolset URL/key as Sidecar-only upstream credentials. The
        # application must call the local Runtime Gateway relay with the
        # Runtime key instead of receiving the Toolset key or bypassing APIG.
        self.spec.env["MCP_URLS"] = ",".join(relay_urls)
        self.spec.env["MCP_API_KEY"] = api_key
        self._relay_env_keys.update(("MCP_URLS", "MCP_API_KEY"))

    def _start_runtime_monitor(self) -> None:
        if self.process is None:
            return

        def monitor() -> None:
            exit_code = self.process.wait()
            with self._state_lock:
                if self._stopped:
                    return
                self._runtime_exit_code = exit_code
                for relay in self._relays:
                    relay.activate_fallback()
                self.spec.status = "degraded"
                message = (
                    "Sidecar exited; Runtime Gateway transport remains fail closed"
                    if self.config.transport == "apig_runtime_port"
                    else "Sidecar exited; direct upstream fallback is active"
                )
                self.spec.diagnostics.append(
                    {
                        "component": "harness_sidecar",
                        "status": "degraded",
                        "message": message,
                    }
                )
                self._restore_nonrelay_env()
                if self.config_path is not None:
                    self.config_path.unlink(missing_ok=True)

        self._monitor_thread = threading.Thread(
            target=monitor,
            name="harness-sidecar-runtime-monitor",
            daemon=True,
        )
        self._monitor_thread.start()

    def _restore_nonrelay_env(self) -> None:
        for key, previous in self._previous_env.items():
            if key in self._relay_env_keys:
                continue
            current = self.spec.env.get(key)
            if self._environ is not None and self._environ.get(key) == current:
                if previous is None:
                    self._environ.pop(key, None)
                else:
                    self._environ[key] = previous
            if previous is None:
                self.spec.env.pop(key, None)
            else:
                self.spec.env[key] = previous

    def __enter__(self) -> "SidecarBinding":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.stop()


def start_harness_sidecar(
    config: HarnessSidecarConfig | Mapping[str, Any] | bool | None = None,
    *,
    profile: str | None = None,
    apply_env: bool = False,
    environ: MutableMapping[str, str] | None = None,
    process_env: Mapping[str, str] | None = None,
) -> SidecarBinding:
    resolved = resolve_sidecar_config(config, profile=profile)
    if not resolved.enabled:
        return SidecarBinding(
            config=resolved,
            spec=SidecarBindingSpec(status="disabled", profile=resolved.profile),
        )
    runtime_env = dict(
        process_env
        if process_env is not None
        else (environ if environ is not None else os.environ)
    )
    # The managed application owns its telemetry exporters. Reusing those
    # process-wide flags in the Sidecar child starts a second exporter against
    # the Runtime-local collector and can make Sidecar discovery fail before
    # the application becomes ready. Keep application telemetry untouched and
    # disable only the child process exporters.
    runtime_env.update(_SIDECAR_TELEMETRY_ENV)
    stderr_lines: list[str] = []
    config_path: Path | None = None
    process: subprocess.Popen[str] | None = None
    binding: SidecarBinding | None = None
    try:
        command = _resolve_runtime_command(resolved, runtime_env)
        config_path = _write_runtime_config(resolved)
        process = subprocess.Popen(
            [*command, "serve", "--config", str(config_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=runtime_env,
            bufsize=1,
        )
        _drain_stream(process.stderr, stderr_lines)
        line = _read_startup_line(process, resolved.startup_timeout_seconds)
        discovery = json.loads(line)
        if not isinstance(discovery, dict):
            raise HarnessSidecarError("runtime discovery must be a JSON object")
        spec = SidecarBindingSpec.from_discovery(discovery)
        if spec.status == "error" or (
            spec.status == "degraded" and not resolved.fail_open
        ):
            detail = discovery.get("error") or discovery.get("diagnostics") or line
            raise HarnessSidecarError(f"Harness Sidecar failed to start: {detail}")
        binding = SidecarBinding(
            config=resolved,
            spec=spec,
            process=process,
            config_path=config_path,
            stderr_lines=stderr_lines,
        )
        binding._configure_failover_relays(runtime_env)
        if apply_env:
            binding.apply_env(environ)
        binding._start_runtime_monitor()
        atexit.register(binding.stop)
        return binding
    except Exception as error:
        if binding is not None:
            binding.stop()
        else:
            if config_path is not None:
                config_path.unlink(missing_ok=True)
            if process is not None:
                _terminate_process(process)
        if isinstance(error, HarnessSidecarError):
            raise
        raise HarnessSidecarError(f"Harness Sidecar startup failed: {error}") from error


def export_sidecar_env(
    binding: SidecarBinding,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    result = dict(base_env or {})
    result.update(binding.spec.env)
    return result


def run_with_harness_sidecar(
    config: HarnessSidecarConfig | Mapping[str, Any] | bool | None,
    command: Sequence[str],
    *,
    profile: str | None = None,
    env: Mapping[str, str] | None = None,
    cwd: str | os.PathLike[str] | None = None,
) -> int:
    if not command:
        raise ValueError("a child command is required")
    base_env = dict(env if env is not None else os.environ)
    resolved = resolve_sidecar_config(config, profile=profile)
    try:
        binding = start_harness_sidecar(resolved, environ=base_env)
    except HarnessSidecarError as error:
        if not resolved.fail_open:
            raise
        warnings.warn(
            f"Harness Sidecar unavailable; running command directly: {error}",
            RuntimeWarning,
            stacklevel=2,
        )
        binding = SidecarBinding(
            config=resolved,
            spec=SidecarBindingSpec(status="degraded", profile=resolved.profile),
        )
    with binding:
        child_env = export_sidecar_env(binding, base_env)
        try:
            completed = subprocess.run(list(command), env=child_env, cwd=cwd)
        except KeyboardInterrupt:
            return 130
        return int(completed.returncode)


def doctor_harness_sidecar(
    config: HarnessSidecarConfig | Mapping[str, Any] | bool | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    resolved = resolve_sidecar_config(config)
    process_env = dict(env if env is not None else os.environ)
    command = _resolve_runtime_command(resolved, process_env)
    try:
        completed = subprocess.run(
            [
                *command,
                "doctor",
                "--json",
                "--components",
                ",".join(resolved.required_runtime_components),
            ],
            text=True,
            capture_output=True,
            env=process_env,
            timeout=max(0.1, resolved.startup_timeout_seconds),
        )
    except subprocess.TimeoutExpired as error:
        raise HarnessSidecarError(
            "Harness Sidecar doctor timed out after "
            f"{resolved.startup_timeout_seconds:g}s"
        ) from error
    except OSError as error:
        raise HarnessSidecarError(
            f"Harness Sidecar doctor could not start: {error}"
        ) from error
    try:
        report = json.loads(completed.stdout.strip() or "{}")
    except ValueError as error:
        raise HarnessSidecarError(
            f"invalid doctor response: {completed.stdout or completed.stderr}"
        ) from error
    if completed.returncode != 0:
        raise HarnessSidecarError(
            str(report.get("error") or completed.stderr or "runtime doctor failed")
        )
    return report


def _resolve_runtime_command(
    config: HarnessSidecarConfig, env: Mapping[str, str]
) -> list[str]:
    if config.runtime_command:
        return list(config.runtime_command)
    configured = env.get("AGENTKIT_HARNESS_RUNTIME_COMMAND")
    if configured:
        return shlex.split(configured)
    executable = shutil.which(RUNTIME_EXECUTABLE)
    if executable:
        return [executable]
    raise HarnessSidecarRuntimeUnavailable(
        "AgentKit Harness Sidecar Runtime is not available in this environment. "
        f"The private Runtime is cloud-only; {_install_hint(config)} or disable "
        "harness.sidecar for local debugging."
    )


def _install_hint(_config: HarnessSidecarConfig) -> str:
    return INSTALL_HINT


def _csv_urls(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _write_runtime_config(config: HarnessSidecarConfig) -> Path:
    descriptor, name = tempfile.mkstemp(
        prefix="agentkit-harness-sidecar-", suffix=".json"
    )
    path = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(config.runtime_payload(), stream, ensure_ascii=False)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _drain_stream(stream, target: list[str]) -> None:
    if stream is None:
        return

    def drain() -> None:
        for line in stream:
            target.append(line.rstrip())

    threading.Thread(target=drain, name="harness-sidecar-stderr", daemon=True).start()


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass


def _read_startup_line(process: subprocess.Popen[str], timeout: float) -> str:
    if process.stdout is None:
        raise HarnessSidecarError("runtime stdout is unavailable")
    lines: queue.Queue[str] = queue.Queue(maxsize=1)

    def read() -> None:
        lines.put(process.stdout.readline())

    threading.Thread(target=read, name="harness-sidecar-discovery", daemon=True).start()
    try:
        line = lines.get(timeout=max(0.1, timeout)).strip()
    except queue.Empty as error:
        raise HarnessSidecarError(
            f"Harness Sidecar did not become ready within {timeout:g}s"
        ) from error
    if not line:
        raise HarnessSidecarError(
            f"Harness Sidecar exited before discovery (exit={process.poll()})"
        )
    return line


__all__ = [
    "HarnessSidecarError",
    "HarnessSidecarRuntimeUnavailable",
    "SidecarBinding",
    "doctor_harness_sidecar",
    "export_sidecar_env",
    "run_with_harness_sidecar",
    "start_harness_sidecar",
]
