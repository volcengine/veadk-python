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

"""Acceptance checks for ``runtime="dsh"``.

Run from the repository root:

    uv run --extra dev --extra dsh python examples/deepseek_harness_runtime/main.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types

from veadk import Agent, Runner
from veadk.consts import DEFAULT_MODEL_AGENT_API_BASE, DEFAULT_MODEL_AGENT_NAME
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer
from veadk.utils.adk_compat import (
    get_event_function_calls,
    get_event_function_responses,
)

APP_NAME = "dsh_runtime_acceptance"
USER_ID = "dsh_acceptance_user"
SHORT_SECRET = "dsh-sqlite-7319"
LONG_SECRET = "dsh-long-memory-4826"
SKILL_SENTINEL = "DSH-SKILL-OK"
HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE / "skills" / "dsh-runtime-acceptance"


@dataclass
class TurnRecord:
    final_text: str = ""
    partial_chunks: list[str] = field(default_factory=list)
    function_calls: list[str] = field(default_factory=list)
    function_responses: list[str] = field(default_factory=list)


@dataclass
class Check:
    name: str
    passed: bool
    evidence: str


def runtime_config() -> dict[str, Any]:
    runtime_config = {
        "provider": os.getenv("VEADK_DEEPSEEK_HARNESS_PROVIDER", "volcengine"),
        "model": os.getenv("VEADK_DEEPSEEK_HARNESS_MODEL")
        or os.getenv("MODEL_AGENT_NAME", DEFAULT_MODEL_AGENT_NAME),
        "profile": os.getenv("VEADK_DEEPSEEK_HARNESS_PROFILE", "sdk-minimal"),
        "base_url": os.getenv("VEADK_DEEPSEEK_HARNESS_BASE_URL")
        or os.getenv("MODEL_AGENT_API_BASE", DEFAULT_MODEL_AGENT_API_BASE),
        "api_key": os.getenv("VEADK_DEEPSEEK_HARNESS_API_KEY")
        or os.getenv("MODEL_AGENT_API_KEY"),
        "request_timeout_seconds": float(
            os.getenv("VEADK_DEEPSEEK_HARNESS_REQUEST_TIMEOUT_SECONDS", "180")
        ),
    }
    return {key: value for key, value in runtime_config.items() if value}


def build_agent(
    *,
    name: str,
    long_term_backend: str,
    tracer: OpentelemetryTracer,
    include_skill: bool,
    include_long_term_memory: bool,
) -> Agent:
    tools = []
    if include_skill:
        tools.append(SkillToolset(skills=[load_skill_from_dir(str(SKILL_DIR))]))

    agent_kwargs = {
        "name": name,
        "description": "Validates the DSH runtime integration.",
        "instruction": (
            "You are validating VeADK's DSH runtime. "
            "Use available tools when they are relevant. "
            "Reply exactly as requested by the user."
        ),
        "runtime": "dsh",
        "model_name": os.getenv("MODEL_AGENT_NAME", DEFAULT_MODEL_AGENT_NAME),
        "deepseek_harness_runtime_config": runtime_config(),
        "tools": tools,
        "auto_save_session": include_long_term_memory,
        "tracers": [tracer],
    }
    if include_long_term_memory:
        agent_kwargs["long_term_memory"] = LongTermMemory(
            backend=long_term_backend,
            app_name=APP_NAME,
            index=APP_NAME,
        )
    if os.getenv("MODEL_AGENT_API_BASE"):
        agent_kwargs["model_api_base"] = os.environ["MODEL_AGENT_API_BASE"]
    if os.getenv("MODEL_AGENT_API_KEY"):
        agent_kwargs["model_api_key"] = os.environ["MODEL_AGENT_API_KEY"]
    return Agent(**agent_kwargs)


def build_runner(agent: Agent, sqlite_path: Path) -> Runner:
    short_term_memory = ShortTermMemory(
        backend="sqlite",
        local_database_path=str(sqlite_path),
    )
    return Runner(
        agent=agent,
        short_term_memory=short_term_memory,
        app_name=APP_NAME,
        user_id=USER_ID,
    )


async def run_turn(runner: Runner, *, session_id: str, text: str) -> TurnRecord:
    assert runner.short_term_memory is not None
    await runner.short_term_memory.create_session(
        app_name=runner.app_name,
        user_id=runner.user_id,
        session_id=session_id,
    )

    record = TurnRecord()
    async for event in runner.run_async(
        user_id=runner.user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=text)]),
    ):
        for call in get_event_function_calls(event):
            record.function_calls.append(call.name or "")
        for response in get_event_function_responses(event):
            record.function_responses.append(response.name or "")
        text_part = _event_text(event)
        if not text_part:
            continue
        if event.partial:
            record.partial_chunks.append(text_part)
        elif event.is_final_response():
            record.final_text = text_part
    return record


def _event_text(event: Any) -> str:
    content = getattr(event, "content", None)
    if not content or not content.parts:
        return ""
    return "".join(
        part.text
        for part in content.parts
        if getattr(part, "text", None) and not getattr(part, "thought", False)
    )


async def search_long_term_memory(runner: Runner, query: str) -> int:
    memory = runner.long_term_memory
    if memory is None:
        return 0
    for _ in range(6):
        response = await memory.search_memory(
            app_name=runner.app_name,
            user_id=runner.user_id,
            query=query,
        )
        if response.memories:
            return len(response.memories)
        await asyncio.sleep(2)
    return 0


async def sqlite_event_count(runner: Runner, session_id: str) -> int:
    session = await runner.session_service.get_session(
        app_name=runner.app_name,
        user_id=runner.user_id,
        session_id=session_id,
    )
    return len(getattr(session, "events", []) or []) if session else 0


def collect_trace_check(
    runner: Runner,
    tracer: OpentelemetryTracer,
    session_ids: list[str],
) -> Check:
    exporter = tracer._inmemory_exporter._exporter
    matched_spans = []
    for session_id in session_ids:
        matched_spans.extend(exporter.get_finished_spans(session_id))
    call_llm_spans = [span for span in matched_spans if span.name == "call_llm"]
    trace_id = runner.get_trace_id()
    dump_path = runner.save_tracing_file(session_id=session_ids[-1])
    evidence = {
        "trace_id": trace_id,
        "matched_spans": len(matched_spans),
        "call_llm_spans": len(call_llm_spans),
        "dump_path": dump_path,
    }
    return Check(
        name="observability",
        passed=bool(call_llm_spans and trace_id != "<unknown_trace_id>"),
        evidence=json.dumps(evidence, ensure_ascii=False),
    )


def print_check(check: Check) -> None:
    status = "PASS" if check.passed else "FAIL"
    print(f"[{status}] {check.name}: {check.evidence}")


async def main_async(args: argparse.Namespace) -> int:
    tracer = OpentelemetryTracer(exporters=[])
    skill_runner = build_runner(
        build_agent(
            name="dsh_skill_acceptance_agent",
            long_term_backend=args.long_term_backend,
            tracer=tracer,
            include_skill=True,
            include_long_term_memory=False,
        ),
        args.sqlite_path,
    )
    memory_runner = build_runner(
        build_agent(
            name="dsh_memory_acceptance_agent",
            long_term_backend=args.long_term_backend,
            tracer=tracer,
            include_skill=False,
            include_long_term_memory=True,
        ),
        args.sqlite_path,
    )
    skill_session = f"dsh-skill-{uuid.uuid4().hex[:8]}"
    session_one = f"dsh-sqlite-{uuid.uuid4().hex[:8]}"
    session_two = f"dsh-ltm-{uuid.uuid4().hex[:8]}"

    skill_turn = await run_turn(
        skill_runner,
        session_id=skill_session,
        text=(
            "Use the local DSH runtime acceptance skill. "
            "What is the DSH skill sentinel? Reply with only the sentinel."
        ),
    )
    short_seed_turn = await run_turn(
        memory_runner,
        session_id=session_one,
        text=f"In this same session, remember the short-term sqlite secret: {SHORT_SECRET}. Reply OK.",
    )
    short_recall_turn = await run_turn(
        memory_runner,
        session_id=session_one,
        text="What is the short-term sqlite secret from this session? Reply with only the secret.",
    )
    long_seed_turn = await run_turn(
        memory_runner,
        session_id=session_one,
        text=(
            "Reply with only OK. The host auto-save callback should persist this "
            f"long-term memory marker from my message: {LONG_SECRET}."
        ),
    )
    session_switch_turn = await run_turn(
        memory_runner,
        session_id=session_two,
        text="Reply with only OK.",
    )
    direct_memory_count = await search_long_term_memory(memory_runner, LONG_SECRET)

    sqlite_events = await sqlite_event_count(memory_runner, session_one)
    checks = [
        Check(
            name="streaming",
            passed=bool(skill_turn.partial_chunks),
            evidence=f"partial_chunks={len(skill_turn.partial_chunks)}",
        ),
        Check(
            name="skill",
            passed=SKILL_SENTINEL in skill_turn.final_text,
            evidence=f"final_text={skill_turn.final_text!r}",
        ),
        Check(
            name="short_term_memory_sqlite",
            passed=sqlite_events >= 4,
            evidence=(
                f"sqlite_path={args.sqlite_path} session_events={sqlite_events} "
                f"recall={short_recall_turn.final_text!r}"
            ),
        ),
        Check(
            name="long_term_memory_auto_save",
            passed=direct_memory_count > 0,
            evidence=(
                f"direct_search_count={direct_memory_count} "
                f"session_switch_final={session_switch_turn.final_text!r}"
            ),
        ),
        collect_trace_check(
            memory_runner, tracer, [skill_session, session_one, session_two]
        ),
    ]

    print("\nTurn evidence:")
    print(f"skill final: {skill_turn.final_text}")
    print(f"short seed final: {short_seed_turn.final_text}")
    print(f"short recall final: {short_recall_turn.final_text}")
    print(f"long seed final: {long_seed_turn.final_text}")
    print(f"session switch final: {session_switch_turn.final_text}")
    print("\nChecks:")
    for check in checks:
        print_check(check)
    return 0 if all(check.passed for check in checks) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=Path(tempfile.gettempdir()) / "veadk_dsh_runtime_acceptance.sqlite",
    )
    parser.add_argument(
        "--long-term-backend",
        default=os.getenv("VEADK_DSH_ACCEPTANCE_LTM_BACKEND", "viking"),
        choices=[
            "local",
            "opensearch",
            "redis",
            "viking",
            "viking_mem",
            "mem0",
            "openviking",
            "tos_context",
        ],
    )
    return parser.parse_args()


def main() -> None:
    raise SystemExit(asyncio.run(main_async(parse_args())))


if __name__ == "__main__":
    main()
