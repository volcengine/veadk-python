"""Freeze public Agent benchmark samples; upstream data stays outside Git.

Run with the separately prepared benchmark environment. This module makes no
provider calls. Sampling never depends on model answers or evaluation results.
"""

import ast
import base64
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace


def upstream_definitions(path, names, namespace=None):
    """Load unchanged upstream definitions without optional inference imports.

    The complete original file remains in the source manifest. No scorer body
    is rewritten; callers explicitly provide dependencies such as re/LMStyle.
    """
    tree = ast.parse(Path(path).read_text())
    nodes = [node for node in tree.body if getattr(node, "name", None) in names]
    if {node.name for node in nodes} != set(names):
        raise ValueError(f"upstream definitions missing in {path}")
    scope = dict(namespace or {})
    code = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__", names=[ast.alias(name="annotations")], level=0
            ),
            *nodes,
        ],
        type_ignores=[],
    )
    exec(compile(ast.fix_missing_locations(code), str(path), "exec"), scope)  # noqa: S102 - pinned upstream source, never model output
    return SimpleNamespace(**scope)


def stable_sample(items, count, label):
    if len(items) < count:
        raise ValueError(f"{label}: need {count} examples, found {len(items)}")
    seed = int(hashlib.sha256(label.encode()).hexdigest()[:16], 16)
    return random.Random(seed).sample(items, count)


def balanced_constraints(items, count):
    """Cover every IFEval constraint, then favor underrepresented constraints."""
    candidates = stable_sample(items, len(items), "IFEval-20261112")
    totals = Counter(i for item in items for i in item["instruction_id_list"])
    seen, selected = Counter(), []
    for _ in range(count):
        best = max(
            candidates,
            key=lambda item: sum(
                1 / (1 + seen[i]) / totals[i] ** 0.5
                for i in item["instruction_id_list"]
            ),
        )
        selected.append(best)
        seen.update(best["instruction_id_list"])
        candidates.remove(best)
    return selected


def read_jsonl(path):
    return [
        json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()
    ]


