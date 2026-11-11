"""Apply pinned upstream scorers to real HTTP traces, never to answer guesses."""

import ast
import contextlib
import datetime
import hashlib
import io
import json
import os
import random
import re
import signal
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from query_routing_public_benchmarks import upstream_definitions


def structured_calls(row):
    return [
        part["functionCall"]
        for event in row.get("events", [])
        for part in (event.get("content") or {}).get("parts", [])
        if part.get("functionCall")
    ]


def isolated_lcb(case, answer, sources, *, timeout=120):
    """Run upstream code/test evaluators without host files, network or secrets."""
    sources = Path(sources)
    with tempfile.TemporaryDirectory(prefix="routing-lcb-") as temporary:
        work = Path(temporary)
        (work / "input.json").write_text(json.dumps({"case": case, "answer": answer}))
        (work / "score.py").write_text(_LCB_SCRIPT)
        command = [
            "prlimit",
            "--as=4294967296",
            "--cpu=90",
            "bwrap",
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--clearenv",
        ]
        paths = {
            Path("/usr"),
            Path("/lib"),
            Path("/lib64"),
            Path(sys.base_prefix),
            Path(sys.prefix),
        }
        for path in sorted(paths):
            if path.exists():
                command.extend(["--ro-bind", str(path), str(path)])
        if Path(sys.executable).is_symlink():
            target = Path(os.readlink(sys.executable))
            if target.is_absolute() and target.parent.parent != Path(sys.base_prefix):
                command.extend(
                    ["--ro-bind", sys.base_prefix, str(target.parent.parent)]
                )
        command.extend(
            [
                "--ro-bind",
                str(sources / "livecodebench"),
                "/source",
                "--ro-bind",
                str(work),
                "/work",
                "--tmpfs",
                "/tmp",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--setenv",
                "PYTHONPATH",
                "/source",
                "--setenv",
                "OPENBLAS_NUM_THREADS",
                "1",
                "--setenv",
                "OMP_NUM_THREADS",
                "1",
                "--chdir",
                "/work",
                sys.executable,
                "/work/score.py",
            ]
        )
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            return {"success": False, "error": "code_evaluation_wall_timeout"}
        marker = next(
            (
                line[13:]
                for line in stdout.splitlines()
                if line.startswith("ROUTING_SCORE")
            ),
            None,
        )
        if process.returncode != 0 or marker is None:
            raise RuntimeError(
                f"isolated LCB evaluator failed ({process.returncode}): {stderr[-1500:]}"
            )
        return json.loads(marker)


_LCB_SCRIPT = """
import json
from lcb_runner.lm_styles import LMStyle
from lcb_runner.utils.extraction_utils import extract_code, extract_execution_code, extract_test_output_code
from lcb_runner.evaluation.compute_code_generation_metrics import check_correctness
from lcb_runner.evaluation.compute_code_execution_metrics import evaluate_score
from lcb_runner.evaluation.compute_test_output_prediction_metrics import check_testcase_output
from lcb_runner.benchmarks.code_generation import CodeGenerationProblem

item = json.load(open('/work/input.json'))
case, answer = item['case'], item['answer']
payload = case['payload']
category = case['category']
if category.startswith('code_generation'):
    problem = CodeGenerationProblem(**payload)
    code = extract_code(answer, LMStyle.OpenAIChat)
    checks, metadata = check_correctness(problem.get_evaluation_sample(), code, timeout=6, debug=False)
    result = {'success': bool(len(checks)) and all(c == True for c in checks), 'test_results': [int(c) for c in checks], 'metadata': metadata}
elif category.startswith('code_execution'):
    predicted = extract_execution_code(answer, LMStyle.OpenAIChat)
    checks = evaluate_score(([predicted], (payload['code'], payload['input'], payload['output'])))
    result = {'success': bool(checks) and all(checks), 'test_results': checks}
else:
    predicted = extract_test_output_code(answer, LMStyle.OpenAIChat)
    expected = json.loads(payload['test'])[0]['output']
    result = {'success': bool(check_testcase_output(predicted, expected))}
print('ROUTING_SCORE' + json.dumps(result, default=str))
"""


