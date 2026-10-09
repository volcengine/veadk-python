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

"""Keep Studio route tests independent of public registry availability."""

import pytest


@pytest.fixture(autouse=True)
def isolated_studio_image_defaults(monkeypatch):
    from frontend.server import mpa_creation

    async def resolve(fields=("runtimeImage", "workerImage")):
        return {
            field: f"registry.example/{field}@sha256:" + "a" * 64 for field in fields
        }

    monkeypatch.setattr(mpa_creation, "resolve_studio_images", resolve)
