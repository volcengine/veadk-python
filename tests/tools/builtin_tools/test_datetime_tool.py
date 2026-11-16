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

"""Hermetic tests for the ``datetime`` built-in tool."""

import inspect
from datetime import datetime as _datetime
from datetime import timedelta as _timedelta
from datetime import timezone as _timezone

import pytest

from veadk.tools.builtin_tools import datetime_tool as datetime_module
from veadk.tools.builtin_tools.datetime_tool import datetime as datetime_tool

_WEEKDAYS = {
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}


def test_signature():
    params = inspect.signature(datetime_tool).parameters
    assert list(params) == [
        "action",
        "value",
        "value2",
        "timezone",
        "target_timezone",
        "format",
        "amount",
        "unit",
    ]


def test_defaults():
    params = inspect.signature(datetime_tool).parameters
    assert params["action"].default is inspect.Parameter.empty
    for name in (
        "value",
        "value2",
        "timezone",
        "target_timezone",
        "format",
        "amount",
        "unit",
    ):
        assert params[name].default is None


# --------------------------------------------------------------------- now --
def test_now_defaults_to_utc():
    result = datetime_tool("now")
    assert result["timezone"] == "UTC"
    moment = _datetime.fromisoformat(result["iso"])
    assert moment.utcoffset() == _timedelta(0)
    assert result["weekday"] in _WEEKDAYS
    assert isinstance(result["timestamp"], float)


def test_now_in_timezone():
    result = datetime_tool("now", timezone="Asia/Shanghai")
    assert result["timezone"] == "Asia/Shanghai"
    assert result["iso"].endswith("+08:00")


@pytest.mark.parametrize("timezone", ["Not/AZone", "", 123])
def test_now_rejects_bad_timezone(timezone):
    assert "error" in datetime_tool("now", timezone=timezone)


# ------------------------------------------------------------------- parse --
def test_parse_iso_with_offset():
    result = datetime_tool("parse", value="2024-01-02T03:04:05+08:00")
    assert result["year"] == 2024
    assert result["month"] == 1
    assert result["day"] == 2
    assert result["hour"] == 3
    assert result["minute"] == 4
    assert result["second"] == 5
    assert result["weekday"] == "tuesday"
    assert result["timezone"] == "+08:00"
    expected = _datetime(
        2024, 1, 2, 3, 4, 5, tzinfo=_timezone(_timedelta(hours=8))
    ).timestamp()
    assert result["timestamp"] == expected


def test_parse_z_suffix():
    result = datetime_tool("parse", value="2024-01-02T03:04:05Z")
    assert result["timezone"] == "UTC"
    assert result["iso"] == "2024-01-02T03:04:05+00:00"


def test_parse_date_only_uses_utc():
    result = datetime_tool("parse", value="2024-01-02")
    assert result["iso"] == "2024-01-02T00:00:00+00:00"
    assert result["hour"] == 0


def test_parse_naive_uses_timezone():
    result = datetime_tool(
        "parse", value="2024-01-02 03:04:05", timezone="Asia/Shanghai"
    )
    assert result["timezone"] == "Asia/Shanghai"
    assert result["iso"] == "2024-01-02T03:04:05+08:00"


def test_parse_slash_date():
    result = datetime_tool("parse", value="2024/01/02")
    assert result["iso"] == "2024-01-02T00:00:00+00:00"


def test_parse_slash_datetime():
    result = datetime_tool("parse", value="2024/01/02 03:04:05")
    assert result["iso"] == "2024-01-02T03:04:05+00:00"


@pytest.mark.parametrize("value", [None, "", "not a date", 123])
def test_parse_rejects_bad_value(value):
    assert "error" in datetime_tool("parse", value=value)


def test_parse_naive_with_bad_timezone():
    result = datetime_tool("parse", value="2024-01-02", timezone="Not/AZone")
    assert "error" in result


# ------------------------------------------------------------------ format --
def test_format_default():
    result = datetime_tool("format", value="2024-01-02T03:04:05+00:00")
    assert result["formatted"] == "2024-01-02 03:04:05"
    assert result["iso"] == "2024-01-02T03:04:05+00:00"


def test_format_custom():
    result = datetime_tool("format", value="2024-01-02", format="%Y/%m/%d")
    assert result["formatted"] == "2024/01/02"


def test_format_rejects_non_string_format():
    result = datetime_tool("format", value="2024-01-02", format=123)
    assert "error" in result


def test_format_requires_value():
    assert "error" in datetime_tool("format")


def test_format_string_failure_is_reported(monkeypatch):
    class _BadMoment:
        def strftime(self, pattern):
            raise ValueError("bad format")

    monkeypatch.setattr(datetime_module, "_parse", lambda *args: _BadMoment())
    result = datetime_tool("format", value="2024-01-02", format="%Y")
    assert "error" in result


