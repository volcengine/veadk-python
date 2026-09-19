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

from veadk.evaluation.base_evaluator import BaseEvaluator

EVAL_SET_DATA = {
    "eval_set_id": "home_automation_agent_light_on_off_set",
    "name": "",
    "description": "This is an eval set that is used for unit testing `x` behavior of the Agent",
    "eval_cases": [
        {
            "eval_id": "eval_case_id",
            "conversation": [
                {
                    "invocation_id": "b7982664-0ab6-47cc-ab13-326656afdf75",  # Unique identifier for the invocation.
                    "user_content": {  # Content provided by the user in this invocation. This is the query.
                        "parts": [{"text": "Turn off device_2 in the Bedroom."}],
                        "role": "user",
                    },
                    "final_response": {  # Final response from the agent that acts as a reference of benchmark.
                        "parts": [{"text": "I have set the device_2 status to off."}],
                        "role": "model",
                    },
                    "intermediate_data": {
                        "tool_uses": [  # Tool use trajectory in chronological order.
                            {
                                "args": {
                                    "location": "Bedroom",
                                    "device_id": "device_2",
                                    "status": "OFF",
                                },
                                "name": "set_device_info",
                            }
                        ],
                        "intermediate_responses": [],  # Any intermediate sub-agent responses.
                    },
                }
            ],
            "session_input": {  # Initial session input.
                "app_name": "home_automation_agent",
                "user_id": "test_user",
                "state": {},
            },
        }
    ],
}

TRACE_SET_DATA = [
    {
        "name": "execute_tool get_city_weather",
        "span_id": 4497348974122733469,
        "trace_id": 142655176138954930885272077198014871976,
        "start_time": 1758158957162250000,
        "end_time": 1758158957162426000,
        "attributes": {
            "gen_ai.tool.name": "get_city_weather",
            "gen_ai.tool.input": '{"name": "get_city_weather", "description": "Retrieves the weather information of a given city. the args must in English", "parameters": {"city": "Beijing"}}',
            "gen_ai.tool.output": '{"id": "call_w4bj25flpvs74zgyyiquqh5s", "name": "get_city_weather", "response": {"result": "Sunny, 25°C"}}',
        },
        "parent_span_id": 574819447039686650,
    },
    {
        "name": "call_llm",
        "span_id": 574819447039686650,
        "trace_id": 142655176138954930885272077198014871976,
        "start_time": 1758158945807630000,
        "end_time": 1758158957171304000,
        "attributes": {
            "gen_ai.app.name": "veadk_default_app",
            "gen_ai.user.id": "veadk_default_user",
            "gen_ai.prompt.0.role": "user",
            "gen_ai.prompt.0.content": "How is the weather like in BeiJing?",
        },
        "parent_span_id": 13789664766018020416,
    },
    {
        "name": "call_llm",
        "span_id": 9007934154052797946,
        "trace_id": 142655176138954930885272077198014871976,
        "start_time": 1758158957171713000,
        "end_time": 1758158964035230000,
        "attributes": {
            "gen_ai.app.name": "veadk_default_app",
            "gen_ai.user.id": "veadk_default_user",
            "gen_ai.prompt.0.content": "How is the weather like in BeiJing?",
            "gen_ai.completion.0.content": "The weather in Beijing is sunny with a temperature of 25°C.",
        },
        "parent_span_id": 13789664766018020416,
    },
    {
        "name": "agent_run [chat_robot]",
        "span_id": 13789664766018020416,
        "trace_id": 142655176138954930885272077198014871976,
        "start_time": 1758158945807350000,
        "end_time": 1758158964035291000,
        "attributes": {},
        "parent_span_id": 5589459087402275636,
    },
    {
        "name": "invocation",
        "span_id": 5589459087402275636,
        "trace_id": 142655176138954930885272077198014871976,
        "start_time": 1758158945807233000,
        "end_time": 1758158964035304000,
        "attributes": {},
        "parent_span_id": None,
    },
]


