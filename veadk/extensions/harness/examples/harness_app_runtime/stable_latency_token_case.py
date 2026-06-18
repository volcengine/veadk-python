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

"""Local HarnessApp Runtime latency/token-shape benchmark.

This script starts a local HarnessApp Runtime and invokes it through
`veadk agentkit invoke`. It compares the same runtime in two modes:

* no_enhance: no Harness enhancement headers.
* harness_enhance: `--enable-harness-enhance` with built-in compression.

The model is deterministic so the test is stable on a developer laptop while
still exercising the real Runtime, Runner, Harness plugin, tool callback, HTTP
Runtime, and CLI invocation path.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import socket
import statistics
import subprocess
import sys
import threading
import time
from collections.abc import AsyncGenerator
from pathlib import Path

import uvicorn
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import BaseModel, ConfigDict, PrivateAttr


PROMPT = (
    "stable-latency-token-case: call metric_payload once, then identify the best "
    "model from metric rows. Final answer must include best_model and accuracy."
)


class RunMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: str
    elapsed_seconds: float
    prompt_chars: int
    output: str


class BenchmarkLlm(BaseLlm):
    _delay_divisor: float = PrivateAttr()
    _max_delay_seconds: float = PrivateAttr()

    def __init__(
        self,
        *,
        model: str,
        delay_divisor: float,
        max_delay_seconds: float,
    ) -> None:
        super().__init__(model=model)
        self._delay_divisor = delay_divisor
        self._max_delay_seconds = max_delay_seconds

    async def generate_content_async(
        self, llm_request: object, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        request_text = _request_text(llm_request)
        has_function_response = _has_function_response(llm_request)
        if PROMPT in request_text and not has_function_response:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part.from_function_call(name="metric_payload", args={})
                    ],
                )
            )
            return

        prompt_chars = len(request_text)
        delay = min(prompt_chars / self._delay_divisor, self._max_delay_seconds)
        await asyncio.sleep(delay)
        compressed = (
            "harness_compressed" in request_text
            or "COMPRESSED_METRIC_ROWS" in request_text
        )
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        text=(
                            "best_model: T5\n"
                            "accuracy: 88\n"
                            f"prompt_chars: {prompt_chars}\n"
                            f"compressed_context: {str(compressed).lower()}"
                        )
                    )
                ],
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--rows", type=int, default=2500)
    parser.add_argument("--delay-divisor", type=float, default=60000.0)
    parser.add_argument("--max-delay-seconds", type=float, default=2.5)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=_default_env_file(),
        help=(
            "Optional env file used to seed local model/runtime variables. "
            "Can also be set with HARNESS_BENCHMARK_ENV_FILE."
        ),
    )
    args = parser.parse_args()

    _load_env_file(args.env_file)
    os.environ.setdefault("LOGGING_LEVEL", "WARNING")
    os.environ["HARNESS_ENHANCE_ENABLED"] = "false"

    runtime_port = _free_port()
    runtime, server, server_thread = _start_runtime(
        port=runtime_port,
        rows=args.rows,
        delay_divisor=args.delay_divisor,
        max_delay_seconds=args.max_delay_seconds,
    )
    endpoint = f"http://127.0.0.1:{runtime_port}"

    try:
        baseline = [
            _invoke_cli(
                mode="no_enhance",
                endpoint=endpoint,
                session_id=f"baseline-{index}",
                enhanced=False,
            )
            for index in range(args.repeats)
        ]
        enhanced = [
            _invoke_cli(
                mode="harness_enhance",
                endpoint=endpoint,
                session_id=f"enhanced-{index}",
                enhanced=True,
            )
            for index in range(args.repeats)
        ]
        report = _build_report(
            baseline=baseline,
            enhanced=enhanced,
            plugin_names=[plugin.name for plugin in runtime.plugins],
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 1
    finally:
        server.should_exit = True
        server_thread.join(timeout=10)


def _start_runtime(
    *,
    port: int,
    rows: int,
    delay_divisor: float,
    max_delay_seconds: float,
):
    from veadk import Agent
    from veadk.cloud.harness_app.app import HarnessApp
    from veadk.memory.short_term_memory import ShortTermMemory

    def metric_payload() -> dict[str, object]:
        metric_rows = [
            {"kind": "metric", "model": "T4", "accuracy": 82, "rank": 2},
            {"kind": "metric", "model": "T5", "accuracy": 88, "rank": 1},
        ]
        debug_rows = [
            {
                "kind": "debug",
                "row": index,
                "trace": "diagnostic-noise-" + ("x" * 48),
            }
            for index in range(rows)
        ]
        return {"metric_rows": metric_rows, "debug_rows": debug_rows}

    runtime = HarnessApp(
        Agent(
            name="local_latency_token_agent",
            instruction="Use tools when requested and return the benchmark markers.",
            model=BenchmarkLlm(
                model="benchmark-fake",
                delay_divisor=delay_divisor,
                max_delay_seconds=max_delay_seconds,
            ),
            tools=[metric_payload],
        ),
        ShortTermMemory(backend="local"),
        harness_name="local_latency_token_case",
        max_llm_calls=6,
    )
    server = uvicorn.Server(
        uvicorn.Config(runtime.app, host="127.0.0.1", port=port, log_level="warning")
    )
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    for _ in range(100):
        if server.started:
            return runtime, server, server_thread
        time.sleep(0.05)
    raise RuntimeError("local HarnessApp Runtime did not start")


def _invoke_cli(
    *,
    mode: str,
    endpoint: str,
    session_id: str,
    enhanced: bool,
) -> RunMetric:
    repo_root = Path(__file__).resolve().parents[5]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root)
    env.setdefault("LOGGING_LEVEL", "WARNING")
    command = [
        sys.executable,
        "-m",
        "veadk.cli.cli",
        "agentkit",
        "invoke",
        "--endpoint",
        endpoint,
        "--apikey",
        "local-test-key",
        "--harness",
        "local_latency_token_case",
        "--user-id",
        "local-user",
        "--session-id",
        session_id,
        "--max-llm-calls",
        "6",
    ]
    if enhanced:
        command.extend(
            [
                "--enable-harness-enhance",
                "--harness-components",
                "invocation_context,compactor,response_verification",
                "--harness-profile",
                "benchmark",
                "--harness-compression-provider",
                "builtin",
            ]
        )
    command.append(PROMPT)
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed = time.perf_counter() - started
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        raise RuntimeError(f"{mode} invoke failed:\n{output}")
    prompt_chars = _extract_prompt_chars(output)
    return RunMetric(
        mode=mode, elapsed_seconds=elapsed, prompt_chars=prompt_chars, output=output
    )


def _extract_prompt_chars(output: str) -> int:
    match = re.search(r"prompt_chars:\s*(\d+)", output)
    if not match:
        raise RuntimeError(f"prompt_chars marker not found in CLI output:\n{output}")
    return int(match.group(1))


def _request_text(llm_request: object) -> str:
    values: list[str] = []
    for content in getattr(llm_request, "contents", []) or []:
        for part in getattr(content, "parts", []) or []:
            text = getattr(part, "text", None)
            if text:
                values.append(str(text))
            function_call = getattr(part, "function_call", None)
            if function_call is not None:
                values.append(_json_for_context(function_call))
            function_response = getattr(part, "function_response", None)
            if function_response is not None:
                values.append(_json_for_context(function_response))
    return "\n".join(values)


def _has_function_response(llm_request: object) -> bool:
    for content in getattr(llm_request, "contents", []) or []:
        for part in getattr(content, "parts", []) or []:
            if getattr(part, "function_response", None) is not None:
                return True
    return False


def _json_for_context(value: object) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return json.dumps(value, ensure_ascii=False, default=str)


def _build_report(
    *,
    baseline: list[RunMetric],
    enhanced: list[RunMetric],
    plugin_names: list[str],
) -> dict[str, object]:
    baseline_latency = statistics.median(item.elapsed_seconds for item in baseline)
    enhanced_latency = statistics.median(item.elapsed_seconds for item in enhanced)
    baseline_chars = int(statistics.median(item.prompt_chars for item in baseline))
    enhanced_chars = int(statistics.median(item.prompt_chars for item in enhanced))
    latency_saved = baseline_latency - enhanced_latency
    char_saved = baseline_chars - enhanced_chars
    latency_saving_ratio = latency_saved / baseline_latency if baseline_latency else 0.0
    char_saving_ratio = char_saved / baseline_chars if baseline_chars else 0.0
    compression_ratio = enhanced_chars / baseline_chars if baseline_chars else 0.0
    answers_match = all("best_model: T5" in item.output for item in baseline + enhanced)
    baseline_uncompressed = all(
        "compressed_context: false" in item.output for item in baseline
    )
    enhanced_compressed = all(
        "compressed_context: true" in item.output for item in enhanced
    )
    passed = (
        answers_match
        and baseline_uncompressed
        and enhanced_compressed
        and enhanced_latency < baseline_latency
        and enhanced_chars < baseline_chars
        and compression_ratio < 0.1
    )
    return {
        "case": "local_stable_latency_token_case",
        "passed": passed,
        "plugins_attached_by_default": plugin_names,
        "repeats": len(baseline),
        "median": {
            "no_enhance_latency_seconds": round(baseline_latency, 4),
            "harness_enhance_latency_seconds": round(enhanced_latency, 4),
            "latency_saved_seconds": round(latency_saved, 4),
            "latency_saving_pct": round(latency_saving_ratio * 100, 4),
            "no_enhance_prompt_chars": baseline_chars,
            "harness_enhance_prompt_chars": enhanced_chars,
            "prompt_chars_saved": char_saved,
            "prompt_chars_saving_pct": round(char_saving_ratio * 100, 4),
        },
        "compression": {
            "provider": "builtin",
            "median_original_prompt_chars": baseline_chars,
            "median_compressed_prompt_chars": enhanced_chars,
            "compression_ratio": round(compression_ratio, 6),
        },
        "answers_match": answers_match,
        "baseline_uncompressed": baseline_uncompressed,
        "enhanced_compressed": enhanced_compressed,
        "details": {
            "no_enhance": [_metric_row(item) for item in baseline],
            "harness_enhance": [_metric_row(item) for item in enhanced],
        },
    }


def _metric_row(metric: RunMetric) -> dict[str, object]:
    return {
        "mode": metric.mode,
        "elapsed_seconds": round(metric.elapsed_seconds, 4),
        "prompt_chars": metric.prompt_chars,
    }


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _default_env_file() -> Path:
    configured = os.getenv("HARNESS_BENCHMARK_ENV_FILE")
    return Path(configured) if configured else Path()


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


if __name__ == "__main__":
    raise SystemExit(main())
