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

"""A timezone-aware date/time tool for model use.

Supports producing the current time, parsing common date/time strings,
formatting, converting between timezones, computing differences, and adding
durations. Uses ``zoneinfo`` so no credentials or external services are
required.
"""

import math
from datetime import datetime as _datetime
from datetime import timedelta as _timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_DEFAULT_TIMEZONE = "UTC"
_DEFAULT_FORMAT = "%Y-%m-%d %H:%M:%S"
_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
_PARSE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d",
    "%Y/%m/%d %H:%M:%S",
)
_UNITS = ("seconds", "minutes", "hours", "days", "weeks")
_ACTIONS = ("now", "parse", "format", "convert", "diff", "add")


class _ToolError(Exception):
    """Internal error surfaced to the model as ``{"error": ...}``."""


def _get_zone(name: str | None) -> ZoneInfo:
    if name is None:
        return ZoneInfo(_DEFAULT_TIMEZONE)
    if not isinstance(name, str) or not name.strip():
        raise _ToolError("timezone must be a non-empty string")
    try:
        return ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise _ToolError(f"unknown timezone: {name}") from exc


def _timezone_name(moment: _datetime) -> str:
    """Return a stable label: zone key when known, else the UTC offset."""
    key = getattr(moment.tzinfo, "key", None)
    if key:
        return key
    offset = moment.utcoffset()
    if offset is None or offset == _timedelta(0):
        return _DEFAULT_TIMEZONE
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    hours, remainder = divmod(abs(total), 3600)
    minutes = remainder // 60
    return f"{sign}{hours:02d}:{minutes:02d}"


def _parse(value: str | None, timezone: str | None) -> _datetime:
    if not isinstance(value, str) or not value.strip():
        raise _ToolError("value must be a non-empty string")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed: _datetime | None = None
    try:
        parsed = _datetime.fromisoformat(text)
    except ValueError:
        for fmt in _PARSE_FORMATS:
            try:
                parsed = _datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        raise _ToolError(f"invalid datetime: {value}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_get_zone(timezone))
    return parsed


def _moment_fields(moment: _datetime) -> dict:
    return {
        "iso": moment.isoformat(),
        "timestamp": moment.timestamp(),
        "timezone": _timezone_name(moment),
        "weekday": _WEEKDAYS[moment.weekday()],
    }


def _human_delta(seconds: float) -> str:
    sign = "-" if seconds < 0 else ""
    remaining = int(abs(seconds))
    days, remaining = divmod(remaining, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, secs = divmod(remaining, 60)
    clock = f"{hours}:{minutes:02d}:{secs:02d}"
    if days:
        label = "day" if days == 1 else "days"
        return f"{sign}{days} {label}, {clock}"
    return f"{sign}{clock}"


def _action_now(timezone: str | None) -> dict:
    return _moment_fields(_datetime.now(_get_zone(timezone)))


def _action_parse(value: str | None, timezone: str | None) -> dict:
    moment = _parse(value, timezone)
    return {
        "iso": moment.isoformat(),
        "timestamp": moment.timestamp(),
        "timezone": _timezone_name(moment),
        "year": moment.year,
        "month": moment.month,
        "day": moment.day,
        "hour": moment.hour,
        "minute": moment.minute,
        "second": moment.second,
        "weekday": _WEEKDAYS[moment.weekday()],
    }


def _action_format(value: str | None, timezone: str | None, fmt: str | None) -> dict:
    if fmt is not None and not isinstance(fmt, str):
        raise _ToolError("format must be a string")
    moment = _parse(value, timezone)
    pattern = fmt or _DEFAULT_FORMAT
    try:
        formatted = moment.strftime(pattern)
    except (TypeError, ValueError) as exc:
        raise _ToolError("invalid format string") from exc
    return {"formatted": formatted, "iso": moment.isoformat()}


def _action_convert(
    value: str | None, timezone: str | None, target_timezone: str | None
) -> dict:
    if target_timezone is None:
        raise _ToolError("target_timezone is required for convert")
    moment = _parse(value, timezone).astimezone(_get_zone(target_timezone))
    return {
        "iso": moment.isoformat(),
        "timestamp": moment.timestamp(),
        "timezone": _timezone_name(moment),
    }


def _action_diff(value: str | None, value2: str | None, timezone: str | None) -> dict:
    start = _parse(value, timezone)
    end = _parse(value2, timezone)
    delta = end - start
    seconds = delta.total_seconds()
    return {
        "seconds": seconds,
        "days": seconds / 86400,
        "human": _human_delta(seconds),
    }


def _action_add(
    value: str | None,
    timezone: str | None,
    amount: float | None,
    unit: str | None,
) -> dict:
    if amount is None:
        raise _ToolError("amount is required for add")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise _ToolError("amount must be a number")
    if not math.isfinite(amount):
        raise _ToolError("amount must be finite")
    if not isinstance(unit, str) or unit.strip().lower() not in _UNITS:
        raise _ToolError("unit must be one of: " + ", ".join(_UNITS))
    moment = _parse(value, timezone) + _timedelta(**{unit.strip().lower(): amount})
    return {"iso": moment.isoformat(), "timestamp": moment.timestamp()}


def datetime(
    action: str,
    value: str | None = None,
    value2: str | None = None,
    timezone: str | None = None,
    target_timezone: str | None = None,
    format: str | None = None,
    amount: float | None = None,
    unit: str | None = None,
) -> dict:
    """Work with dates and times, including timezone conversions.

    Use this tool for the current time, parsing or formatting a timestamp,
    converting a timestamp between timezones, computing the difference between
    two timestamps, or adding a duration. Timestamps without an explicit offset
    use ``timezone`` (default UTC).

    Args:
        action: One of ``now``, ``parse``, ``format``, ``convert``, ``diff``,
            ``add``.
        value: The primary date/time string for ``parse``, ``format``,
            ``convert``, ``diff``, and ``add``.
        value2: The second date/time string for ``diff``.
        timezone: IANA timezone name (for example ``Asia/Shanghai``) used when
            ``value`` has no offset. Defaults to UTC.
        target_timezone: IANA timezone name to convert to (``convert`` only).
        format: ``strftime`` format string (``format`` only).
        amount: Numeric amount to add (``add`` only).
        unit: One of ``seconds``, ``minutes``, ``hours``, ``days``, ``weeks``
            (``add`` only).

    Returns:
        A dict with the requested fields. On invalid input, a dict with an
        ``error`` key.
    """
    try:
        if action == "now":
            return _action_now(timezone)
        if action == "parse":
            return _action_parse(value, timezone)
        if action == "format":
            return _action_format(value, timezone, format)
        if action == "convert":
            return _action_convert(value, timezone, target_timezone)
        if action == "diff":
            return _action_diff(value, value2, timezone)
        if action == "add":
            return _action_add(value, timezone, amount, unit)
        raise _ToolError(
            f"unsupported action: {action!r}; expected one of " + ", ".join(_ACTIONS)
        )
    except _ToolError as exc:
        return {"error": str(exc)}
    except (OverflowError, ValueError, TypeError, OSError) as exc:
        return {"error": str(exc) or type(exc).__name__}
    except Exception as exc:  # noqa: BLE001 - tool results must not raise
        return {"error": f"invalid datetime input ({type(exc).__name__})"}
