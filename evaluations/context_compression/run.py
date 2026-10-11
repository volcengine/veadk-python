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

"""Run paired, synthetic evaluations only against an explicitly selected Ark API.

The launcher drops ambient configuration and suppresses framework output before
credentials are used. Reports contain scores/counters only, never model text.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
ARK_HOSTS = {"ark.cn-beijing.volces.com", "ark.cn-shanghai.volces.com"}


def validate_target(api_base: str, model: str, key_env: str):
    url = urlsplit(api_base)
    if (
        url.scheme != "https"
        or url.hostname not in ARK_HOSTS
        or url.port not in (None, 443)
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path.rstrip("/") != "/api/v3"
    ):
        raise ValueError("evaluation_requires_explicit_ark_endpoint")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,150}", model):
        raise ValueError("invalid_model_identifier")
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key_env):
        raise ValueError("invalid_credential_environment_name")


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--live", action="store_true", help="Use the specified authorized Ark endpoint"
    )
    result.add_argument("--api-base", required=True)
    result.add_argument("--model", required=True)
    result.add_argument(
        "--key-env",
        required=True,
        help="Environment variable NAME, never the credential value",
    )
    result.add_argument("--context-window", type=int, required=True)
    result.add_argument("--input-limit", type=int)
    result.add_argument("--output-reserve", type=int, default=4096)
    result.add_argument("--variants", type=int, default=4)
    result.add_argument("--repeats", type=int, default=3)
    result.add_argument("--max-model-calls", type=int, default=200)
    result.add_argument("--max-seconds", type=int, default=3600)
    result.add_argument("--case-pause-seconds", type=float, default=0)
    result.add_argument(
        "--tiers",
        nargs="+",
        choices=["short", "pressure", "overflow"],
        default=["short", "pressure", "overflow"],
    )
    result.add_argument("--report", type=Path, required=True)
    result.add_argument(
        "--case-ids", nargs="+", default=[], help="Run selected paired cases"
    )
    result.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    return result


def isolated_environment(args):
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "LANG", "LC_ALL", "SYSTEMROOT", "TMPDIR"}
    }
    credential = os.environ.get(args.key_env)
    if not credential:
        raise ValueError("credential_environment_not_set")
    env.update(
        {
            "PYTHONPATH": str(ROOT),
            "PYTHON_DOTENV_DISABLED": "1",
            "MODEL_AGENT_API_KEY": credential,
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
            "HF_HUB_OFFLINE": "1",
            "DO_NOT_TRACK": "1",
            "OTEL_SDK_DISABLED": "true",
            "VEADK_CONTEXT_EVAL_WORKER": "1",
        }
    )
    return env


def main():
    if __package__ in (None, ""):
        sys.path.insert(0, str(ROOT))
    args = parser().parse_args()
    try:
        validate_target(args.api_base, args.model, args.key_env)
        if not args.live:
            raise ValueError("live_evaluation_not_enabled")
        if not 1 <= args.variants <= 1000 or not 1 <= args.repeats <= 10:
            raise ValueError("invalid_dataset_size")
        if not 1 <= args.max_model_calls <= 20000 or not 1 <= args.max_seconds <= 43200:
            raise ValueError("invalid_evaluation_budget")
        if args.context_window < 16000 or args.output_reserve <= 0:
            raise ValueError("invalid_capacity")
        if not 0 <= args.case_pause_seconds <= 60:
            raise ValueError("invalid_case_pause")
        from evaluations.context_compression.corpus import select_cases

        select_cases(args.variants, args.tiers, args.case_ids)
    except ValueError as error:
        # Only fixed error identifiers created above; URL parser errors are not echoed.
        known = str(error)
        print(
            known
            if re.fullmatch(r"[a-z_]+", known)
            else "invalid_evaluation_configuration"
        )
        return 2
    if args.worker:
        if os.getenv("VEADK_CONTEXT_EVAL_WORKER") != "1":
            return 2
        import asyncio

        from evaluations.context_compression.worker import evaluate

        return asyncio.run(evaluate(args))
    try:
        env = isolated_environment(args)
    except ValueError:
        print("credential_environment_not_set")
        return 2
    args.report = args.report.resolve()
    if args.report.exists():
        print("report_already_exists")
        return 2
    # Frameworks may log exception payloads. Discard both file descriptors, not
    # merely Python stdout, before any credential-bearing library is imported.
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        *sys.argv[1:],
        "--worker",
        "--report",
        str(args.report),
    ]
    with tempfile.TemporaryDirectory(prefix="veadk-context-evaluation-") as cwd:
        try:
            completed = subprocess.run(
                command,
                env=env,
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=args.max_seconds + 30,
                check=False,
            )
        except subprocess.TimeoutExpired:
            print("evaluation_time_budget_exhausted; inspect partial report")
            return 2
        except KeyboardInterrupt:
            print("evaluation_interrupted; partial report retained")
            return 130
    print(
        "evaluation_finished; inspect aggregate report"
        if completed.returncode == 0
        else "evaluation_incomplete_or_failed; inspect aggregate report"
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
