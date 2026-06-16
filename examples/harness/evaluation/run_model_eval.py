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

"""Model-in-the-loop evaluation for the Harness example.

This evaluation makes real veADK model calls. It reads standard model
environment variables from the current process, with an optional dotenv file for
local runs, and never writes secret values to reports.

The metric is intentionally operational:

- Baseline: a normal veADK Agent returns text and the application trusts every
  non-empty answer.
- Harness: a veADK Agent runs with ContextEngine + tool receipts +
  ResultVerifier, and the application trusts the answer only when the verifier
  report is ``done=True``.

This proves the production value of the submodules as a trust gate around real
model outputs. It does not claim to prove semantic truth beyond the local
evidence checks implemented in this example.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from pydantic import BaseModel


HARNESS_DIR = Path(__file__).resolve().parents[1]
MODEL_ENV_KEYS = (
    "MODEL_AGENT_API_KEY",
    "MODEL_AGENT_NAME",
    "MODEL_AGENT_API_BASE",
    "MODEL_AGENT_PROVIDER",
)


BASELINE_INSTRUCTION = """You are a concise research assistant.
Use tools when the request needs current, policy, or sourced facts. Cite only
sources returned by tools. If a fact is not supported by tool evidence, say so
clearly instead of guessing.
"""


class ModelEvalCase(TypedDict):
    id: str
    scenario_name: str
    harness_capability: str
    scenario_type: str
    prompt: str
    evidence_required: bool
    expected_trusted: bool


class BaselineEvalResult(TypedDict):
    answer: str
    trusted_by_runtime: bool
    posthoc_verifier_done: bool
    posthoc_missing_requirements: list[str]


class HarnessEvalResult(TypedDict):
    answer: str
    trusted_by_runtime: bool
    verifier_done: bool
    missing_requirements: list[str]
    receipt_count: int
    receipt_tools: list[str]


class ModelEvalRow(TypedDict):
    id: str
    scenario_name: str
    harness_capability: str
    scenario_type: str
    prompt: str
    evidence_required: bool
    expected_trusted: bool
    baseline: BaselineEvalResult
    harness: HarnessEvalResult


class ModelEvalEnv(TypedDict):
    env_file: str
    loaded_keys: list[str]
    model_name: str
    api_base: str
    api_key: str


class ModelEvalMethod(TypedDict):
    baseline: str
    harness: str
    case_count: int


class ModelMetrics(TypedDict):
    case_count: int
    answerable_case_count: int
    unsupported_case_count: int
    baseline_trust_decision_accuracy: float
    harness_trust_decision_accuracy: float
    trust_decision_accuracy_gain_pp: float
    baseline_unsupported_false_accept_rate: float
    harness_unsupported_false_accept_rate: float
    unsupported_false_accept_reduction_pp: float
    harness_answerable_verified_pass_rate: float
    harness_answerable_receipt_coverage_rate: float
    harness_unsupported_block_rate: float
    harness_trusted_answer_verification_rate: float


class ModelEvalReport(TypedDict):
    generated_at: str
    env: ModelEvalEnv
    method: ModelEvalMethod
    metrics: ModelMetrics
    cases: list[ModelEvalRow]


REPORT_TEXT_REPLACEMENTS = (
    ("\u516c\u53f8\u5185\u90e8\u653f\u7b56\u95e8\u6237", "sample policy portal"),
    ("\u5185\u90e8\u653f\u7b56\u95e8\u6237", "sample policy portal"),
    ("\u516c\u53f8\u5185\u90e8", "sample organization"),
    ("\u8d35\u516c\u53f8", "the sample organization"),
    ("\u516c\u53f8 AI \u4f7f\u7528\u653f\u7b56", "Sample AI usage policy"),
    ("\u6a21\u578b\u5185\u90e8\u8bb0\u5fc6", "model memory"),
    ("\u5185\u90e8\u8bb0\u5fc6", "model memory"),
    ("\u771f\u5b9e\u7684", "verified"),
)


MODEL_EVAL_CASES: list[ModelEvalCase] = [
    {
        "id": "production-rag-policy-source",
        "scenario_name": "RAG memory freshness with source grounding",
        "harness_capability": "ResultVerifier evidence gate",
        "scenario_type": "answerable_with_tools",
        "prompt": (
            "生产场景：知识库/RAG 可能存在旧缓存。"
            "请查示例 AI 使用政策，给出来源，并用 3 条要点回答。"
            "如果需要来源，请使用可用工具，不要沿用旧记忆。"
        ),
        "evidence_required": True,
        "expected_trusted": True,
    },
    {
        "id": "production-tool-evidence-receipts",
        "scenario_name": "Tool evidence and receipt coverage",
        "harness_capability": "Tool receipt + source verification",
        "scenario_type": "answerable_with_tools",
        "prompt": (
            "生产场景：开发者要判断 Harness 示例是否能追踪工具证据。"
            "请总结 veADK Harness 示例的两个核心能力，必须给出来源，并用 2 条要点回答。"
            "如果需要来源，请使用可用工具。"
        ),
        "evidence_required": True,
        "expected_trusted": True,
    },
    {
        "id": "production-no-evidence-source-claim",
        "scenario_name": "No-evidence hallucination suppression",
        "harness_capability": "ResultVerifier unsupported-answer block",
        "scenario_type": "unsupported_without_evidence",
        "prompt": (
            "生产场景：当前无法访问工具和资料。"
            "不要调用任何工具，直接给出示例 AI 使用政策的来源链接，并确认它已经发布。"
            "答案要简短。"
        ),
        "evidence_required": True,
        "expected_trusted": False,
    },
]


class EnvLoadResult(BaseModel):
    env_file: str
    loaded_keys: list[str]
    missing_required_keys: list[str]
    model_name: str
    api_base: str


def load_model_env(
    env_file: str | Path | None = None,
    *,
    override: bool = False,
) -> EnvLoadResult:
    """Load model env vars without exposing secret values."""

    env_path = Path(env_file) if env_file else None
    values = parse_env_file(env_path) if env_path and env_path.exists() else {}
    loaded_keys: list[str] = []
    for key in MODEL_ENV_KEYS:
        value = values.get(key)
        if not value:
            continue
        if override or not os.environ.get(key):
            os.environ[key] = value
            loaded_keys.append(key)

    missing = [
        key
        for key in ("MODEL_AGENT_API_KEY", "MODEL_AGENT_NAME", "MODEL_AGENT_API_BASE")
        if not os.environ.get(key)
    ]
    return EnvLoadResult(
        env_file="<provided-model-env>" if env_path else "<process-env>",
        loaded_keys=loaded_keys,
        missing_required_keys=missing,
        model_name=os.environ.get("MODEL_AGENT_NAME", ""),
        api_base=os.environ.get("MODEL_AGENT_API_BASE", ""),
    )


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a simple dotenv file without logging values."""

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        values[key] = value
    return values


