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


import json
import os

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams
from google.adk.agents.callback_context import CallbackContext
from google.adk.cli.utils.agent_loader import AgentLoader
from google.adk.models.llm_response import LlmResponse

from veadk.agent import Agent
from veadk.cli.services.agentpilot.agentpilot import AgentPilot
from veadk.config import getenv
from veadk.evaluation.deepeval_evaluator.deepeval_evaluator import DeepevalEvaluator
from veadk.evaluation.eval_set_recorder import EvalSetRecorder
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runner import Runner
from veadk.tracing.telemetry.exporters.inmemory_exporter import InMemoryExporter
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer


class AgentProcessor:
    def __init__(self, agents_dir: str = ""):
        self.agents_dir = agents_dir

        self.agent: Agent = None

        self.runner: Runner = None

        self.prompt_optimizer: AgentPilot = AgentPilot(
            api_key=getenv("AGENT_PILOT_API_KEY")
        )

        self.trace_dict = {}

        self.short_term_memory = None

        self.evaluator = None
        self.evalset_recorder = None

    def get_agent_names(self) -> list[str]:
        agent_dirs = []

        for dirpath, dirnames, filenames in os.walk(self.agents_dir):
            required_files = {"agent.py", "__init__.py"}
            existing_files = set(filenames)
            if required_files.issubset(existing_files):
                agent_dirs.append(dirpath)

        return [agent_dir.split("/")[-1] for agent_dir in agent_dirs]

    def _set_short_term_memory(self, backend: str, db_url: str):
        return ShortTermMemory(backend=backend, db_url=db_url)

    async def set_runner(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
        short_term_memory_backend: str,
        short_term_memory_db_url: str,
    ):
        short_term_memory = self._set_short_term_memory(
            backend=short_term_memory_backend, db_url=short_term_memory_db_url
        )
        await short_term_memory.create_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )

        self.short_term_memory = short_term_memory

    def set_agent(
        self,
        agent_name: str,
    ):
        try:
            agent_loader = AgentLoader(agents_dir=self.agents_dir)
            agent = agent_loader.load_agent(agent_name)
            self.agent = agent
            self.agent.after_model_callback = after_model_callback
            if not self.agent.tracers:
                exporter = InMemoryExporter()
                self.agent.tracers = [OpentelemetryTracer(exporters=[exporter])]
            self.runner = Runner(
                agent=self.agent, short_term_memory=self.short_term_memory
            )
            self.evalset_recorder = EvalSetRecorder(
                self.short_term_memory.session_service
            )
        except Exception as e:
            print(e)

    def get_memory_status(self) -> dict:
        short_term_memory_backend = self.runner.short_term_memory.backend
        long_term_memory_backend = "No long term memory provided."
        if self.agent.long_term_memory:
            long_term_memory_backend = self.agent.long_term_memory.backend
        return {
            "short_term_memory_backend": short_term_memory_backend,
            "long_term_memory_backend": long_term_memory_backend,
        }

    async def get_testcases(self, session_id: str):
        try:
            dump_path = await self.evalset_recorder.dump(
                self.runner.app_name, self.runner.user_id, session_id
            )
            os.remove(dump_path)
        except Exception as _:
            pass

        dump_path = await self.evalset_recorder.dump(
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

    def optimize_prompt(self, prompt: str, feedback: str) -> str:
        self.agent.instruction = prompt
        return self.prompt_optimizer.optimize(agents=[self.agent], feedback=feedback)

    async def get_history_sessions(self, session_id: str) -> list[str]:
        events = []

        session_service = self.runner.short_term_memory.session_service
        session = await session_service.get_session(
            app_name=self.runner.app_name,
            user_id=self.runner.user_id,
            session_id=session_id,
        )

        # prevent no session created
        if session:
            for event in session.events:
                event_string = event.model_dump_json(exclude_none=True, by_alias=True)
                events.append(event_string)
                print(event_string)
            return events
        else:
            return []

    async def get_event(self, session_id: str, invocation_id: str) -> str:
        session_service = self.runner.short_term_memory.session_service
        session = await session_service.get_session(
            app_name=self.runner.app_name,
            user_id=self.runner.user_id,
            session_id=session_id,
        )

        # prevent no session created
        if session:
            for event in session.events:
                if event.invocation_id == invocation_id:
                    # find model response
                    if (
                        event.author != "user"
                        and event.content.parts[0]
                        and event.content.parts[0].text
                    ):
                        return event.model_dump_json(exclude_none=True, by_alias=True)
            return ""
        return ""

    async def run_sse(self, session_id: str, prompt: str):
        self.agent.model._additional_args["stream"] = True
        self.agent.model._additional_args["stream_options"] = {"include_usage": True}
        self.agent.after_model_callback = after_model_callback

        if self.agent and self.runner:
            async for chunk in self.runner.run_sse(
                session_id=session_id, prompt=prompt
            ):
                yield chunk

    def trace(self, session_id: str) -> str:
        tracing_file_path = self.runner.save_tracing_file(session_id=session_id)

        content = "No content!"
        with open(tracing_file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
            content = json.dumps(data, ensure_ascii=False, indent=2)

        # remove file
        if os.path.exists(tracing_file_path):
            os.remove(tracing_file_path)

        return content

    async def save_session_to_long_term_memory(self, session_id: str):
        """Save session to long term memory"""
        await self.runner.save_session_to_long_term_memory(session_id)


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
