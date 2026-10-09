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

"""Typed Python client for the AgentKit Studio MPA control plane."""

from __future__ import annotations

import re
from typing import Any, Literal, TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

_SECRET_FIELD_NAMES = {
    "accesstoken",
    "apikey",
    "authorization",
    "bearertoken",
    "clientsecret",
    "cookie",
    "password",
    "refreshtoken",
    "secret",
    "secretkey",
}
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_SAFE_ERROR_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_Model = TypeVar("_Model", bound=BaseModel)


def _contains_secret_field(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).replace("_", "").replace("-", "").casefold()
            if normalized in _SECRET_FIELD_NAMES or normalized.endswith("password"):
                return True
            if _contains_secret_field(item):
                return True
    if isinstance(value, list):
        return any(_contains_secret_field(item) for item in value)
    return False


class MpaProfile(BaseModel):
    """Executable Profile references accepted by the Studio BFF."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    system: str = Field(min_length=1)
    model: dict[str, Any]
    tools: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[dict[str, Any]] = Field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = Field(default_factory=list, alias="mcpServers")
    multiagent: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_embedded_secrets(self) -> "MpaProfile":
        if _contains_secret_field(self.model_dump(by_alias=True)):
            raise ValueError("secret values must be represented by references")
        return self


class MpaAgentOperationRequest(BaseModel):
    """Input shared by create, update, and operation retry."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    operation_kind: str | None = Field(default=None, alias="operationKind")
    runtime_id: str = Field(alias="runtimeId", min_length=1)
    region: str = "cn-beijing"
    mpa_instance_id: str = Field(default="", alias="mpaInstanceId")
    source_profile_id: str = Field(alias="sourceProfileId", min_length=1)
    profile: MpaProfile
    target_key: str = Field(default="", alias="targetKey")
    runtime_revision: str = Field(default="", alias="runtimeRevision")
    create: bool | None = None


class MpaAgentOperation(BaseModel):
    """Safe lifecycle-operation response returned by Studio."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    operation_id: str = Field(alias="operationId")
    operation_kind: str = Field(alias="operationKind")
    owner_id: str = Field(default="", alias="ownerId")
    target_key: str = Field(default="", alias="targetKey")
    stage: str
    status: str
    mpa_instance_id: str = Field(default="", alias="mpaInstanceId")
    runtime_id: str = Field(default="", alias="runtimeId")
    runtime_region: str = Field(default="", alias="runtimeRegion")
    runtime_revision: str = Field(default="", alias="runtimeRevision")
    profile_revision: int | None = Field(default=None, alias="profileRevision")
    safe_error_code: str = Field(default="", alias="safeErrorCode")
    retry_count: int = Field(default=0, alias="retryCount")


class MpaAgentCapabilities(BaseModel):
    """Server-negotiated actions for the current MPA binding."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    can_read: bool = Field(default=False, alias="canRead")
    can_write: bool = Field(default=False, alias="canWrite")
    can_debug: bool = Field(default=False, alias="canDebug")


class MpaAgentView(BaseModel):
    """Studio-owned view of one MPA Agent and its Runtime binding."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    mpa_instance_id: str = Field(alias="mpaInstanceId")
    binding_status: str = Field(alias="bindingStatus")
    runtime: dict[str, Any] | None = None
    profile: dict[str, Any] | None = None
    capabilities: MpaAgentCapabilities = Field(default_factory=MpaAgentCapabilities)
    etag: str = ""


class MpaProfileStatus(BaseModel):
    """Current immutable Profile revision reported through Studio."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    operation_id: str = Field(default="", alias="operationId")
    status: str
    profile_revision: int = Field(alias="profileRevision")
    runtime_revision: str = Field(default="", alias="runtimeRevision")
    etag: str = ""


