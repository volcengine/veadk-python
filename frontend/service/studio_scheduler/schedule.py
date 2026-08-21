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

"""Pure next-occurrence calculation without a resident scheduler process."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .models import Schedule

_SEARCH_LIMIT_MINUTES = 366 * 24 * 60 * 5


def next_scheduled_time(schedule: Schedule, after: datetime) -> datetime | None:
    """Return the first scheduled UTC minute strictly after ``after``."""
    if after.tzinfo is None or after.utcoffset() is None:
        raise ValueError("after must include a timezone")
    after = after.astimezone(timezone.utc).replace(second=0, microsecond=0)
    if schedule.kind == "once":
        return schedule.run_at if schedule.run_at and schedule.run_at > after else None

    zone = ZoneInfo(schedule.timezone)
    candidate = after + timedelta(minutes=1)
    if schedule.kind == "daily":
        return _search(candidate, zone, schedule, lambda local: True)
    if schedule.kind == "weekly":
        return _search(
            candidate,
            zone,
            schedule,
            lambda local: local.weekday() in schedule.weekdays,
        )

    minute, hour, month_day, month, week_day = _parse_cron(schedule.cron)

    def cron_matches(local: datetime) -> bool:
        cron_weekday = (local.weekday() + 1) % 7
        day_matches = local.day in month_day
        weekday_matches = cron_weekday in week_day
        if len(month_day) != 31 and len(week_day) != 7:
            calendar_day_matches = day_matches or weekday_matches
        else:
            calendar_day_matches = day_matches and weekday_matches
        return (
            local.minute in minute
            and local.hour in hour
            and local.month in month
            and calendar_day_matches
        )

    for _ in range(_SEARCH_LIMIT_MINUTES):
        if cron_matches(candidate.astimezone(zone)):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError("cron expression has no occurrence within five years")


def _search(
    candidate: datetime,
    zone: ZoneInfo,
    schedule: Schedule,
    day_matches: Callable[[datetime], bool],
) -> datetime:
    for _ in range(366 * 24 * 60 * 2):
        local = candidate.astimezone(zone)
        if (
            local.hour == schedule.hour
            and local.minute == schedule.minute
            and day_matches(local)
        ):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError("schedule has no occurrence within two years")


def _parse_cron(
    expression: str,
) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("cron expression must have five fields")
    minute = _parse_field(fields[0], 0, 59, "minute")
    hour = _parse_field(fields[1], 0, 23, "hour")
    month_day = _parse_field(fields[2], 1, 31, "day of month")
    month = _parse_field(fields[3], 1, 12, "month")
    week_day = _parse_field(fields[4], 0, 7, "day of week")
    if 7 in week_day:
        week_day.remove(7)
        week_day.add(0)
    return minute, hour, month_day, month, week_day


def _parse_field(field: str, minimum: int, maximum: int, name: str) -> set[int]:
    values: set[int] = set()
    for part in field.split(","):
        base, separator, step_text = part.partition("/")
        try:
            step = int(step_text) if separator else 1
        except ValueError as error:
            raise ValueError(f"cron {name} step is invalid") from error
        if step < 1:
            raise ValueError(f"cron {name} step must be positive")
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            start_text, end_text = base.split("-", 1)
            try:
                start, end = int(start_text), int(end_text)
            except ValueError as error:
                raise ValueError(f"cron {name} range is invalid") from error
        else:
            try:
                start = end = int(base)
            except ValueError as error:
                raise ValueError(f"cron {name} value is invalid") from error
        if start < minimum or end > maximum or start > end:
            raise ValueError(f"cron {name} value is outside {minimum}-{maximum}")
        values.update(range(start, end + 1, step))
    return values