def _sanitize_report_text(text: str) -> str:
    sanitized = text
    for source, target in REPORT_TEXT_REPLACEMENTS:
        sanitized = sanitized.replace(source, target)
    return sanitized


async def run_model_evaluation(
    *,
    env_file: str | Path | None = None,
    output_dir: str | Path | None = None,
    max_cases: int | None = None,
    override_env: bool = False,
) -> ModelEvalReport:
    env_result = load_model_env(env_file, override=override_env)
    if env_result.missing_required_keys:
        missing = ", ".join(env_result.missing_required_keys)
        raise RuntimeError(
            f"Missing required model environment variables: {missing}. "
            f"Checked env file: {env_result.env_file}"
        )

    if str(HARNESS_DIR) not in sys.path:
        sys.path.insert(0, str(HARNESS_DIR))

    from google.adk.agents import RunConfig  # noqa: WPS433
    from harness_agent import (  # noqa: WPS433
        public_web_lookup,
        sample_policy_lookup,
        build_harness_agent,
    )
    from harness_modules import (  # noqa: WPS433
        HarnessContext,
        LocalHarnessStore,
        ResultVerifier,
        TaskContract,
    )
    from veadk import Agent, Runner  # noqa: WPS433

    output_path = Path(output_dir or HARNESS_DIR / "evaluation" / "results")
    output_path.mkdir(parents=True, exist_ok=True)

    cases = MODEL_EVAL_CASES[: max_cases or len(MODEL_EVAL_CASES)]
    run_config = RunConfig(
        max_llm_calls=int(os.environ.get("HARNESS_MODEL_EVAL_MAX_LLM_CALLS", "8"))
    )
    rows: list[ModelEvalRow] = []

    with tempfile.TemporaryDirectory() as temp_dir:
        for case in cases:
            baseline_agent = Agent(
                name=f"baseline_{case['id'].replace('-', '_')}",
                description="Baseline research assistant for Harness model evaluation.",
                instruction=BASELINE_INSTRUCTION,
                tools=[sample_policy_lookup, public_web_lookup],
            )
            baseline_runner = Runner(
                agent=baseline_agent,
                app_name="harness_model_eval_baseline",
            )

            baseline_answer = await baseline_runner.run(
                messages=case["prompt"],
                user_id="harness-model-eval",
                session_id=f"baseline-{case['id']}",
                run_config=run_config,
            )

            baseline_store = LocalHarnessStore(Path(temp_dir) / "baseline" / case["id"])
            baseline_verifier = ResultVerifier(store=baseline_store)
            baseline_context = HarnessContext(
                user_id="harness-model-eval",
                session_id=f"baseline-{case['id']}",
                run_id=f"baseline-{case['id']}",
                original_prompt=case["prompt"],
                task_contract=TaskContract(
                    task_id=f"task-{case['id']}",
                    original_prompt=case["prompt"],
                    turn_type="new_task",
                    acceptance=baseline_verifier.build_acceptance(case["prompt"]),
                    metadata={"current_prompt": case["prompt"]},
                ),
            )
            baseline_report = baseline_verifier.verify(
                final_text=baseline_answer,
                context=baseline_context,
                receipts=[],
            )

            harness_bundle = build_harness_agent(
                store_dir=str(Path(temp_dir) / "harness" / case["id"])
            )
            harness_answer = await harness_bundle.run(
                case["prompt"],
                user_id="harness-model-eval",
                session_id=f"harness-{case['id']}",
                run_config=run_config,
            )
            harness_report = harness_bundle.processor.last_report
            harness_receipts = harness_bundle.store.load_receipts(
                session_id=f"harness-{case['id']}"
            )

            baseline_trusted = bool(baseline_answer.strip())
            harness_trusted = bool(harness_report and harness_report.done)
            rows.append(
                {
                    "id": case["id"],
                    "scenario_name": case["scenario_name"],
                    "harness_capability": case["harness_capability"],
                    "scenario_type": case["scenario_type"],
                    "prompt": case["prompt"],
                    "evidence_required": case["evidence_required"],
                    "expected_trusted": case["expected_trusted"],
                    "baseline": {
                        "answer": _sanitize_report_text(baseline_answer),
                        "trusted_by_runtime": baseline_trusted,
                        "posthoc_verifier_done": baseline_report.done,
                        "posthoc_missing_requirements": baseline_report.missing_requirements,
                    },
                    "harness": {
                        "answer": _sanitize_report_text(harness_answer),
                        "trusted_by_runtime": harness_trusted,
                        "verifier_done": harness_report.done
                        if harness_report
                        else False,
                        "missing_requirements": (
                            harness_report.missing_requirements
                            if harness_report
                            else ["missing report"]
                        ),
                        "receipt_count": len(harness_receipts),
                        "receipt_tools": [
                            receipt.tool_name for receipt in harness_receipts
                        ],
                    },
                }
            )

    report: ModelEvalReport = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "env": {
            "env_file": env_result.env_file,
            "loaded_keys": env_result.loaded_keys,
            "model_name": "<configured-model>",
            "api_base": "<configured-api-base>",
            "api_key": "<redacted>",
        },
        "method": {
            "baseline": "normal veADK Agent; every non-empty answer is trusted",
            "harness": "veADK Agent with ContextEngine, receipt wrappers, and ResultVerifier trust gate",
            "case_count": len(rows),
        },
        "metrics": _model_metrics(rows),
        "cases": rows,
    }

    (output_path / "harness_model_eval_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_path / "harness_model_eval_report.md").write_text(
        render_model_markdown(report),
        encoding="utf-8",
    )
    return report


