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

import pytest

from veadk.knowledgebase import KnowledgeBase
from veadk.knowledgebase.backends.in_memory_backend import InMemoryKnowledgeBackend


@pytest.mark.asyncio
async def test_knowledgebase():
    os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

    app_name = "kb_test_app"
    kb = KnowledgeBase(backend="local", app_name=app_name)

    assert isinstance(kb._backend, InMemoryKnowledgeBackend)
