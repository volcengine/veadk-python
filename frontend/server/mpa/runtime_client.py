"""Typed Studio-to-mpa-agent Profile transport."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from veadk.integrations.mpa.control_plane_client import (
    MpaExecutionConfigChange,
    MpaProfile,
    MpaSessionExecutionConfig,
)


class MpaProfileApplyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    source_profile_id: str = Field(alias="sourceProfileId", min_length=1)
    source_profile_digest: str = Field(alias="sourceProfileDigest")
    profile: MpaProfile

    @classmethod
    def from_profile(
        cls, *, source_profile_id: str, profile: MpaProfile
    ) -> "MpaProfileApplyRequest":
        canonical = json.dumps(
            profile.model_dump(by_alias=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(
            sourceProfileId=source_profile_id,
            sourceProfileDigest=f"sha256:{hashlib.sha256(canonical).hexdigest()}",
            profile=profile,
        )


class MpaProfileResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    operation_id: str = Field(alias="operationId")
    status: str
    etag: str = ""


class MpaRuntimeSessionSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str = ""
    session_id: str = Field(default="", alias="sessionId")
    app_name: str = Field(default="", alias="appName")
    user_id: str = Field(default="", alias="userId")
    status: str = ""
    updated_at: str = Field(default="", alias="updatedAt")
    mpa_instance_id: str = Field(default="", alias="mpaInstanceId")
    profile_revision: int | None = Field(default=None, alias="profileRevision")
    admin_debug: bool = Field(default=False, alias="adminDebug")

    @property
    def stable_id(self) -> str:
        return self.session_id or self.id


class MpaRuntimeError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        status_code: int,
        request_id: str = "",
        current_state: dict[str, Any] | None = None,
    ) -> None:
        super().__init__("MPA Runtime request failed")
        self.code = code
        self.status_code = status_code
        self.request_id = request_id
        self.current_state = current_state


class MpaRuntimeClient:
    def __init__(self, *, transport: httpx.AsyncClient | None = None) -> None:
        self._transport = transport

    async def apply_profile(
        self,
        *,
        endpoint: str,
        mpa_instance_id: str,
        bearer_token: str,
        idempotency_key: str,
        profile: MpaProfileApplyRequest,
        create: bool = False,
        runtime_revision: str = "",
    ) -> MpaProfileResult:
        if create and runtime_revision:
            raise ValueError("create cannot carry a runtime revision")
        if not create and not runtime_revision:
            raise ValueError("update requires a runtime revision")
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Idempotency-Key": idempotency_key,
            "If-None-Match" if create else "If-Match": "*"
            if create
            else runtime_revision,
        }
        response = await self._request(
            "PUT",
            f"{endpoint.rstrip('/')}/api/v1/agents/{mpa_instance_id}/profile",
            headers=headers,
            json=profile.model_dump(by_alias=True),
        )
        return self._result(response)

    async def profile_status(
        self, *, endpoint: str, mpa_instance_id: str, bearer_token: str
    ) -> MpaProfileResult:
        response = await self._request(
            "GET",
            f"{endpoint.rstrip('/')}/api/v1/agents/{mpa_instance_id}/profile-status",
            headers={"Authorization": f"Bearer {bearer_token}"},
        )
        return self._result(response)

    async def execution_smoke(
        self,
        *,
        endpoint: str,
        mpa_instance_id: str,
        bearer_token: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        del mpa_instance_id
        response = await self._request(
            "POST",
            f"{endpoint.rstrip('/')}/api/v1/readiness/execution-smoke",
            headers={
                "Authorization": f"Bearer {bearer_token}",
                "Idempotency-Key": idempotency_key,
            },
            json={},
        )
        payload = response.json()
        if not isinstance(payload, dict):
            raise MpaRuntimeError("runtime_invalid_response", status_code=502)
        return payload

    async def session_execution_config(
        self,
        *,
        endpoint: str,
        session_id: str,
        bearer_token: str,
    ) -> MpaSessionExecutionConfig:
        response = await self._request(
            "GET",
            f"{endpoint.rstrip('/')}/api/v1/sessions/{session_id}/execution-config",
            headers={"Authorization": f"Bearer {bearer_token}"},
        )
        return self._execution_config_result(response)

    async def list_sessions(
        self,
        *,
        endpoint: str,
        bearer_token: str,
        include_a2a: bool = True,
    ) -> list[MpaRuntimeSessionSummary]:
        response = await self._request(
            "GET",
            f"{endpoint.rstrip('/')}/api/v1/sessions",
            headers={"Authorization": f"Bearer {bearer_token}"},
            params={"include_a2a": "true" if include_a2a else "false"},
        )
        return self._session_list_result(response)

    async def delete_session(
        self,
        *,
        endpoint: str,
        session_id: str,
        bearer_token: str,
    ) -> None:
        await self._request(
            "DELETE",
            f"{endpoint.rstrip('/')}/api/v1/sessions/{session_id}",
            headers={"Authorization": f"Bearer {bearer_token}"},
        )

    async def patch_session_execution_config(
        self,
        *,
        endpoint: str,
        session_id: str,
        bearer_token: str,
        if_match: str,
        changes: list[MpaExecutionConfigChange],
    ) -> MpaSessionExecutionConfig:
        response = await self._request(
            "PATCH",
            f"{endpoint.rstrip('/')}/api/v1/sessions/{session_id}/execution-config",
            headers={
                "Authorization": f"Bearer {bearer_token}",
                "If-Match": if_match,
            },
            json={"changes": [change.model_dump(mode="json") for change in changes]},
        )
        return self._execution_config_result(response)

    async def upgrade_session_profile(
        self,
        *,
        endpoint: str,
        session_id: str,
        bearer_token: str,
        if_match: str,
        idempotency_key: str,
        target_profile_revision: int,
    ) -> MpaSessionExecutionConfig:
        response = await self._request(
            "POST",
            f"{endpoint.rstrip('/')}/api/v1/sessions/{session_id}/profile-upgrade",
            headers={
                "Authorization": f"Bearer {bearer_token}",
                "If-Match": if_match,
                "Idempotency-Key": idempotency_key,
            },
            json={"targetProfileRevision": int(target_profile_revision)},
        )
        return self._execution_config_result(response)

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            if self._transport is not None:
                response = await self._transport.request(method, url, **kwargs)
            else:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.request(method, url, **kwargs)
        except httpx.HTTPError as error:
            raise MpaRuntimeError("runtime_unavailable", status_code=503) from error
        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            error = payload.get("error") if isinstance(payload, dict) else {}
            detail = payload.get("detail") if isinstance(payload, dict) else {}
            code = error.get("code") if isinstance(error, dict) else None
            if code is None and isinstance(detail, dict):
                code = detail.get("code")
            current_state = None
            if isinstance(error, dict) and isinstance(error.get("currentState"), dict):
                current_state = dict(error["currentState"])
            elif isinstance(detail, dict) and isinstance(
                detail.get("currentState"), dict
            ):
                current_state = dict(detail["currentState"])
            raise MpaRuntimeError(
                str(code or "runtime_request_failed"),
                status_code=response.status_code,
                request_id=response.headers.get("X-Request-Id", ""),
                current_state=current_state,
            )
        return response

    @staticmethod
    def _result(response: httpx.Response) -> MpaProfileResult:
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError
            payload = dict(payload)
            payload["etag"] = response.headers.get(
                "ETag", str(payload.get("etag") or "")
            )
            return MpaProfileResult(**payload)
        except (ValueError, TypeError) as error:
            raise MpaRuntimeError(
                "runtime_invalid_response", status_code=502
            ) from error

    @staticmethod
    def _execution_config_result(response: httpx.Response) -> MpaSessionExecutionConfig:
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError
            payload = dict(payload)
            payload["etag"] = response.headers.get(
                "ETag", str(payload.get("etag") or "")
            )
            return MpaSessionExecutionConfig(**payload)
        except (ValueError, TypeError) as error:
            raise MpaRuntimeError(
                "runtime_invalid_response", status_code=502
            ) from error

    @staticmethod
    def _session_list_result(
        response: httpx.Response,
    ) -> list[MpaRuntimeSessionSummary]:
        try:
            payload = response.json()
            if isinstance(payload, list):
                items = payload
            elif isinstance(payload, dict):
                raw_items = (
                    payload.get("sessions")
                    or payload.get("items")
                    or payload.get("data")
                    or []
                )
                if not isinstance(raw_items, list):
                    raise ValueError
                items = raw_items
            else:
                raise ValueError
            return [
                MpaRuntimeSessionSummary(**item)
                for item in items
                if isinstance(item, dict)
            ]
        except (ValueError, TypeError) as error:
            raise MpaRuntimeError(
                "runtime_invalid_response", status_code=502
            ) from error