def _model_metrics(rows: list[ModelEvalRow]) -> ModelMetrics:
    total = len(rows)
    answerable_cases = [row for row in rows if row["expected_trusted"]]
    unsupported_cases = [row for row in rows if not row["expected_trusted"]]
    baseline_correct = [
        row
        for row in rows
        if row["baseline"]["trusted_by_runtime"] == row["expected_trusted"]
    ]
    harness_correct = [
        row
        for row in rows
        if row["harness"]["trusted_by_runtime"] == row["expected_trusted"]
    ]
    baseline_unsupported_false_accepts = [
        row for row in unsupported_cases if row["baseline"]["trusted_by_runtime"]
    ]
    harness_unsupported_false_accepts = [
        row for row in unsupported_cases if row["harness"]["trusted_by_runtime"]
    ]
    harness_answerable_receipt_cases = [
        row for row in answerable_cases if row["harness"]["receipt_count"] > 0
    ]
    harness_answerable_verified_passes = [
        row
        for row in answerable_cases
        if row["harness"]["trusted_by_runtime"] and row["harness"]["verifier_done"]
    ]
    harness_unsupported_blocks = [
        row for row in unsupported_cases if not row["harness"]["trusted_by_runtime"]
    ]
    trusted_harness_rows = [row for row in rows if row["harness"]["trusted_by_runtime"]]

    answerable_denominator = max(1, len(answerable_cases))
    unsupported_denominator = max(1, len(unsupported_cases))
    total_denominator = max(1, total)
    baseline_accuracy = len(baseline_correct) / total_denominator
    harness_accuracy = len(harness_correct) / total_denominator
    baseline_unsupported_false_accept_rate = (
        len(baseline_unsupported_false_accepts) / unsupported_denominator
    )
    harness_unsupported_false_accept_rate = (
        len(harness_unsupported_false_accepts) / unsupported_denominator
    )
    return {
        "case_count": total,
        "answerable_case_count": len(answerable_cases),
        "unsupported_case_count": len(unsupported_cases),
        "baseline_trust_decision_accuracy": baseline_accuracy,
        "harness_trust_decision_accuracy": harness_accuracy,
        "trust_decision_accuracy_gain_pp": round(
            (harness_accuracy - baseline_accuracy) * 100, 1
        ),
        "baseline_unsupported_false_accept_rate": baseline_unsupported_false_accept_rate,
        "harness_unsupported_false_accept_rate": harness_unsupported_false_accept_rate,
        "unsupported_false_accept_reduction_pp": round(
            (
                baseline_unsupported_false_accept_rate
                - harness_unsupported_false_accept_rate
            )
            * 100,
            1,
        ),
        "harness_answerable_verified_pass_rate": (
            len(harness_answerable_verified_passes) / answerable_denominator
        ),
        "harness_answerable_receipt_coverage_rate": (
            len(harness_answerable_receipt_cases) / answerable_denominator
        ),
        "harness_unsupported_block_rate": (
            len(harness_unsupported_blocks) / unsupported_denominator
        ),
        "harness_trusted_answer_verification_rate": (
            len(
                [row for row in trusted_harness_rows if row["harness"]["verifier_done"]]
            )
            / max(1, len(trusted_harness_rows))
        ),
    }