class MpaExecutionConfigChange(BaseModel):
    """One explicit Session execution-config category mutation."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    category: str = Field(min_length=1)
    mode: Literal["replace", "clear", "inherit"]
    value: Any | None = None


class MpaSessionExecutionConfig(BaseModel):
    """Versioned effective execution configuration for one Runtime Session."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    app_name: str = Field(alias="appName")
    session_id: str = Field(alias="sessionId")
    revision: int
    etag: str = ""
    mpa_instance_id: str = Field(alias="mpaInstanceId")
    profile_revision: int = Field(alias="profileRevision")
    profile_default_revision: int = Field(alias="profileDefaultRevision")
    overrides: dict[str, Any] = Field(default_factory=dict)
    effective_refs: dict[str, Any] = Field(default_factory=dict, alias="effectiveRefs")
    invalid_refs: list[dict[str, Any]] = Field(
        default_factory=list, alias="invalidRefs"
    )
    updated_by: str = Field(default="", alias="updatedBy")
    created_at: str = Field(default="", alias="createdAt")
    updated_at: str = Field(default="", alias="updatedAt")


class MpaAgentDeletePreview(BaseModel):
    """Authorized impact preview returned before MPA Runtime deletion."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    mpa_instance_id: str = Field(alias="mpaInstanceId")
    binding_status: str = Field(alias="bindingStatus")
    can_delete: bool = Field(alias="canDelete")
    blockers: list[str] = Field(default_factory=list)
    session_counts: dict[str, int] = Field(default_factory=dict, alias="sessionCounts")
    active_sessions: list[dict[str, Any]] = Field(
        default_factory=list, alias="activeSessions"
    )
    cleanup_plan: list[dict[str, Any]] = Field(
        default_factory=list, alias="cleanupPlan"
    )


class MpaControlPlaneError(RuntimeError):
    """Safe, structured failure raised by all control-plane requests."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int,
        request_id: str = "",
        retryable: bool = False,
        current_state: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"MPA control-plane request failed: {code}")
        self.code = code
        self.status_code = status_code
        self.request_id = request_id
        self.retryable = retryable
        self.current_state = current_state


