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

"""Test fixtures for the codex runtime tests.

``veadk.runtime.codex.runtime`` hard-imports ``openai_codex`` (the optional
codex extra). It is installed in dev environments but not in the base CI image,
so stub the module here — before the codex test modules import — when it is
absent. Tests mock ``AsyncCodex`` behaviour anyway; the stub only lets the
import chain succeed so the runtime/translate/proxy logic can be exercised.
"""

import sys
import types
from unittest.mock import MagicMock

try:
    import openai_codex  # noqa: F401
except ImportError:
    _stub = types.ModuleType("openai_codex")
    # Name imported by veadk.runtime.codex.runtime; tests patch its usage.
    _stub.AsyncCodex = MagicMock()  # type: ignore[attr-defined]
    sys.modules["openai_codex"] = _stub
