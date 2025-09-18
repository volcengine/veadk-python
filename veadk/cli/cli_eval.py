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

import click

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


@click.command()
@click.option(
    "--agent-dir",
    default=".",
    help="To-be-evaluated agent directory. Must export `root_agent` in `agent.py`",
)
@click.option(
    "--agent-a2a-url",
    default=None,
    help="To-be-evaluated agent URL. The agent should be deployed as A2A mode.",
)
@click.option(
    "--evalset-file",
    required=True,
    help="Google ADK formatted evalset file path",
)
@click.option(
    "--evaluator",
    type=click.Choice(["adk", "deepeval"], case_sensitive=False),
    help="Evaluator type, choose `adk` or `deepeval`",
)
@click.option(
    "--judge-model-name",
    default="doubao-1-5-pro-256k-250115",
    help="Judge model name, default is `doubao-1-5-pro-256k-250115`. Useless under `adk` evaluator.",
)
@click.option(
    "--volcengine-access-key",
    default=None,
    help="Volcengine access key for using Volcengine models",
)
@click.option(
    "--volcengine-secret-key",
    default=None,
    help="Volcengine secret key for using Volcengine models",
)
def eval(
    agent_dir: str,
    agent_a2a_url: str,
    evalset_file: str,
    evaluator: str,
    judge_model_name: str,
    volcengine_access_key: str,
    volcengine_secret_key: str,
) -> None:
    import asyncio
    import os
    from pathlib import Path

    from google.adk.cli.utils.agent_loader import AgentLoader

    from veadk.a2a.remote_ve_agent import RemoteVeAgent
    from veadk.config import getenv, settings
    from veadk.prompts.prompt_evaluator import eval_principle_prompt

    try:
        from deepeval.metrics import GEval, ToolCorrectnessMetric
        from deepeval.test_case import LLMTestCaseParams

        from veadk.evaluation.adk_evaluator import ADKEvaluator
        from veadk.evaluation.deepeval_evaluator import DeepevalEvaluator
    except ImportError:
        raise ImportError(
            "Please install veadk with `[evaluation]` extras, e.g., `pip install veadk-python[eval]`"
        )

    # ====== prepare agent instance ======
    if not agent_dir and not agent_a2a_url:
        raise ValueError(
            "Option `--agent-dir` or  `--agent-a2a-url` should be provided one of them."
        )

    if agent_dir and agent_a2a_url:
        logger.warning(
            "`--agent-dir` and `--agent-a2a-url` are both provided, will use `--agent-a2a-url`."
        )
        agent_instance = RemoteVeAgent(name="a2a_agent", url=agent_a2a_url)
        logger.info(f"Loaded agent from {agent_a2a_url}")

    if not agent_dir and agent_a2a_url:
        agent_instance = RemoteVeAgent(name="a2a_agent", url=agent_a2a_url)
        logger.info(f"Loaded agent from {agent_a2a_url}")

    if agent_dir and not agent_a2a_url:
        agent_instance = AgentLoader(str(Path(agent_dir).parent.resolve())).load_agent(
            str(Path(agent_dir).name)
        )
        logger.info(f"Loaded agent from {agent_dir}, agent name: {agent_instance.name}")

    # ====== prepare envs ======
    if volcengine_access_key and "VOLCENGINE_ACCESS_KEY" not in os.environ:
        os.environ["VOLCENGINE_ACCESS_KEY"] = volcengine_access_key
    if volcengine_secret_key and "VOLCENGINE_SECRET_KEY" not in os.environ:
        os.environ["VOLCENGINE_SECRET_KEY"] = volcengine_secret_key

    # ====== prepare evaluator instance ======
    evaluator_instance = None
    if evaluator == "adk" and judge_model_name:
        logger.warning(
            "Using Google ADK evaluator, `--judge-model-name` will be ignored."
        )
        evaluator_instance = ADKEvaluator(agent=agent_instance)

        asyncio.run(evaluator_instance.evaluate(eval_set_file_path=evalset_file))

    if evaluator == "deepeval":
        if not volcengine_access_key:
            volcengine_access_key = getenv("VOLCENGINE_ACCESS_KEY")
        if not volcengine_secret_key:
            volcengine_secret_key = getenv("VOLCENGINE_SECRET_KEY")

        evaluator_instance = DeepevalEvaluator(
            agent=agent_instance,
            judge_model_api_key=settings.model.api_key,
            judge_model_name=judge_model_name,
        )

        judge_model = evaluator_instance.judge_model

        metrics = [
            GEval(
                threshold=0.8,
                name="Base Evaluation",
                criteria=eval_principle_prompt,
                evaluation_params=[
                    LLMTestCaseParams.INPUT,
                    LLMTestCaseParams.ACTUAL_OUTPUT,
                    LLMTestCaseParams.EXPECTED_OUTPUT,
                ],
                model=judge_model,
            ),
            ToolCorrectnessMetric(threshold=0.5),
        ]

        asyncio.run(
            evaluator_instance.evaluate(
                eval_set_file_path=evalset_file, metrics=metrics
            )
        )
