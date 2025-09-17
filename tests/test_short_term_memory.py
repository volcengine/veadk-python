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

import asyncio
import os

from veadk.memory.short_term_memory import ShortTermMemory
from veadk.utils.misc import formatted_timestamp


def test_short_term_memory():
    # local
    memory = ShortTermMemory(backend="local")
    asyncio.run(
        memory.session_service.create_session(
            app_name="app", user_id="user", session_id="session"
        )
    )
    session = asyncio.run(
        memory.session_service.get_session(
            app_name="app", user_id="user", session_id="session"
        )
    )
    assert session is not None

    # sqlite
    memory = ShortTermMemory(
        backend="sqlite",
        local_database_path=f"/tmp/tmp_for_test_{formatted_timestamp()}.db",
    )
    asyncio.run(
        memory.session_service.create_session(
            app_name="app", user_id="user", session_id="session"
        )
    )
    session = asyncio.run(
        memory.session_service.get_session(
            app_name="app", user_id="user", session_id="session"
        )
    )
    assert session is not None
    assert os.path.exists(memory.local_database_path)
    os.remove(memory.local_database_path)
