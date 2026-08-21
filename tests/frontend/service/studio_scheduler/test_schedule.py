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

from datetime import datetime, timezone

from frontend.service.studio_scheduler.models import CronJob, Schedule
from frontend.service.studio_scheduler.schedule import next_scheduled_time


def test_cron_schedule_uses_the_declared_timezone() -> None:
    schedule = Schedule(
        kind="cron",
        timezone="Asia/Shanghai",
        cron="30 9 * * 1-5",
    )

    result = next_scheduled_time(
        schedule,
        datetime(2026, 8, 21, 1, 30, tzinfo=timezone.utc),
    )

    assert result == datetime(2026, 8, 24, 1, 30, tzinfo=timezone.utc)


def test_daily_and_weekly_schedules_compute_the_next_utc_minute() -> None:
    daily = Schedule(kind="daily", timezone="Asia/Shanghai", hour=9, minute=0)
    weekly = Schedule(
        kind="weekly",
        timezone="Asia/Shanghai",
        hour=9,
        minute=0,
        weekdays=(0, 4),
    )
    after = datetime(2026, 8, 21, 1, 0, tzinfo=timezone.utc)  # Friday 09:00 CST

    assert next_scheduled_time(daily, after) == datetime(
        2026, 8, 22, 1, 0, tzinfo=timezone.utc
    )
    assert next_scheduled_time(weekly, after) == datetime(
        2026, 8, 24, 1, 0, tzinfo=timezone.utc
    )


def test_once_schedule_has_no_successor() -> None:
    schedule = Schedule(
        kind="once",
        timezone="UTC",
        run_at=datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc),
    )

    assert schedule.run_at is not None
    assert next_scheduled_time(schedule, schedule.run_at) is None


def test_job_parser_accepts_bff_owner_and_discriminated_schedule_shape() -> None:
    job = CronJob.from_dict(
        {
            "jobId": "job-1",
            "ownerId": "owner-1",
            "revision": 2,
            "enabled": True,
            "runtimeId": "runtime-1",
            "agentName": "agent",
            "region": "cn-beijing",
            "prompt": "hello",
            "schedule": {
                "type": "cron",
                "timezone": "Asia/Shanghai",
                "expression": "0 9 * * *",
            },
        },
        default_provider="volcengine",
    )

    assert job.user_id == "owner-1"
    assert job.runtime.runtime_id == "runtime-1"
    assert job.schedule.cron == "0 9 * * *"