# ----------------------------------------------------------------- convert --
def test_convert_from_utc_to_target():
    result = datetime_tool(
        "convert",
        value="2024-01-01 12:00:00",
        timezone="UTC",
        target_timezone="Asia/Shanghai",
    )
    assert result["iso"] == "2024-01-01T20:00:00+08:00"
    assert result["timezone"] == "Asia/Shanghai"
    expected = _datetime(2024, 1, 1, 12, 0, 0, tzinfo=_timezone.utc).timestamp()
    assert result["timestamp"] == expected


def test_convert_aware_value_uses_its_offset():
    result = datetime_tool(
        "convert",
        value="2024-01-01T12:00:00+08:00",
        target_timezone="UTC",
    )
    assert result["iso"] == "2024-01-01T04:00:00+00:00"
    assert result["timezone"] == "UTC"


def test_convert_requires_target_timezone():
    result = datetime_tool("convert", value="2024-01-01")
    assert "error" in result


def test_convert_rejects_bad_target_timezone():
    result = datetime_tool("convert", value="2024-01-01", target_timezone="Not/AZone")
    assert "error" in result


# -------------------------------------------------------------------- diff --
def test_diff_positive():
    result = datetime_tool(
        "diff",
        value="2024-01-01 00:00:00",
        value2="2024-01-03 03:04:05",
    )
    assert result["seconds"] == 183845.0
    assert result["days"] == pytest.approx(183845 / 86400)
    assert result["human"] == "2 days, 3:04:05"


def test_diff_zero():
    result = datetime_tool(
        "diff", value="2024-01-01T00:00:00Z", value2="2024-01-01T00:00:00Z"
    )
    assert result["seconds"] == 0
    assert result["human"] == "0:00:00"


def test_diff_negative_seconds():
    result = datetime_tool(
        "diff",
        value="2024-01-01 00:00:05",
        value2="2024-01-01 00:00:00",
    )
    assert result["seconds"] == -5.0
    assert result["human"] == "-0:00:05"


def test_diff_negative_day_is_singular():
    result = datetime_tool(
        "diff",
        value="2024-01-02 00:00:00",
        value2="2024-01-01 00:00:00",
    )
    assert result["human"] == "-1 day, 0:00:00"


def test_diff_requires_value2():
    assert "error" in datetime_tool("diff", value="2024-01-01")


def test_diff_rejects_bad_value():
    assert "error" in datetime_tool("diff", value="nope", value2="2024-01-01")


# --------------------------------------------------------------------- add --
@pytest.mark.parametrize(
    ("amount", "unit", "expected"),
    [
        (30, "seconds", "2024-01-01T00:00:30+00:00"),
        (90, "minutes", "2024-01-01T01:30:00+00:00"),
        (2, "hours", "2024-01-01T02:00:00+00:00"),
        (1, "days", "2024-01-02T00:00:00+00:00"),
        (1, "weeks", "2024-01-08T00:00:00+00:00"),
        (1.5, "hours", "2024-01-01T01:30:00+00:00"),
        (1, "DAYS", "2024-01-02T00:00:00+00:00"),
    ],
)
def test_add_units(amount, unit, expected):
    result = datetime_tool(
        "add", value="2024-01-01T00:00:00Z", amount=amount, unit=unit
    )
    assert result["iso"] == expected
    assert "error" not in result


def test_add_requires_amount():
    assert "error" in datetime_tool("add", value="2024-01-01", unit="days")


@pytest.mark.parametrize("amount", [True, "1", None])
def test_add_rejects_bad_amount(amount):
    result = datetime_tool("add", value="2024-01-01", amount=amount, unit="days")
    assert "error" in result


@pytest.mark.parametrize("amount", [float("nan"), float("inf")])
def test_add_rejects_non_finite_amount(amount):
    result = datetime_tool("add", value="2024-01-01", amount=amount, unit="days")
    assert "error" in result


@pytest.mark.parametrize("unit", [None, "months", 1, ""])
def test_add_rejects_bad_unit(unit):
    result = datetime_tool("add", value="2024-01-01", amount=1, unit=unit)
    assert "error" in result


def test_add_rejects_bad_value():
    result = datetime_tool("add", value="nope", amount=1, unit="days")
    assert "error" in result


def test_add_overflow_returns_error():
    result = datetime_tool("add", value="2024-01-01", amount=1e30, unit="days")
    assert "error" in result


# ------------------------------------------------------------------- other --
@pytest.mark.parametrize("action", ["unknown", "", None, 1])
def test_unknown_action(action):
    result = datetime_tool(action)
    assert "error" in result


def test_unexpected_internal_error_is_reported(monkeypatch):
    def explode(timezone):
        raise RuntimeError("boom")

    monkeypatch.setattr(datetime_module, "_action_now", explode)
    result = datetime_tool("now")
    assert "error" in result
    assert "RuntimeError" in result["error"]
