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

import builtins
import importlib
import sys

import pytest


def test_mem0_backend_missing_dependency_points_to_database_extra(monkeypatch):
    module_name = "veadk.memory.long_term_memory_backends.mem0_backend"
    sys.modules.pop(module_name, None)
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "mem0":
            raise ImportError("No module named mem0")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    try:
        with pytest.raises(ImportError) as exc_info:
            importlib.import_module(module_name)
        message = str(exc_info.value)
        assert "veadk-python[database]" in message
        assert "mem0ai>=1.0.0,<2" in message
    finally:
        sys.modules.pop(module_name, None)
