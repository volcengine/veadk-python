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

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server.evaluation_automation.models import AutomaticEvaluationStatus
from frontend.server.evaluation_automation.routes import mount_routes


def test_status_route_authorizes_and_filters_the_current_user() -> None:
    service = Mock()
    now = datetime.now(timezone.utc)
    service.list_statuses.return_value = [
        AutomaticEvaluationStatus(
            runtimeId="runtime",
            appName="agent",
            userId="user",
            sessionId="session",
            state="running",
            scheduledAt=now,
            dueAt=now,
            startedAt=now,
        )
    ]
    authorize = Mock()
    app = FastAPI()
    mount_routes(app, service, authorize)

    response = TestClient(app).get(
        "/web/evaluation/statuses",
        params={
            "runtimeId": "runtime",
            "region": "cn-beijing",
            "appName": "agent",
            "userId": "user",
        },
    )

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "runtimeId": "runtime",
            "appName": "agent",
            "userId": "user",
            "sessionId": "session",
            "state": "running",
            "scheduledAt": now.isoformat().replace("+00:00", "Z"),
            "dueAt": now.isoformat().replace("+00:00", "Z"),
            "startedAt": now.isoformat().replace("+00:00", "Z"),
        }
    ]
    authorize.assert_called_once()
    service.list_statuses.assert_called_once_with(
        runtime_id="runtime",
        app_name="agent",
        user_id="user",
    )
