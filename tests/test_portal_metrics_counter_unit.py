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
histogram onto a counter. The full recorder-based test in
test_portal_metrics.py exercises runtime wiring and requires google.adk.
"""
import re
from pathlib import Path


def test_chat_exception_counter_uses_count_unit():
    src = (
        Path(__file__).resolve().parent.parent
        / "veadk"
        / "tracing"
        / "telemetry"
        / "portal_metrics.py"
    ).read_text(encoding="utf-8")

    m = re.search(
        r"chat_exception_counter\s*=\s*self\.meter\.create_counter\((.*?)\)",
        src,
        re.S,
    )
    assert m, "chat_exception_counter create_counter block not found"
    block = m.group(1)
    unit = re.search(r'unit\s*=\s*"([^"]*)"', block)
    assert unit, "no unit= found on chat_exception_counter"
    assert unit.group(1) in ("1", "count"), (
        f"chat_exception_counter unit must be a count unit, got {unit.group(1)!r}"
    )