def score_static(case, row, sources):
    if row.get("errors"):
        return {"success": False, "reason": "agent_error"}
    answer = row.get("answer", "")
    if not answer:
        return {"success": False, "reason": "empty_answer"}
    family, payload = case["source"], case["payload"]
    sources = Path(sources)
    if family == "IFEval":
        from instruction_following_eval import evaluation_lib
        from langdetect import DetectorFactory

        DetectorFactory.seed = 0
        example = evaluation_lib.InputExample(**payload)
        strict = evaluation_lib.test_instruction_following_strict(
            example, {example.prompt: answer}
        )
        loose = evaluation_lib.test_instruction_following_loose(
            example, {example.prompt: answer}
        )
        return {
            "success": strict.follow_all_instructions,
            "strict_constraints": strict.follow_instruction_list,
            "loose_success": loose.follow_all_instructions,
            "loose_constraints": loose.follow_instruction_list,
        }
    if family == "MMLU-Pro":
        scorer = upstream_definitions(
            sources / "mmlu_pro/evaluate_from_api.py",
            ["extract_answer", "extract_again", "extract_final"],
            {"re": re},
        )
        with contextlib.redirect_stdout(io.StringIO()):
            prediction = scorer.extract_answer(answer)
        return {"success": prediction == payload["answer"], "prediction": prediction}
    if family == "LongBench-v2":
        scorer = upstream_definitions(
            sources / "longbench/pred.py", ["extract_answer"], {"re": re}
        )
        prediction = scorer.extract_answer(answer)
        return {
            "success": prediction == payload["answer"],
            "prediction": prediction,
            "budget_band": case["budget_band"],
            "context_chars": case["context_chars"],
        }
    if family == "MMMU":
        import numpy as np

        path = sources / "mmmu/mmmu/utils/eval_utils.py"
        names = [
            n.name
            for n in ast.parse(path.read_text()).body
            if isinstance(n, ast.FunctionDef)
        ]
        seed = int(hashlib.sha256(case["id"].encode()).hexdigest()[:8], 16)

        class ObservedRandom(random.Random):
            used_fallback = False

            def choice(self, seq):
                self.used_fallback = True
                return super().choice(seq)

        rng = ObservedRandom(seed)
        scorer = upstream_definitions(path, names, {"re": re, "random": rng, "np": np})
        if payload["question_type"] == "multiple-choice":
            choices = ast.literal_eval(payload["options"])
            mapping = {chr(65 + i): value for i, value in enumerate(choices)}
            prediction = scorer.parse_multi_choice_response(
                answer, list(mapping), mapping
            )
            success = scorer.eval_multi_choice(payload["answer"], prediction)
        else:
            prediction = scorer.parse_open_response(answer)
            success = scorer.eval_open(payload["answer"], prediction)
        return {
            "success": bool(success),
            "prediction": prediction,
            "parser_random_fallback": rng.used_fallback,
        }
    if family == "LiveCodeBench":
        return isolated_lcb(case, answer, sources)
    raise ValueError(f"unknown static benchmark: {family}")


def replay_agentdojo_call(backend, entry):
    """Replay native calls with their recorded nondeterministic clock input."""
    result = entry.get("result")
    if (
        entry["name"] == "send_email"
        and isinstance(result, dict)
        and "timestamp" in result
    ):
        from agentdojo.default_suites.v1.tools import email_client

        recorded = datetime.datetime.fromisoformat(result["timestamp"])

        class RecordedDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return recorded if tz is None else recorded.astimezone(tz)

        # Scope the clock to this upstream tool module during sequential offline
        # replay. The global clock and native task/attack assertions stay intact.
        clock = SimpleNamespace(**(vars(datetime) | {"datetime": RecordedDateTime}))
        with patch.object(email_client, "datetime", clock):
            return backend.call(entry["name"], entry["arguments"])
    return backend.call(entry["name"], entry["arguments"])


