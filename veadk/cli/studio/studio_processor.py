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

import os

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse

from veadk import Agent
from veadk.cli.services.agentpilot.agentpilot import AgentPilot
from veadk.config import getenv
from veadk.evaluation.deepeval_evaluator import DeepevalEvaluator
from veadk.evaluation.eval_set_recorder import EvalSetRecorder
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runner import Runner
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer


class StudioProcessor:
    def __init__(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
        agent: Agent,
        short_term_memory: ShortTermMemory,
    ) -> None:
        self.agent = agent
        self.short_term_memory = short_term_memory

        self.tracer = None
        if self.agent.tracers == []:
            self.tracer = OpentelemetryTracer()
            self.agent.tracer = [self.tracer]
        else:
            self.tracer = self.agent.tracers[0]

        if self.agent.after_model_callback:
            self.agent.after_model_callback.append(after_model_callback)
        else:
            self.agent.after_model_callback = [after_model_callback]

        self.runner = Runner(
            agent=self.agent,
            short_term_memory=self.short_term_memory,
            app_name=app_name,
            user_id=user_id,
        )
        self.session_id = session_id
        self.agent_pilot = AgentPilot(api_key=getenv("AGENT_PILOT_API_KEY"))

        self.eval_set_recorder = EvalSetRecorder(
            session_service=self.short_term_memory.session_service, eval_set_id="studio"
        )
        self.evaluator = DeepevalEvaluator(agent=self.agent)

    async def get_testcases(self):
        session_id = self.session_id
        try:
            dump_path = await self.eval_set_recorder.dump(
                self.runner.app_name, self.runner.user_id, session_id
            )
            os.remove(dump_path)
        except Exception as _:
            pass

        dump_path = await self.eval_set_recorder.dump(
            self.runner.app_name, self.runner.user_id, session_id
        )
        self._eval_set_path = dump_path

        # 2. build
        self.evaluator = DeepevalEvaluator(self.agent)
        self.evaluator.generate_eval_data(dump_path)

        test_cases = self.evaluator.get_data()

        return test_cases

    async def evaluate(self):
        metrics = [
            GEval(
                name="Correctness&MatchDegree",
                model=self.evaluator.judge_model,
                criteria="Judge the correctness and match degree of the model output with the expected output.",
                evaluation_params=[
                    LLMTestCaseParams.INPUT,
                    LLMTestCaseParams.ACTUAL_OUTPUT,
                    LLMTestCaseParams.EXPECTED_OUTPUT,
                ],
            ),
        ]

        await self.evaluator.eval(
            eval_set_file_path=self._eval_set_path, metrics=metrics
        )
        test_cases = self.evaluator.get_data()

        os.remove(self._eval_set_path)
        self._eval_set_path = ""

        return test_cases


def after_model_callback(callback_context: CallbackContext, llm_response: LlmResponse):
    if llm_response.content and llm_response.content.parts:
        valid_parts = [
            part
            for part in llm_response.content.parts
            if not (part.function_call and not part.function_call.name)
        ]
        if len(valid_parts) < len(llm_response.content.parts):
            llm_response.content.parts = valid_parts
    return llm_response