def prepare_static(sources):
    import pyarrow.parquet as pq

    sources = Path(sources)
    cases = []

    def add(family, category, identifier, prompt, payload, **extra):
        case_id = f"{family}-{identifier}"
        cases.append(
            {
                "id": case_id,
                "source": family,
                "category": category,
                "prompt": prompt,
                "oracle": "upstream",
                "benchmark": family,
                "payload": payload,
                "state": {"benchmark_id": case_id},
                **extra,
            }
        )

    data = read_jsonl(
        sources / "ifeval/instruction_following_eval/data/input_data.jsonl"
    )
    for item in balanced_constraints(data, 60):
        add(
            "IFEval",
            item["instruction_id_list"][0].split(":")[0],
            item["key"],
            item["prompt"],
            item,
        )

    data = pq.read_table(
        sources / "data/TIGER-Lab/MMLU-Pro/data/test-00000-of-00001.parquet"
    ).to_pylist()
    groups = defaultdict(list)
    for item in data:
        groups[item["category"]].append(item)
    assert len(groups) == 14
    for category, items in sorted(groups.items()):
        for item in stable_sample(items, 4, "MMLU-Pro-" + category):
            options = "\n".join(
                f"({chr(65 + i)}) {text}" for i, text in enumerate(item["options"])
            )
            prompt = (
                item["question"]
                + "\n"
                + options
                + "\nEnd your response with: The answer is (X)."
            )
            add("MMLU-Pro", category, item["question_id"], prompt, item)

    for path in sorted((sources / "data/MMMU/MMMU").glob("*/validation-*.parquet")):
        data = pq.read_table(path).to_pylist()
        item = stable_sample(data, 1, "MMMU-" + path.parent.name)[0]
        options = ast.literal_eval(item["options"])
        prompt = item["question"]
        if item["question_type"] == "multiple-choice":
            prompt += "\n" + "\n".join(
                f"({chr(65 + i)}) {text}" for i, text in enumerate(options)
            )
            prompt += "\nAnswer with the option letter in parentheses."
        else:
            prompt += "\nGive the final answer briefly."
        parts = []
        images = {}
        for key in sorted(item):
            if re.fullmatch(r"image_\d+", key) and item[key]:
                image = item[key]["bytes"]
                images[key] = hashlib.sha256(image).hexdigest()
                mime = "image/png" if image.startswith(b"\x89PNG") else "image/jpeg"
                parts.extend(
                    [
                        {"text": f"<{key.replace('_', ' ')}>"},
                        {
                            "inlineData": {
                                "mimeType": mime,
                                "data": base64.b64encode(image).decode(),
                            }
                        },
                    ]
                )
        if not images:
            raise ValueError(f"MMMU sample has no actual image: {item['id']}")
        payload = {k: v for k, v in item.items() if not k.startswith("image_")}
        payload["image_sha256"] = images
        parts.append({"text": prompt})
        add("MMMU", path.parent.name, item["id"], prompt, payload, parts=parts)

    data = json.loads((sources / "data/zai-org/LongBench-v2/data.json").read_text())
    groups = defaultdict(list)
    for item in data:
        groups[item["domain"]].append(item)
    assert len(groups) == 6
    template = (sources / "longbench/prompts/0shot.txt").read_text()
    for category, items in sorted(groups.items()):
        # Preserve complete documents. Within each family, include length
        # extremes and middle ranges rather than silently truncating contexts.
        ordered = sorted(items, key=lambda i: len(i["context"]))
        strata = [
            ordered[i * len(ordered) // 3 : (i + 1) * len(ordered) // 3]
            for i in range(3)
        ]
        for band, group in enumerate(strata):
            for item in stable_sample(group, 2, f"LongBench-v2-{category}-{band}"):
                prompt = template.replace("$DOC$", item["context"]).replace(
                    "$Q$", item["question"]
                )
                for letter in "ABCD":
                    prompt = prompt.replace(f"$C_{letter}$", item[f"choice_{letter}"])
                payload = {k: v for k, v in item.items() if k != "context"}
                payload["context_sha256"] = hashlib.sha256(
                    item["context"].encode()
                ).hexdigest()
                add(
                    "LongBench-v2",
                    category,
                    item["_id"],
                    prompt,
                    payload,
                    context_chars=len(prompt),
                    budget_band="within" if len(prompt) <= 32000 else "over",
                )

    lcb = sources / "livecodebench/lcb_runner"
    code_prompt = upstream_definitions(
        lcb / "prompts/code_generation.py",
        ["PromptConstants", "get_generic_question_template_answer"],
    )
    # release_v6 is the cumulative union of test.jsonl through test6.jsonl.
    groups = defaultdict(list)
    for suffix in ("", "2", "3", "4", "5", "6"):
        path = sources / f"data/livecodebench/code_generation_lite/test{suffix}.jsonl"
        with path.open() as stream:
            for line in stream:
                item = json.loads(line)
                key = hashlib.sha256(
                    f"LCB-generation-{item['platform']}-{item['question_id']}".encode()
                ).hexdigest()
                bucket = groups[item["difficulty"]]
                bucket.append((key, item))
                bucket.sort(key=lambda pair: pair[0])
                del bucket[4:]
    for difficulty, items in sorted(groups.items()):
        for _, item in items:
            add(
                "LiveCodeBench",
                "code_generation_" + difficulty,
                f"code-{item['platform']}-{item['question_id']}",
                code_prompt.get_generic_question_template_answer(
                    SimpleNamespace(**item)
                ),
                item,
                release="release_v6",
            )

    data = pq.read_table(
        sources / "data/livecodebench/execution-v2/data/test-00000-of-00001.parquet"
    ).to_pylist()
    fn = upstream_definitions(
        lcb / "prompts/code_execution.py", ["make_direct_output_prompt"]
    )
    ordered = sorted(data, key=lambda i: i["numsteps"])
    for band in range(3):
        group = ordered[band * len(ordered) // 3 : (band + 1) * len(ordered) // 3]
        for item in stable_sample(group, 3, f"LCB-execution-{band}"):
            add(
                "LiveCodeBench",
                f"code_execution_depth_{band + 1}",
                f"execution-{item['id']}",
                fn.make_direct_output_prompt((item["code"], item["input"])),
                item,
            )

    data = pq.read_table(
        sources / "data/livecodebench/test_generation/test.parquet"
    ).to_pylist()
    groups = defaultdict(list)
    for item in data:
        groups[item["difficulty"]].append(item)
    fn = upstream_definitions(
        lcb / "prompts/test_output_prediction.py",
        [
            "format_testcase_func_name_input",
            "parse_function_name_from_starter_code",
            "get_generic_question_template_test_completion",
        ],
    )
    for difficulty, items in sorted(groups.items()):
        for item in stable_sample(items, 3, "LCB-output-" + difficulty):
            test = json.loads(item["test"])[0]
            prompt = fn.get_generic_question_template_test_completion(
                SimpleNamespace(**item), test["input"]
            )
            prompt += "\nReturn the completed assertion in a Python code block."
            add(
                "LiveCodeBench",
                "test_output_" + difficulty,
                f"output-{item['question_id']}-{item['test_id']}",
                prompt,
                item,
            )
    # Keep protocol assignment balanced within each family and independent of
    # model outcomes. Both arms of a pair always use the same protocol.
    for family in sorted({c["source"] for c in cases}):
        selected = [c for c in cases if c["source"] == family]
        for index, case in enumerate(selected):
            case["protocol"] = "chat" if index % 2 else "responses"
    return cases


def prepare_bfcl(sources):
    root = Path(sources) / "bfcl/berkeley-function-call-leaderboard/bfcl_eval"
    config = {}
    exec((root / "constants/executable_backend_config.py").read_text(), config)  # noqa: S102 - pinned upstream source, never model output
    cases = []
    allocation = {
        "simple_python": 12,
        "parallel": 12,
        "multiple": 8,
        "irrelevance": 8,
        "multi_turn_base": 10,
        "multi_turn_miss_param": 10,
    }
    for category, count in allocation.items():
        data = read_jsonl(root / f"data/BFCL_v4_{category}.json")
        answers = (
            {
                i["id"]: i
                for i in read_jsonl(
                    root / f"data/possible_answer/BFCL_v4_{category}.json"
                )
            }
            if category != "irrelevance"
            else {}
        )
        for index, item in enumerate(stable_sample(data, count, "BFCL-" + category)):
            functions = list(item.get("function", []))
            for name in item.get("involved_classes", []):
                path = (
                    root
                    / "data/multi_turn_func_doc"
                    / config["MULTI_TURN_FUNC_DOC_FILE_MAPPING"][name]
                )
                functions.extend(read_jsonl(path))
            excluded = set(item.get("excluded_function", []))
            functions = [
                f for f in functions if f["name"].rsplit(".", 1)[-1] not in excluded
            ]
            identifier = "BFCL-" + item["id"]
            turns = []
            for messages in item["question"]:
                if not messages or any(m["role"] != "user" for m in messages):
                    raise ValueError(f"unsupported BFCL message shape: {item['id']}")
                turns.append(
                    {
                        "prompt": "\n".join(m["content"] for m in messages),
                        "oracle": "upstream",
                    }
                )
            cases.append(
                {
                    "id": identifier,
                    "source": "BFCL",
                    "benchmark": "BFCL",
                    "category": category,
                    "protocol": "responses" if index % 2 == 0 else "chat",
                    "turns": turns,
                    "state": {"benchmark_id": identifier},
                    "payload": {
                        "entry": item,
                        "functions": functions,
                        "answer": answers.get(item["id"]),
                    },
                }
            )
    return cases


def write_manifest(path, manifest):
    raw = json.dumps(manifest, ensure_ascii=False, indent=2, default=str).encode()
    Path(path).write_bytes(raw)
    Path(path).with_suffix(".sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")


def benchmark_app(case, cohort, arm):
    digest = hashlib.sha256(case["id"].encode()).hexdigest()[:16]
    return f"economy_bench_{digest}_{cohort}_{arm}"


def prepare_agentdojo(sources):
    import sys

    sys.path.insert(0, str(Path(sources) / "agentdojo/src"))
    from agentdojo.attacks.base_attacks import FixedJailbreakAttack
    from agentdojo.attacks.important_instructions_attacks import (
        ImportantInstructionsAttack,
    )
    from agentdojo.task_suite.load_suites import get_suite

    cases = []
    for domain in ("banking", "slack", "travel", "workspace"):
        suite = get_suite("v1.2.2", domain)
        attack = FixedJailbreakAttack(
            ImportantInstructionsAttack._JB_STRING, suite, None
        )
        eligible = []
        for task in suite.user_tasks.values():
            try:
                attack.get_injection_candidates(task)
            except ValueError as exc:
                if "not injectable" not in str(exc):
                    raise
            else:
                eligible.append(task)
        selected = stable_sample(eligible, 5, "AgentDojo-" + domain)
        injection_tasks = list(suite.injection_tasks.values())
        for index, task in enumerate(selected):
            injection_task = stable_sample(
                injection_tasks, 1, f"AgentDojo-{domain}-{task.ID}"
            )[0]
            injections = attack.attack(task, injection_task)
            for condition in ("clean", "attack"):
                identifier = f"AgentDojo-{domain}-{task.ID}-{condition}"
                cases.append(
                    {
                        "id": identifier,
                        "source": "AgentDojo",
                        "benchmark": "AgentDojo",
                        "category": domain,
                        "condition": condition,
                        "task_group": f"{domain}-{task.ID}",
                        "protocol": "responses" if index % 2 == 0 else "chat",
                        "prompt": task.PROMPT,
                        "oracle": "upstream",
                        "state": {"benchmark_id": identifier},
                        "payload": {
                            "suite": domain,
                            "version": "v1.2.2",
                            "user_task": task.ID,
                            "injection_task": injection_task.ID,
                            "injections": injections if condition == "attack" else {},
                            "attack": "important_instructions_no_names",
                            "eligible_population": len(eligible),
                        },
                    }
                )
    return cases
