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

import pytest
from utils import generate_events, generate_session

from veadk.evaluation.eval_set_recorder import EvalSetRecorder
from veadk.memory.short_term_memory import ShortTermMemory

APP_NAME = "app"
USER_ID = "user"
SESSION_ID = "session"

EVAL_SET_ID = "temp_unittest"


@pytest.mark.asyncio
async def test_runtime_data_collecting():
    session_service = ShortTermMemory().session_service

    mocked_events = generate_events(10)
    mocked_session = generate_session(mocked_events, APP_NAME, USER_ID, SESSION_ID)

    session_service.sessions = {
        APP_NAME: {
            USER_ID: {
                SESSION_ID: mocked_session,
            }
        }
    }

    recorder = EvalSetRecorder(session_service=session_service, eval_set_id=EVAL_SET_ID)
    dump_path = await recorder.dump(APP_NAME, USER_ID, SESSION_ID)

    assert dump_path == f"/tmp/{APP_NAME}/{recorder.eval_set_id}.evalset.json"
    assert os.path.exists(dump_path) and os.path.isfile(dump_path)
    assert os.path.getsize(dump_path) > 0

    with open(dump_path, "r") as f:
        data = json.load(f)
        assert data["eval_set_id"] == EVAL_SET_ID
        assert len(data["eval_cases"]) == 1

    os.remove(dump_path)
