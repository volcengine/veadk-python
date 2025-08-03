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

import pytest

from veadk.knowledgebase import KnowledgeBase


@pytest.mark.asyncio
async def test_knowledgebase():
    app_name = "kb_test_app"
    key = "Supercalifragilisticexpialidocious"
    kb = KnowledgeBase(backend="local")
    # Attempt to delete any existing data for the app_name before adding new data
    kb.add(
        data=[f"knowledgebase_id is {key}"],
        app_name=app_name,
    )
    res_list = kb.search(
        query="knowledgebase_id",
        app_name=app_name,
    )
    res = "".join(res_list)
    assert key in res, f"Test failed for backend local res is {res}"
    assert key in res, f"Test failed for backend local res is {res}"
    assert key in res, f"Test failed for backend local res is {res}"
