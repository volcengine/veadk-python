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

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from functools import cached_property
from typing import Any

from google.adk.events.event import Event
from google.adk.sessions import BaseSessionService, Session
from google.adk.sessions.base_session_service import ListSessionsResponse
from pydantic import Field
from typing_extensions import override

import veadk.config  # noqa E401
from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.configs.database_configs import ApiSessionConfig
from veadk.memory.short_term_memory_backends.base_backend import (
    BaseShortTermMemoryBackend,
)
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)


def _drop_none(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _drop_none(item) for key, item in value.items() if item is not None
        }
    if isinstance(value, list):
        return [_drop_none(item) for item in value]
    return value


def _load_json_if_needed(value: object) -> object:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _parse_timestamp(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            timestamp = value.replace("Z", "+00:00")
            return datetime.fromisoformat(timestamp).timestamp()
    raise ValueError(f"Invalid timestamp value: {value!r}")


def _format_timestamp(value: float) -> str:
    return (
        datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
    )


def _camel_get(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return default


def _summarize_request_body(body: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("AppName", "UserId", "SessionId", "AccountId"):
        if key in body:
            summary[key] = body[key]
    if "Config" in body:
        summary["Config"] = body["Config"]
    if "State" in body:
        summary["HasState"] = body["State"] is not None
    if "Event" in body:
        try:
            event = json.loads(body["Event"])
            summary["EventId"] = _camel_get(event, "id", "Id")
            summary["InvocationId"] = _camel_get(event, "invocation_id", "InvocationId")
        except (TypeError, json.JSONDecodeError):
            summary["HasEvent"] = True
    return summary


def _is_not_found_response(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False

    if str(payload.get("detail", "")).lower() == "session not found":
        return True

    metadata = payload.get("ResponseMetadata")
    if not isinstance(metadata, dict):
        return False

    error = metadata.get("Error")
    if not isinstance(error, dict):
        return False

    code = str(error.get("Code", "")).lower()
    message = str(error.get("Message", "")).lower()
    return code == "resourcenotfound.session" or message == "session not found"


def _normalize_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    actions = payload.get("actions") or payload.get("Actions")
    if not isinstance(actions, dict):
        return payload

    normalized_actions = dict(actions)
    for key in (
        "state_delta",
        "stateDelta",
        "artifact_delta",
        "artifactDelta",
        "requested_auth_configs",
        "requestedAuthConfigs",
        "requested_tool_confirmations",
        "requestedToolConfirmations",
    ):
        if key in normalized_actions and normalized_actions[key] is None:
            normalized_actions[key] = {}

    normalized = dict(payload)
    if "actions" in normalized:
        normalized["actions"] = normalized_actions
    if "Actions" in normalized:
        normalized["Actions"] = normalized_actions
    return normalized


def _summarize_response(action: str, response: object) -> dict[str, Any]:
    result = response.get("Result") if isinstance(response, dict) else response
    summary: dict[str, Any] = {
        "has_result": isinstance(response, dict) and "Result" in response,
        "result_type": type(result).__name__ if result is not None else None,
    }
    if _is_not_found_response(response):
        summary["not_found"] = True
        return summary

    if isinstance(result, list):
        summary["session_count"] = len(result)
    elif isinstance(result, dict):
        if _is_not_found_response(result):
            summary["not_found"] = True
            return summary

        session_ids = _camel_get(
            result,
            "SessionIds",
            "session_ids",
            "SessionIDList",
            "session_id_list",
        )
        if isinstance(session_ids, list):
            summary["session_count"] = len(session_ids)

        session_payload = _camel_get(result, "Session", "session", default=result)
        if isinstance(session_payload, dict):
            events = _camel_get(session_payload, "Events", "events")
            if isinstance(events, list):
                summary["event_count"] = len(events)
            session_id = _camel_get(session_payload, "SessionId", "sessionId", "id")
            if session_id:
                summary["SessionId"] = session_id
    elif action == "DeleteSession":
        summary["deleted"] = "Error" not in response
    return summary


class ApiSessionService(BaseSessionService):
    def __init__(self, config: ApiSessionConfig):
        self.config = config

    def _get_credential(self) -> tuple[str, str, dict[str, str]]:
        ak = os.getenv("VOLCENGINE_ACCESS_KEY")
        sk = os.getenv("VOLCENGINE_SECRET_KEY")
        header = {}
        if not (ak and sk):
            credential = get_credential_from_vefaas_iam()
            ak = credential.access_key_id
            sk = credential.secret_access_key
            header = {"X-Security-Token": credential.session_token}
        return ak, sk, header

    def _request_sync(self, action: str, body: dict[str, Any]) -> Any:
        ak, sk, header = self._get_credential()
        logger.info(
            f"Calling ApiSessionService action={action}, "
            f"service={self.config.service}, region={self.config.region}, "
            f"version={self.config.version}, body={_summarize_request_body(body)}"
        )
        response = ve_request(
            request_body=body,
            action=action,
            ak=ak,
            sk=sk,
            service=self.config.service,
            version=self.config.version,
            region=self.config.region,
            host="open.volcengineapi.com",
            header=header,
            scheme="https",
        )
        if not isinstance(response, (dict, list)):
            raise ValueError(f"ApiSessionService {action} error: {response}")
        logger.info(
            f"ApiSessionService action={action} returned "
            f"{_summarize_response(action, response)}"
        )
        return response

    async def _request(self, action: str, body: dict[str, Any]) -> Any:
        return await asyncio.to_thread(self._request_sync, action, body)

    def _body(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = {"AccountId": self.config.account_id or None, **payload}
        result = _drop_none(body)
        if not isinstance(result, dict):
            raise TypeError("ApiSessionService request body must be a dict")
        return result

    def _result(self, action: str, response: Any, *, allow_empty: bool = False) -> Any:
        if response is None:
            if allow_empty:
                return None
            raise ValueError(f"ApiSessionService {action} error: {response}")

        if isinstance(response, list):
            return response

        if not isinstance(response, dict):
            raise ValueError(f"ApiSessionService {action} error: {response}")

        if "Result" in response:
            return response["Result"]
        if _is_not_found_response(response) and allow_empty:
            return None
        error = response.get("Error")
        metadata = response.get("ResponseMetadata")
        if isinstance(metadata, dict):
            error = error or metadata.get("Error")
        code = response.get("Code") or response.get("code")
        if error or code:
            raise ValueError(f"ApiSessionService {action} error: {response}")
        return response

    @override
    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        session_id = session_id.strip() if session_id and session_id.strip() else None
        session_id = session_id or str(uuid.uuid4())
        body = self._body(
            {
                "AppName": app_name,
                "UserId": user_id,
                "SessionId": session_id,
                "State": state or None,
            }
        )
        response = await self._request("CreateSession", body)
        result = self._result("CreateSession", response, allow_empty=True)
        session = self._session_from_result(
            result,
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            state=state,
        )
        if session is None:
            return Session(
                app_name=app_name,
                user_id=user_id,
                id=session_id,
                state=state or {},
            )
        return session

    @override
    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Any | None = None,
    ) -> Session | None:
        session_config = None
        if config:
            session_config = _drop_none(
                {
                    "NumRecentEvents": getattr(config, "num_recent_events", None),
                    "AfterTimestamp": getattr(config, "after_timestamp", None),
                }
            )
        body = self._body(
            {
                "UserId": user_id,
                "SessionId": session_id,
                "Config": session_config,
            }
        )
        response = await self._request("GetSession", body)
        result = self._result("GetSession", response, allow_empty=True)
        return self._session_from_result(
            result, app_name=app_name, user_id=user_id, session_id=session_id
        )

    @override
    async def list_sessions(
        self, *, app_name: str, user_id: str | None = None
    ) -> ListSessionsResponse:
        body = self._body({"UserId": user_id})
        response = await self._request("ListSessionIds", body)
        result = self._result("ListSessionIds", response, allow_empty=True)
        return self._list_sessions_from_result(
            result, app_name=app_name, user_id=user_id
        )

    @override
    async def delete_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> None:
        body = self._body({"UserId": user_id, "SessionId": session_id})
        response = await self._request("DeleteSession", body)
        self._result("DeleteSession", response, allow_empty=True)

    @override
    async def append_event(self, session: Session, event: Event) -> Event:
        if event.partial:
            return event

        event = self._trim_temp_delta_state(event)
        body = self._body(
            {
                "AppName": session.app_name,
                "UserId": session.user_id,
                "SessionId": session.id,
                "Event": json.dumps(
                    self._event_to_remote_json(event), ensure_ascii=False
                ),
            }
        )
        response = await self._request("AppendEvent", body)
        self._result("AppendEvent", response, allow_empty=True)

        await super().append_event(session=session, event=event)
        session.last_update_time = event.timestamp
        return event

    def _event_to_remote_json(self, event: Event) -> dict[str, Any]:
        payload = event.model_dump(mode="json", exclude_none=True)
        remote = {
            "id": payload.pop("id", None),
            "invocation_id": payload.pop("invocation_id", None),
            "timestamp": _format_timestamp(float(payload.pop("timestamp", 0.0))),
            "content": payload.pop("content", None),
            "event_data": payload,
        }
        result = _drop_none(remote)
        if not isinstance(result, dict):
            raise TypeError("Remote event payload must be a dict")
        return result

    def _event_from_remote_json(self, payload: object) -> Event:
        payload = _load_json_if_needed(payload)
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid event payload: {payload!r}")
        payload = _normalize_event_payload(payload)

        event_data = payload.get("event_data") or payload.get("EventData")
        if isinstance(event_data, str):
            event_data = json.loads(event_data)
        if isinstance(event_data, dict):
            merged = {
                **event_data,
                "id": _camel_get(payload, "id", "Id"),
                "invocation_id": _camel_get(
                    payload, "invocation_id", "InvocationId", "invocationId"
                ),
                "timestamp": _parse_timestamp(
                    _camel_get(payload, "timestamp", "Timestamp")
                ),
                "content": _camel_get(payload, "content", "Content"),
            }
            merged = _drop_none(merged)
            if not isinstance(merged, dict):
                raise TypeError("Merged event payload must be a dict")
            merged = _normalize_event_payload(merged)
            return Event.model_validate(merged)

        if "timestamp" in payload or "Timestamp" in payload:
            payload = {
                **payload,
                "timestamp": _parse_timestamp(
                    _camel_get(payload, "timestamp", "Timestamp")
                ),
            }
        payload = _normalize_event_payload(payload)
        return Event.model_validate(payload)

    def _session_from_result(
        self,
        result: object,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        state: dict[str, Any] | None = None,
    ) -> Session | None:
        result = _load_json_if_needed(result)
        if result is None:
            return None
        if isinstance(result, list):
            if not result:
                return None
            if len(result) == 1:
                result = _load_json_if_needed(result[0])
        if not isinstance(result, dict):
            raise ValueError(f"Invalid session payload: {result!r}")

        payload = _camel_get(result, "Session", "session", default=result)
        payload = _load_json_if_needed(payload)
        if payload is None:
            return None
        if isinstance(payload, list):
            if not payload:
                return None
            if len(payload) == 1:
                payload = _load_json_if_needed(payload[0])
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid session payload: {payload!r}")

        raw_events = _camel_get(payload, "events", "Events", default=[])
        if raw_events is None:
            raw_events = []
        if not isinstance(raw_events, list):
            raise ValueError(f"Invalid session events payload: {raw_events!r}")

        events = [self._event_from_remote_json(event) for event in raw_events]
        session_state = _camel_get(payload, "state", "State", default=state or {})
        last_update_time = _parse_timestamp(
            _camel_get(
                payload,
                "last_update_time",
                "LastUpdateTime",
                "lastUpdateTime",
                "update_time",
                "UpdateTime",
                "updateTime",
                default=0.0,
            )
        )
        return Session(
            id=str(
                _camel_get(payload, "id", "SessionId", "sessionId", default=session_id)
            ),
            app_name=str(
                _camel_get(payload, "app_name", "AppName", "appName", default=app_name)
            ),
            user_id=str(
                _camel_get(payload, "user_id", "UserId", "userId", default=user_id)
            ),
            state=session_state or {},
            events=events,
            last_update_time=last_update_time,
        )

    def _list_sessions_from_result(
        self, result: object, *, app_name: str, user_id: str | None
    ) -> ListSessionsResponse:
        result = _load_json_if_needed(result)
        if result is None:
            return ListSessionsResponse()

        sessions_payload = result
        if isinstance(result, dict):
            sessions_payload = _camel_get(
                result,
                "Sessions",
                "sessions",
                "SessionIds",
                "session_ids",
                "SessionIDList",
                "session_id_list",
                default=[],
            )
        if not isinstance(sessions_payload, list):
            raise ValueError(f"Invalid list sessions payload: {result!r}")

        sessions = []
        for item in sessions_payload:
            if isinstance(item, (str, int)):
                sessions.append(
                    Session(
                        app_name=app_name,
                        user_id=user_id or "",
                        id=str(item),
                    )
                )
                continue
            session = self._session_from_result(
                item,
                app_name=app_name,
                user_id=user_id or "",
                session_id="",
            )
            if session:
                session.events = []
                sessions.append(session)
        return ListSessionsResponse(sessions=sessions)


class ApiSTMBackend(BaseShortTermMemoryBackend):
    api_session_config: ApiSessionConfig = Field(default_factory=ApiSessionConfig)

    @cached_property
    @override
    def session_service(self) -> BaseSessionService:
        return ApiSessionService(config=self.api_session_config)
