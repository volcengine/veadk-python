# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""Minimal regression: chat_exception_counter must use a count unit, not "time".

This static source check requires only the Python standard library; it guards
telemetry metadata consistency against a copy-paste of a duration unit from a
histogram onto a counter. The recorder-based runtime test in
test_portal_metrics.py exercises runtime wiring and requires google.adk.
"""
import re
from pathlib import Path


def _counter_block(src, var):
    m = re.search(var + r"\s*=\s*self\.meter\.create_counter\((.*?)\)", src, re.S)
    assert m, var + " block not found"
    unit = re.search(r'unit\s*=\s*"([^"]*)"', m.group(1))
    return unit.group(1) if unit else None


def _source():
    return (
        Path(__file__).resolve().parent.parent
        / "veadk"
        / "tracing"
        / "telemetry"
        / "portal_metrics.py"
    ).read_text(encoding="utf-8")


def test_chat_exception_counter_uses_count_unit():
    assert _counter_block(_source(), "self.chat_exception_counter") in ("1", "count")


def test_sibling_counters_unchanged():
    # scope guard: these units must remain as-is (not altered by this change)
    src = _source()
    assert _counter_block(src, "self.llm_invoke_counter") == "count"
    assert _counter_block(src, "self.skill_download_counter") == "1"
    assert _counter_block(src, "self.skill_load_counter") == "1"