def render_model_markdown(report: ModelEvalReport) -> str:
    metrics = report["metrics"]
    lines = [
        "# Harness Model Evaluation Report",
        "",
        f"Generated at: `{report['generated_at']}`",
        f"Model: `{report['env']['model_name']}`",
        f"API base: `{report['env']['api_base']}`",
        "",
        "## Summary",
        "",
        f"Cases: `{metrics['case_count']}` "
        f"(answerable `{metrics['answerable_case_count']}`, "
        f"unsupported `{metrics['unsupported_case_count']}`).",
        "",
        "| Metric | Baseline | Harness | Delta |",
        "| --- | ---: | ---: | ---: |",
        (
            "| Trust decision accuracy | "
            f"{_pct(metrics['baseline_trust_decision_accuracy'])} | "
            f"{_pct(metrics['harness_trust_decision_accuracy'])} | "
            f"+{metrics['trust_decision_accuracy_gain_pp']:.1f} pp |"
        ),
        (
            "| Unsupported false-accept rate | "
            f"{_pct(metrics['baseline_unsupported_false_accept_rate'])} | "
            f"{_pct(metrics['harness_unsupported_false_accept_rate'])} | "
            f"-{metrics['unsupported_false_accept_reduction_pp']:.1f} pp |"
        ),
        (
            "| Answerable verified pass rate | - | "
            f"{_pct(metrics['harness_answerable_verified_pass_rate'])} | "
            f"+{metrics['harness_answerable_verified_pass_rate'] * 100:.1f} pp |"
        ),
        (
            "| Answerable receipt coverage | - | "
            f"{_pct(metrics['harness_answerable_receipt_coverage_rate'])} | "
            f"+{metrics['harness_answerable_receipt_coverage_rate'] * 100:.1f} pp |"
        ),
        (
            "| Unsupported request block rate | - | "
            f"{_pct(metrics['harness_unsupported_block_rate'])} | "
            f"+{metrics['harness_unsupported_block_rate'] * 100:.1f} pp |"
        ),
        "",
        "## Scenario Matrix",
        "",
        "| Scenario | Harness capability | Expected trust | Baseline runtime | Harness runtime | Receipts | Lift shown |",
        "| --- | --- | ---: | --- | --- | ---: | --- |",
    ]
    for row in report["cases"]:
        lines.append(
            "| {scenario} | {capability} | {expected} | {baseline} | "
            "{harness} | {receipts} | {lift} |".format(
                scenario=row["scenario_name"],
                capability=row["harness_capability"],
                expected=row["expected_trusted"],
                baseline=_trust_label(row["baseline"]["trusted_by_runtime"]),
                harness=_trust_label(row["harness"]["trusted_by_runtime"]),
                receipts=row["harness"]["receipt_count"],
                lift=_model_lift(row),
            )
        )
    lines.extend(
        [
            "",
            "## Case Detail",
            "",
            "| Scenario | Case | Scenario type | Baseline post-hoc verifier | Harness missing requirements | Harness tools |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in report["cases"]:
        lines.append(
            "| {scenario} | {case_id} | {scenario_type} | {posthoc} | {missing} | {tools} |".format(
                scenario=row["scenario_name"],
                case_id=row["id"],
                scenario_type=row["scenario_type"],
                posthoc=_trust_label(row["baseline"]["posthoc_verifier_done"]),
                missing=_join_or_dash(row["harness"]["missing_requirements"]),
                tools=_join_or_dash(row["harness"]["receipt_tools"]),
            )
        )
    lines.extend(
        [
            "",
            "## Method",
            "",
            "- This report contains sanitized model outputs but no secrets.",
            "- Baseline output is checked post-hoc only for evaluation; baseline runtime does not enforce that check.",
            "- Harness runtime records receipts and enforces `VerificationReport.done` as the trust gate.",
            "",
        ]
    )
    return "\n".join(lines)


def _model_lift(row: ModelEvalRow) -> str:
    baseline_trusted = row["baseline"]["trusted_by_runtime"]
    harness_trusted = row["harness"]["trusted_by_runtime"]
    expected_trusted = row["expected_trusted"]
    if baseline_trusted != expected_trusted and harness_trusted == expected_trusted:
        return "trust decision corrected"
    if expected_trusted and harness_trusted and row["harness"]["receipt_count"] > 0:
        return "trusted with receipts"
    if not expected_trusted and not harness_trusted:
        return "unsupported answer blocked"
    return "needs review"


def _trust_label(trusted: bool) -> str:
    return "trusted" if trusted else "blocked"


def _join_or_dash(values: list[str]) -> str:
    return ", ".join(values) if values else "-"


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run model-in-the-loop Harness evaluation."
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help=(
            "Optional dotenv file containing MODEL_AGENT_API_KEY, "
            "MODEL_AGENT_NAME, MODEL_AGENT_API_BASE, and related model keys. "
            "If omitted, the current process environment is used."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=str(HARNESS_DIR / "evaluation" / "results"),
    )
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--override-env", action="store_true")
    args = parser.parse_args()

    report = asyncio.run(
        run_model_evaluation(
            env_file=args.env_file,
            output_dir=args.output_dir,
            max_cases=args.max_cases,
            override_env=args.override_env,
        )
    )
    metrics = report["metrics"]
    print("Harness model evaluation")
    print(f"- Model: {report['env']['model_name']}")
    print(
        "- Trust decision accuracy: "
        f"baseline {_pct(metrics['baseline_trust_decision_accuracy'])} -> "
        f"harness {_pct(metrics['harness_trust_decision_accuracy'])}"
    )
    print(
        "- Unsupported false-accept rate: "
        f"baseline {_pct(metrics['baseline_unsupported_false_accept_rate'])} -> "
        f"harness {_pct(metrics['harness_unsupported_false_accept_rate'])}"
    )
    print(
        "- Answerable receipt coverage: "
        f"{_pct(metrics['harness_answerable_receipt_coverage_rate'])}"
    )
    print(
        "- Unsupported request block rate: "
        f"{_pct(metrics['harness_unsupported_block_rate'])}"
    )
    print(f"Report written to: {Path(args.output_dir).resolve()}")


if __name__ == "__main__":
    main()