def agentdojo_results_equal(expected, actual):
    """Match replay results, respecting the upstream CalendarEvent set field.

    Calendar.create_event uses list(set(participants)); its order varies with
    Python's process hash seed. Native utility checks also compare this field
    as a set. Preserve duplicates and every other list's order in this check.
    """

    def canonical(value):
        if isinstance(value, list):
            return [canonical(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: canonical(item) for key, item in value.items()}
        if {"id_", "title", "start_time", "end_time", "participants"} <= value.keys():
            participants = value["participants"]
            if isinstance(participants, list) and all(
                isinstance(p, str) for p in participants
            ):
                result["participants"] = sorted(participants)
        return result

    return canonical(expected) == canonical(actual)


def score_bfcl(case, rows, sources):
    from bfcl_eval.utils import make_json_serializable
    from bfcl_eval.constants.enums import Language
    from bfcl_eval.constants.type_mappings import (
        JAVA_TYPE_CONVERSION,
        JS_TYPE_CONVERSION,
    )
    from bfcl_eval.eval_checker.ast_eval.type_convertor.java_type_converter import (
        java_type_converter,
    )
    from bfcl_eval.eval_checker.ast_eval.type_convertor.js_type_converter import (
        js_type_converter,
    )
    from bfcl_eval.eval_checker.multi_turn_eval.multi_turn_checker import (
        multi_turn_checker,
        multi_turn_irrelevance_checker,
    )

    payload = case["payload"]
    names = {f["name"].replace(".", "_"): f["name"] for f in payload["functions"]}
    calls = [structured_calls(row) for row in rows]
    if any(call["name"] not in names for turn in calls for call in turn):
        return {"success": False, "reason": "undeclared_function"}
    if any(row.get("errors") for row in rows):
        return {"success": False, "reason": "agent_error"}
    if case["category"].startswith("multi_turn"):
        decoded = []
        for turn in calls:
            steps = []
            for call in turn:
                # Only declared names and JSON values become a Python literal
                # call for the native checker; never execute model-written code.
                expression = (
                    names[call["name"]]
                    + "("
                    + ", ".join(f"{k}={v!r}" for k, v in call.get("args", {}).items())
                    + ")"
                )
                if any(
                    not re.fullmatch(r"[A-Za-z_]\w*", key)
                    for key in call.get("args", {})
                ):
                    return {"success": False, "reason": "invalid_parameter_name"}
                steps.append([expression])
            decoded.append(steps)
        truth = payload["answer"]["ground_truth"]
        identity = hashlib.sha256(
            json.dumps(rows, sort_keys=True).encode()
        ).hexdigest()[:20]
        result = multi_turn_checker(
            decoded, truth, payload["entry"], case["category"], "routinghttp" + identity
        )
        irrelevant = multi_turn_irrelevance_checker(decoded, truth)
        return {
            "success": bool(result["valid"] and irrelevant["valid"]),
            "native": make_json_serializable(result),
            "irrelevance": irrelevant,
        }
    if case["category"] == "irrelevance":
        return {"success": not any(calls), "structured_calls": sum(map(len, calls))}
    path = (
        Path(sources)
        / "bfcl/berkeley-function-call-leaderboard/bfcl_eval/eval_checker/ast_eval/ast_checker.py"
    )
    tree = ast.parse(path.read_text())
    # Omit provider registries used only to select wire-name normalization.
    # All scorer functions/constants execute unchanged for every tested model.
    tree.body = [
        n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    scope = {
        "re": re,
        "Language": Language,
        "JAVA_TYPE_CONVERSION": JAVA_TYPE_CONVERSION,
        "JS_TYPE_CONVERSION": JS_TYPE_CONVERSION,
        "java_type_converter": java_type_converter,
        "js_type_converter": js_type_converter,
        "MODEL_CONFIG_MAPPING": {
            "routinghttp": SimpleNamespace(underscore_to_dot=True)
        },
    }
    exec(compile(tree, str(path), "exec"), scope)  # noqa: S102 - pinned upstream source, never model output
    prediction = [{call["name"]: call.get("args", {})} for call in calls[0]]
    result = scope["ast_checker"](
        payload["functions"],
        prediction,
        payload["answer"]["ground_truth"],
        Language.PYTHON,
        case["category"],
        "routinghttp",
    )
    return {"success": bool(result["valid"]), "native": make_json_serializable(result)}


def serializable_score(score):
    """Preserve native values, including BFCL's sets of missing parameters."""

    def encode(value):
        if isinstance(value, (set, frozenset)):
            return sorted(value, key=repr)
        raise TypeError(f"unsupported native score metadata: {type(value).__name__}")

    return json.loads(json.dumps(score, default=encode))


def score_public_rows(manifest, rows, root):
    sources = Path(manifest["benchmark_sources"])
    for folder in (
        "ifeval",
        "bfcl/berkeley-function-call-leaderboard",
        "livecodebench",
        "agentdojo/src",
    ):
        sys.path.insert(0, str(sources / folder))
    tool_audit = defaultdict(list)
    for line in (Path(root) / "audit.jsonl").read_text().splitlines():
        entry = json.loads(line)
        if entry["kind"] == "benchmark_tool":
            tool_audit[
                (entry["cohort"], entry["arm"], entry["experiment_case_id"])
            ].append(entry)
    grouped = defaultdict(list)
    cases = {c["id"]: c for c in manifest["cases"]}
    for row in rows:
        grouped[(row["cohort"], row["arm"], row["cluster"])].append(row)
    for (_, _, case_id), group in grouped.items():
        case = cases[case_id]
        group.sort(key=lambda row: int(row["id"].rsplit(":", 1)[1]))
        if case["source"] == "BFCL":
            score = score_bfcl(case, group, sources)
            for row in group:
                row.update(
                    success=score["success"],
                    native_score=score,
                    score_unit="whole_task",
                )
        elif case["source"] == "AgentDojo":
            from query_routing_benchmark_agent import AgentDojoBackend

            backend = AgentDojoBackend(case)
            for row in group:
                for entry in tool_audit[(row["cohort"], row["arm"], row["id"])]:
                    replayed = replay_agentdojo_call(backend, entry)
                    if not agentdojo_results_equal(replayed, entry["result"]):
                        raise ValueError(
                            "AgentDojo replay differs from the executed tool result"
                        )
                score = backend.score(row["answer"])
                row.update(
                    success=score["success"] and not bool(row.get("errors")),
                    native_score=score,
                    score_unit="task",
                    condition=case["condition"],
                    task_group=case["task_group"],
                )
        else:
            for row in group:
                score = score_static(case, row, sources)
                row.update(
                    success=score["success"], native_score=score, score_unit="task"
                )
    for row in rows:
        row["native_score"] = serializable_score(row["native_score"])
    (Path(root) / "paired-results.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    )
