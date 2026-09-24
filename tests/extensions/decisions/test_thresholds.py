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

"""Threshold parsing tests shared by the decision points."""

from __future__ import annotations

import logging

import pytest

from veadk.extensions.decisions.thresholds import (
    DEFAULT_JUDGEMENT_THRESHOLD,
    probability_threshold,
)


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_an_unset_threshold_keeps_the_default(raw: object) -> None:
    assert probability_threshold(raw) == DEFAULT_JUDGEMENT_THRESHOLD


@pytest.mark.parametrize("raw", ["0", "0.0", "0.5", "0.87", "1", "1.0", 0.3])
def test_an_in_range_threshold_is_kept(raw: object) -> None:
    assert probability_threshold(raw) == float(raw)  # type: ignore[arg-type]


def test_an_out_of_range_threshold_is_clamped_to_its_intent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # 1.5 原意是"永不生效"，夹到 1.0 仍保留这个语义；-1 同理。
    with caplog.at_level(logging.WARNING):
        assert probability_threshold("1.5") == 1.0
        assert probability_threshold("-1") == 0.0
        assert probability_threshold("inf") == 1.0
        assert probability_threshold("-inf") == 0.0

    assert (
        sum("outside [0, 1]" in record.getMessage() for record in caplog.records) == 4
    )


@pytest.mark.parametrize("raw", ["nan", "NaN", float("nan")])
def test_nan_falls_back_to_the_default(raw: object) -> None:
    # NaN 的比较恒为 False，直接使用会导致"永不写入"这种静默失效。
    assert probability_threshold(raw) == DEFAULT_JUDGEMENT_THRESHOLD


@pytest.mark.parametrize("raw", ["not-a-number", [], {}])
def test_unparseable_text_falls_back_to_the_default(raw: object) -> None:
    assert probability_threshold(raw) == DEFAULT_JUDGEMENT_THRESHOLD


def test_the_setting_name_reaches_the_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        probability_threshold("1.5", name="HARNESS_MODE_DECISION_THRESHOLD")

    assert any(
        "HARNESS_MODE_DECISION_THRESHOLD" in record.getMessage()
        for record in caplog.records
    )