def test_evaluator():
    base_evaluator = BaseEvaluator(agent=None, name="test_evaluator")

    # save data to file
    eval_set_file_path = "./eval_set_for_test_evaluator.json"
    with open(eval_set_file_path, "w") as f:
        json.dump(EVAL_SET_DATA, f)

    base_evaluator.build_eval_set(file_path=eval_set_file_path)

    assert len(base_evaluator.invocation_list) == 1
    assert len(base_evaluator.invocation_list[0].invocations) == 1
    assert (
        base_evaluator.invocation_list[0].invocations[0].invocation_id
        == "b7982664-0ab6-47cc-ab13-326656afdf75"
    )

    os.remove(eval_set_file_path)


def test_tracing_file_to_evalset():
    base_evaluator = BaseEvaluator(agent=None, name="test_evaluator")

    # save data to file
    tracing_file_path = "./tracing_for_test_evaluator.json"
    with open(tracing_file_path, "w") as f:
        json.dump(TRACE_SET_DATA, f)

    base_evaluator.build_eval_set(file_path=tracing_file_path)

    assert len(base_evaluator.invocation_list) == 1
    assert len(base_evaluator.invocation_list[0].invocations) == 1
    assert (
        base_evaluator.invocation_list[0].invocations[0].expected_output
        == "The weather in Beijing is sunny with a temperature of 25°C."
    )

    os.remove(tracing_file_path)


def test_tracing_file_creates_isolated_eval_case_per_sorted_trace(tmp_path):
    trace_a = 101
    trace_b = 202

    def call_llm(trace_id, start_time, app_name, user_id, prompt="", completion=""):
        return {
            "name": "call_llm",
            "trace_id": trace_id,
            "start_time": start_time,
            "attributes": {
                "gen_ai.app.name": app_name,
                "gen_ai.user.id": user_id,
                "gen_ai.prompt.0.content": prompt,
                "gen_ai.completion.0.content": completion,
            },
        }

    def execute_tool(start_time, tool_name):
        return {
            "name": f"execute_tool {tool_name}",
            "trace_id": trace_a,
            "start_time": start_time,
            "attributes": {
                "gen_ai.tool.name": tool_name,
                "gen_ai.tool.input": json.dumps({"parameters": {"order": tool_name}}),
                "gen_ai.tool.output": json.dumps({"id": f"call-{tool_name}"}),
            },
        }

    tracing_data = [
        call_llm(trace_a, 40, "app-a", "user-a", completion="answer-a"),
        call_llm(trace_b, 60, "app-b", "user-b", completion="answer-b"),
        execute_tool(30, "second"),
        call_llm(trace_b, 50, "app-b", "user-b", prompt="question-b"),
        call_llm(trace_a, 10, "app-a", "user-a", prompt="question-a"),
        execute_tool(20, "first"),
    ]
    tracing_file_path = tmp_path / "tracing.json"
    tracing_file_path.write_text(json.dumps(tracing_data))

    eval_set = BaseEvaluator(
        agent=None, name="test_evaluator"
    )._build_eval_set_from_tracing_json(str(tracing_file_path))

    assert len(eval_set.eval_cases) == 2
    eval_cases = {
        eval_case.session_input.app_name: eval_case for eval_case in eval_set.eval_cases
    }

    case_a = eval_cases["app-a"]
    assert case_a.session_input.user_id == "user-a"
    assert case_a.creation_timestamp == 10 / 1e9
    assert case_a.conversation[0].user_content.parts[0].text == "question-a"
    assert case_a.conversation[0].final_response.parts[0].text == "answer-a"
    assert [
        tool.name for tool in case_a.conversation[0].intermediate_data.tool_uses
    ] == ["first", "second"]

    case_b = eval_cases["app-b"]
    assert case_b.session_input.user_id == "user-b"
    assert case_b.creation_timestamp == 50 / 1e9
    assert case_b.conversation[0].user_content.parts[0].text == "question-b"
    assert case_b.conversation[0].final_response.parts[0].text == "answer-b"
    assert case_b.conversation[0].intermediate_data.tool_uses == []