class MpaControlPlaneClient:
    """Access MPA control-plane APIs through AgentKit Studio's BFF."""

    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str = "",
        transport: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not base_url.strip():
            raise ValueError("Studio base URL is required.")
        self._base_url = base_url.rstrip("/")
        self._bearer_token = self._bearer_value(bearer_token)
        self._transport = transport or httpx.AsyncClient(timeout=timeout)
        self._owns_transport = transport is None

    async def __aenter__(self) -> "MpaControlPlaneClient":
        return self

    async def __aexit__(self, *_exc_info: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the internally owned HTTP connection pool."""
        if self._owns_transport:
            await self._transport.aclose()

    async def get_agent_view(
        self,
        mpa_instance_id: str,
        *,
        runtime_id: str = "",
        region: str = "all",
    ) -> MpaAgentView:
        response = await self._request(
            "GET",
            f"/web/mpa/agents/{quote(mpa_instance_id, safe='')}/view",
            params={"runtimeId": runtime_id, "region": region},
        )
        return self._model_with_etag(response, MpaAgentView)

    async def create_agent(
        self, request: MpaAgentOperationRequest, *, idempotency_key: str
    ) -> MpaAgentOperation:
        if request.operation_kind != "create":
            raise ValueError("create_agent requires operationKind=create")
        if not idempotency_key.strip():
            raise ValueError("Idempotency key is required.")
        response = await self._request(
            "POST",
            "/web/mpa/agents",
            headers={"Idempotency-Key": idempotency_key},
            json=request.model_dump(mode="json", by_alias=True),
        )
        return self._model(response, MpaAgentOperation)

    async def update_agent(
        self,
        mpa_instance_id: str,
        request: MpaAgentOperationRequest,
        *,
        idempotency_key: str,
    ) -> MpaAgentOperation:
        if request.operation_kind != "update":
            raise ValueError("update_agent requires operationKind=update")
        if not request.runtime_revision.strip():
            raise ValueError("A runtime revision is required for update.")
        if not idempotency_key.strip():
            raise ValueError("Idempotency key is required.")
        response = await self._request(
            "PATCH",
            f"/web/mpa/agents/{quote(mpa_instance_id, safe='')}",
            headers={"Idempotency-Key": idempotency_key},
            json=request.model_dump(mode="json", by_alias=True),
        )
        return self._model(response, MpaAgentOperation)

    async def list_active_operations(self) -> list[MpaAgentOperation]:
        response = await self._request(
            "GET", "/web/mpa/agent-operations", params={"status": "active"}
        )
        try:
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(
                payload.get("operations"), list
            ):
                raise TypeError
            return [
                MpaAgentOperation.model_validate(item) for item in payload["operations"]
            ]
        except (TypeError, ValueError, ValidationError) as error:
            raise MpaControlPlaneError(
                "control_plane_invalid_response", status_code=502
            ) from error

    async def get_operation(self, operation_id: str) -> MpaAgentOperation:
        response = await self._request(
            "GET", f"/web/mpa/agent-operations/{quote(operation_id, safe='')}"
        )
        return self._model(response, MpaAgentOperation)

    async def retry_operation(
        self, operation_id: str, request: MpaAgentOperationRequest
    ) -> MpaAgentOperation:
        if request.operation_kind == "update" and not request.runtime_revision.strip():
            raise ValueError("A runtime revision is required for update retry.")
        response = await self._request(
            "POST",
            f"/web/mpa/agent-operations/{quote(operation_id, safe='')}/retry",
            json=request.model_dump(mode="json", by_alias=True),
        )
        return self._model(response, MpaAgentOperation)

    async def get_profile_status(
        self,
        mpa_instance_id: str,
        *,
        runtime_id: str,
        region: str = "cn-beijing",
    ) -> MpaProfileStatus:
        response = await self._request(
            "GET",
            f"/web/mpa/agents/{quote(mpa_instance_id, safe='')}/profile-status",
            params={"runtimeId": runtime_id, "region": region},
        )
        return self._model_with_etag(response, MpaProfileStatus)

    async def apply_profile(
        self,
        mpa_instance_id: str,
        *,
        runtime_id: str,
        source_profile_id: str,
        profile: MpaProfile,
        idempotency_key: str,
        region: str = "cn-beijing",
        create: bool = False,
        runtime_revision: str = "",
    ) -> MpaProfileStatus:
        if create and runtime_revision:
            raise ValueError("create cannot carry a runtime revision")
        if not create and not runtime_revision.strip():
            raise ValueError("A runtime revision is required for update.")
        if not idempotency_key.strip():
            raise ValueError("Idempotency key is required.")
        response = await self._request(
            "PUT",
            f"/web/mpa/agents/{quote(mpa_instance_id, safe='')}/profile",
            headers={"Idempotency-Key": idempotency_key},
            json={
                "runtimeId": runtime_id,
                "region": region,
                "mpaInstanceId": mpa_instance_id,
                "sourceProfileId": source_profile_id,
                "profile": profile.model_dump(mode="json", by_alias=True),
                "create": create,
                "runtimeRevision": runtime_revision,
            },
        )
        return self._model_with_etag(response, MpaProfileStatus)

    async def get_session_execution_config(
        self,
        session_id: str,
        *,
        runtime_id: str,
        region: str = "cn-beijing",
    ) -> MpaSessionExecutionConfig:
        response = await self._request(
            "GET",
            f"/web/mpa/sessions/{quote(session_id, safe='')}/execution-config",
            params={"runtimeId": runtime_id, "region": region},
        )
        return self._model_with_etag(response, MpaSessionExecutionConfig)

    async def patch_session_execution_config(
        self,
        session_id: str,
        *,
        runtime_id: str,
        etag: str,
        changes: list[MpaExecutionConfigChange],
        region: str = "cn-beijing",
    ) -> MpaSessionExecutionConfig:
        if not etag.strip():
            raise ValueError("ETag is required for an execution-config update.")
        response = await self._request(
            "PATCH",
            f"/web/mpa/sessions/{quote(session_id, safe='')}/execution-config",
            headers={"If-Match": etag},
            json={
                "runtimeId": runtime_id,
                "region": region,
                "changes": [
                    change.model_dump(mode="json", by_alias=True) for change in changes
                ],
            },
        )
        return self._model_with_etag(response, MpaSessionExecutionConfig)

    async def upgrade_session_profile(
        self,
        session_id: str,
        *,
        runtime_id: str,
        etag: str,
        idempotency_key: str,
        target_profile_revision: int,
        region: str = "cn-beijing",
    ) -> MpaSessionExecutionConfig:
        if not etag.strip():
            raise ValueError("ETag is required for a Profile upgrade.")
        if not idempotency_key.strip():
            raise ValueError("Idempotency key is required.")
        if target_profile_revision < 1:
            raise ValueError("Target Profile revision must be positive.")
        response = await self._request(
            "POST",
            f"/web/mpa/sessions/{quote(session_id, safe='')}/profile-upgrade",
            headers={
                "If-Match": etag,
                "Idempotency-Key": idempotency_key,
            },
            json={
                "runtimeId": runtime_id,
                "region": region,
                "targetProfileRevision": target_profile_revision,
            },
        )
        return self._model_with_etag(response, MpaSessionExecutionConfig)

    async def get_delete_preview(
        self,
        mpa_instance_id: str,
        *,
        runtime_id: str,
        region: str = "cn-beijing",
    ) -> MpaAgentDeletePreview:
        response = await self._request(
            "GET",
            f"/web/mpa/agents/{quote(mpa_instance_id, safe='')}/delete-preview",
            params={"runtimeId": runtime_id, "region": region},
        )
        return self._model(response, MpaAgentDeletePreview)

    @staticmethod
    def _model(response: httpx.Response, model: type[_Model]) -> _Model:
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError
            return model.model_validate(payload)
        except (TypeError, ValueError, ValidationError) as error:
            raise MpaControlPlaneError(
                "control_plane_invalid_response", status_code=502
            ) from error

    @classmethod
    def _model_with_etag(cls, response: httpx.Response, model: type[_Model]) -> _Model:
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError
            if etag := response.headers.get("ETag", ""):
                payload["etag"] = etag
            return model.model_validate(payload)
        except (TypeError, ValueError, ValidationError) as error:
            raise MpaControlPlaneError(
                "control_plane_invalid_response", status_code=502
            ) from error

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}))
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        try:
            response = await self._transport.request(
                method, f"{self._base_url}{path}", headers=headers, **kwargs
            )
        except httpx.TimeoutException as error:
            raise MpaControlPlaneError(
                "control_plane_timeout", status_code=0, retryable=True
            ) from error
        except httpx.RequestError as error:
            raise MpaControlPlaneError(
                "control_plane_unavailable", status_code=0, retryable=True
            ) from error
        if response.is_error:
            raise self._response_error(response)
        return response

    @staticmethod
    def _response_error(response: httpx.Response) -> MpaControlPlaneError:
        detail: Any = None
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = payload.get("detail", payload.get("error"))
        except ValueError:
            pass
        if isinstance(detail, dict):
            code = MpaControlPlaneClient._safe_error_code(
                detail.get("code"), response.status_code
            )
            request_id = str(
                detail.get("requestId") or response.headers.get("X-Request-Id", "")
            )
            current_state = detail.get("currentState")
            if not isinstance(current_state, dict):
                current_state = None
        else:
            code = MpaControlPlaneClient._safe_error_code(detail, response.status_code)
            request_id = response.headers.get("X-Request-Id", "")
            current_state = None
        return MpaControlPlaneError(
            code,
            status_code=response.status_code,
            request_id=request_id,
            retryable=response.status_code in _RETRYABLE_STATUS_CODES,
            current_state=current_state,
        )

    @staticmethod
    def _safe_error_code(value: Any, status_code: int) -> str:
        candidate = value if isinstance(value, str) else ""
        if _SAFE_ERROR_CODE.fullmatch(candidate):
            return candidate
        return f"http_{status_code}"

    @staticmethod
    def _bearer_value(value: str) -> str:
        token = value.strip()
        if token.lower().startswith("bearer "):
            return token[7:].strip()
        return token
