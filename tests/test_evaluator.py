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


def test_evaluator():
    base_evaluator = BaseEvaluator(agent=None, name="test_evaluator")

    # save data to file
    eval_set_file_path = "./eval_set_for_test_evaluator.json"
    with open(eval_set_file_path, "w") as f:
        json.dump(EVAL_SET_DATA, f)

    base_evaluator.generate_eval_data(eval_set_file_path=eval_set_file_path)

    assert len(base_evaluator.invocation_list) == 1
    assert len(base_evaluator.invocation_list[0].invocations) == 1
    assert (
        base_evaluator.invocation_list[0].invocations[0].invocation_id
        == "b7982664-0ab6-47cc-ab13-326656afdf75"
    )

    os.remove(eval_set_file_path)
