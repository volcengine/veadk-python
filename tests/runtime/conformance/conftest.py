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

"""Fixtures for the runtime conformance suite.

Every scenario takes the ``harness`` fixture, which is parametrized over
``conformance_adapters.ADAPTERS``: one test id per ``(scenario, runtime)``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The offline Codex doubles and the scripted model live in the differential
# suite; import them by path, the same arrangement `tests/runtime/codex` uses,
# so this directory runs standalone and inside a full-tree collection.
_DIFFERENTIAL = str(Path(__file__).resolve().parents[1] / "differential")
if _DIFFERENTIAL not in sys.path:
    sys.path.insert(0, _DIFFERENTIAL)

import fake_codex_sdk  # noqa: E402
from conformance_adapters import ADAPTERS  # noqa: E402
from conformance_harness import ConformanceHarness  # noqa: E402


@pytest.fixture(params=sorted(ADAPTERS))
def harness(request, monkeypatch, tmp_path):
    """A function-scoped harness for one runtime.

    Function scope is what makes the suite ``pytest -n`` safe: every
    process-global the adapters touch (the shim registry, the memoized
    ``get_runtime``, compat's warning dedupe, ``PIAGENT_*`` env vars) is set up
    here and restored in ``teardown`` or by ``monkeypatch``.
    """
    adapter = ADAPTERS[request.param](monkeypatch, tmp_path)
    adapter.setup()
    try:
        yield ConformanceHarness(adapter)
    finally:
        adapter.teardown()
        fake_codex_sdk.REQUEST_LOG.clear()
