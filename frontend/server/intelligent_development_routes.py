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

"""Studio-only HTTP surface for foreground intelligent development."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
import json
import re
import shlex
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from frontend.server.intelligent_development import (
    DevSession,
    DevelopmentEvent,
    IntelligentDevelopmentVerifier,
)
from frontend.server.sandbox_remote import SandboxRemoteTransport
from veadk.cli.frontend_sandbox import (
    SandboxCapacityError,
    SandboxCloudSession,
    SandboxConfigurationError,
    SandboxConversationService,
    SandboxError,
    SandboxProvisioningError,
    SandboxSessionNotFoundError,
    SandboxSessionUnavailableError,
    SandboxValidationError,
    mount_sandbox_routes,
)

INTELLIGENT_DEVELOPMENT_PREFIX = "/web/intelligent-development"
INTELLIGENT_DEVELOPMENT_TOOL_NAME = "intelligent-development"
INTELLIGENT_DEVELOPMENT_AGENT_KIND = "intelligent-development"
INTELLIGENT_DEVELOPMENT_WORKLOAD = INTELLIGENT_DEVELOPMENT_AGENT_KIND
INTELLIGENT_DEVELOPMENT_SCHEMA_VERSION = "1"
_PROJECT_ROOT = "/home/gem/workspace"
_SAFE_WORKSPACE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class IntelligentDevelopmentGateway:
    """Delegate shared cloud APIs without owning their lifecycle."""

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    def __getattr__(self, name: str) -> Any:
        return getattr(self._gateway, name)

    async def drain(self) -> None:
        """The ordinary Sandbox service owns the shared gateway lifecycle."""

    async def create_session(self, *args: Any, **kwargs: Any) -> SandboxCloudSession:
        return await self._gateway.create_session(*args, **kwargs)


class _SandboxSurfaceAdapter:
    """Expose the existing Sandbox route adapter below a Studio-only prefix."""

    def __init__(
        self,
        app: FastAPI,
        service: SandboxConversationService,
        owner_resolver: Callable[[Request], str],
    ) -> None:
        self._app = app
        self._service = service
        self._owner_resolver = owner_resolver

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Any],
        send: Callable[[dict[str, Any]], Any],
    ) -> None:
        rewritten = dict(scope)
        path = scope.get("path", "")
        allowed_suffixes = (
            "/approvals/",
            "/disconnect",
        )
        if not any(marker in path for marker in allowed_suffixes):
            raise HTTPException(status_code=404, detail="Not Found")
        parts = path.split("/")
        try:
            session_index = parts.index("sessions") + 1
            session_id = parts[session_index]
        except (ValueError, IndexError):
            raise HTTPException(status_code=404, detail="Not Found")
        request = Request(scope, receive=receive)
        owner = self._owner_resolver(request)
        try:
            await resolve_intelligent_development_session(
                self._service, session_id, owner
            )
        except SandboxError as error:
            raise _http_error(error) from error
        rewritten["path"] = f"/web/sandbox{path}"
        raw_path = scope.get("raw_path")
        if isinstance(raw_path, bytes):
            rewritten["raw_path"] = b"/web/sandbox" + raw_path
        await self._app(rewritten, receive, send)


def _http_error(error: SandboxError) -> HTTPException:
    status = 500
    if isinstance(error, SandboxConfigurationError):
        status = 503
    elif isinstance(error, SandboxValidationError):
        status = 422
    elif isinstance(error, SandboxSessionNotFoundError):
        status = 404
    elif isinstance(error, (SandboxSessionUnavailableError, SandboxCapacityError)):
        status = 409
    elif isinstance(error, SandboxProvisioningError):
        status = 502
    return HTTPException(
        status_code=status,
        detail={
            "code": error.code,
            "message": str(error),
            "retryable": error.retryable,
        },
    )


def _public_session(session: SandboxCloudSession) -> dict[str, object]:
    return {
        "sessionId": session.instance_id,
        "userSessionId": session.user_session_id,
        "status": session.status,
        "createdAt": session.created_at,
        "expireAt": session.expire_at,
        "toolType": session.tool_type,
        "createdBy": session.creator_name or session.created_by,
        "displayName": session.display_name,
        "persistent": False,
        "toolName": INTELLIGENT_DEVELOPMENT_TOOL_NAME,
    }


async def _request_object(request: Request, maximum: int) -> dict[str, object]:
    body = await request.body()
    if len(body) > maximum:
        raise SandboxValidationError("请求内容过大。")
    try:
        value = json.loads(body) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SandboxValidationError("请求不是有效 JSON。") from error
    if not isinstance(value, dict):
        raise SandboxValidationError("请求必须是 JSON 对象。")
    return value


def _require_development_session(session: SandboxCloudSession) -> None:
    if session.agent_kind != INTELLIGENT_DEVELOPMENT_AGENT_KIND:
        raise SandboxSessionNotFoundError("智能开发 Session 不存在或不属于当前用户。")


async def resolve_intelligent_development_session(
    service: SandboxConversationService,
    session_id: str,
    owner_id: str,
) -> SandboxCloudSession:
    """Resolve an owner-scoped Dev Session without granting admin bypass."""
    cloud = await service._cloud_session(session_id)
    if cloud.created_by != owner_id:
        raise SandboxSessionNotFoundError("智能开发 Session 不存在或不属于当前用户。")
    _require_development_session(cloud)
    if cloud.status.lower() != "ready" or not cloud.endpoint:
        raise SandboxSessionUnavailableError("智能开发 Session 尚未就绪。")
    if cloud.expire_at:
        try:
            expires_at = datetime.fromisoformat(cloud.expire_at.replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except ValueError as error:
            raise SandboxSessionUnavailableError(
                "智能开发 Session 过期时间无效。"
            ) from error
        if expires_at <= datetime.now(timezone.utc):
            raise SandboxSessionNotFoundError("智能开发 Session 已过期。")
    return cloud


def _workspace(session: SandboxCloudSession) -> str:
    _require_development_session(session)
    identity = session.user_session_id
    if not _SAFE_WORKSPACE.fullmatch(identity):
        raise SandboxSessionUnavailableError("开发工作空间标识无效。")
    return f"{_PROJECT_ROOT}/{identity}"


async def _prepare_workspace(session: SandboxCloudSession) -> str:
    workspace = _workspace(session)
    source = (
        "import os,stat\n"
        f"root={_PROJECT_ROOT!r}; path={workspace!r}\n"
        "os.makedirs(root,mode=0o755,exist_ok=True)\n"
        "os.makedirs(path,mode=0o700,exist_ok=True)\n"
        "metadata=os.stat(path,follow_symlinks=False)\n"
        "assert stat.S_ISDIR(metadata.st_mode)\n"
        "os.chmod(path,0o700)\n"
    )
    await SandboxRemoteTransport(session.endpoint).exec_text(
        f"python3 -c {shlex.quote(source)}",
        timeout=12,
    )
    return workspace


VerifierFactory = Callable[
    [Callable[[DevelopmentEvent], Any]], IntelligentDevelopmentVerifier
]
CleanupStaleRuntimes = Callable[[], Any]


def mount_intelligent_development_routes(
    app: FastAPI,
    service: SandboxConversationService,
    owner_resolver: Callable[[Request], str],
    creator_resolver: Callable[[Request], str],
    verifier_factory: VerifierFactory | None = None,
    configured: bool = True,
    cleanup_stale_runtimes: CleanupStaleRuntimes | None = None,
) -> None:
    """Mount fixed SANDBOX_DEV routes without changing the generic Sandbox API."""

    delegated = FastAPI()
    verification_locks: dict[tuple[str, str], asyncio.Lock] = {}
    verification_locks_guard = asyncio.Lock()
    mount_sandbox_routes(
        delegated,
        service,
        owner_resolver,
        admin_resolver=lambda _request: False,
        creator_resolver=creator_resolver,
    )

    @app.get(f"{INTELLIGENT_DEVELOPMENT_PREFIX}/capabilities")
    async def _capabilities(request: Request) -> dict[str, object]:
        owner_resolver(request)
        if not configured:
            return {"enabled": False, "reason": "管理员未配置 SANDBOX_DEV"}
        return {"enabled": True, "reason": ""}

    @app.get(f"{INTELLIGENT_DEVELOPMENT_PREFIX}/sessions")
    async def _list(request: Request) -> dict[str, object]:
        owner = owner_resolver(request)
        try:
            sessions = await service.list_sessions(owner, is_admin=False)
        except SandboxError as error:
            raise _http_error(error) from error
        return {
            "sessions": [
                _public_session(session)
                for session in sessions
                if session.agent_kind == INTELLIGENT_DEVELOPMENT_AGENT_KIND
            ]
        }

    @app.post(f"{INTELLIGENT_DEVELOPMENT_PREFIX}/sessions")
    async def _create(request: Request) -> dict[str, object]:
        owner = owner_resolver(request)
        if not configured:
            raise HTTPException(status_code=503, detail="管理员未配置 SANDBOX_DEV")
        try:
            data = await _request_object(request, 64 * 1024)
            if set(data) - {"displayName"}:
                raise SandboxValidationError("智能开发会话只接受 displayName。")
            session = await service.create(
                owner,
                data.get("displayName", ""),
                creator_resolver(request),
                False,
            )
        except SandboxError as error:
            raise _http_error(error) from error
        _require_development_session(session)
        return _public_session(session)

    @app.delete(f"{INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/{{session_id}}")
    async def _delete(session_id: str, request: Request) -> dict[str, bool]:
        owner = owner_resolver(request)
        try:
            await resolve_intelligent_development_session(service, session_id, owner)
            await service.delete(session_id, owner, is_admin=False)
        except SandboxError as error:
            raise _http_error(error) from error
        return {"deleted": True}

    @app.post(f"{INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/{{session_id}}/connect")
    async def _connect(session_id: str, request: Request) -> dict[str, object]:
        owner = owner_resolver(request)
        try:
            cloud = await resolve_intelligent_development_session(
                service, session_id, owner
            )
            workspace = _workspace(cloud)
            conversation = await service.connect(session_id, owner, is_admin=False)
            _require_development_session(conversation.cloud)
            if not conversation.codex.workspace_locked:
                await _prepare_workspace(conversation.cloud)
                await service.update_workspace(session_id, owner, workspace)
            elif conversation.codex.cwd != workspace:
                raise SandboxSessionUnavailableError("开发会话已在非预期工作空间启动。")
        except SandboxError as error:
            raise _http_error(error) from error
        return {
            **_public_session(conversation.cloud),
            **service.settings(session_id, owner),
        }

    @app.post(
        f"{INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/{{session_id}}/verify-deliver"
    )
    async def _verify_deliver(
        session_id: str,
        request: Request,
    ) -> StreamingResponse:
        owner = owner_resolver(request)
        if verifier_factory is None:
            raise HTTPException(
                status_code=503,
                detail="智能开发验证服务尚未配置。",
            )
        try:
            cloud = await resolve_intelligent_development_session(
                service, session_id, owner
            )
            project_root = _workspace(cloud)
            conversation = await service.connect(session_id, owner, is_admin=False)
            _require_development_session(conversation.cloud)
            if conversation.codex.active:
                raise SandboxSessionUnavailableError(
                    "当前开发回复尚未完成，请稍后再验证。"
                )
            if conversation.codex.cwd != project_root:
                raise SandboxSessionUnavailableError("开发工作空间不符合验证要求。")
        except SandboxError as error:
            raise _http_error(error) from error

        lock_key = (owner, session_id)
        async with verification_locks_guard:
            verification_lock = verification_locks.setdefault(lock_key, asyncio.Lock())
            if verification_lock.locked():
                raise _http_error(
                    SandboxSessionUnavailableError(
                        "当前 Session 正在验证，请勿重复提交。"
                    )
                )
            await verification_lock.acquire()
        queue: asyncio.Queue[DevelopmentEvent | None] = asyncio.Queue()

        async def event_sink(event: DevelopmentEvent) -> None:
            await queue.put(event)

        try:
            verifier = verifier_factory(event_sink)
            session = DevSession(
                owner_id=owner,
                session_id=conversation.cloud.instance_id,
                endpoint=conversation.cloud.endpoint,
                project_root=project_root,
            )
        except Exception:
            async with verification_locks_guard:
                verification_lock.release()
                verification_locks.pop(lock_key, None)
            raise

        async def run() -> None:
            try:
                await verifier.run(owner_id=owner, session=session)
            finally:
                async with verification_locks_guard:
                    verification_lock.release()
                    verification_locks.pop(lock_key, None)
                await queue.put(None)

        async def stream() -> AsyncIterator[str]:
            task = asyncio.create_task(run())
            try:
                while True:
                    event = await queue.get()
                    if event is None:
                        break
                    yield event.as_sse()
                await task
            except asyncio.CancelledError:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                raise
            except Exception:
                if not task.done():
                    task.cancel()
                payload = {
                    "code": "INTELLIGENT_DEVELOPMENT_FAILED",
                    "message": "验证未能完成，请返回开发会话后重试。",
                    "retryable": True,
                }
                yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get(f"{INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/{{session_id}}/status")
    async def _status(session_id: str, request: Request) -> dict[str, object]:
        owner = owner_resolver(request)
        try:
            await resolve_intelligent_development_session(service, session_id, owner)
            return service.status(session_id, owner)
        except SandboxError as error:
            raise _http_error(error) from error

    @app.get(f"{INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/{{session_id}}/models")
    async def _models(session_id: str, request: Request) -> dict[str, object]:
        owner = owner_resolver(request)
        try:
            await resolve_intelligent_development_session(service, session_id, owner)
            models = await service.list_models(session_id, owner)
        except SandboxError as error:
            raise _http_error(error) from error
        return {"models": [model.public_dict() for model in models]}

    @app.put(f"{INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/{{session_id}}/model")
    async def _model(session_id: str, request: Request) -> dict[str, object]:
        owner = owner_resolver(request)
        try:
            await resolve_intelligent_development_session(service, session_id, owner)
            body = await _request_object(request, 64 * 1024)
            model = body.get("model")
            if set(body) != {"model"} or not isinstance(model, str):
                raise SandboxValidationError("模型名称必须是文本。")
            return {"model": await service.set_model(session_id, owner, model)}
        except SandboxError as error:
            raise _http_error(error) from error

    @app.get(f"{INTELLIGENT_DEVELOPMENT_PREFIX}/releases/summary")
    async def _release_summary(
        request: Request,
        sessionId: str,
        artifactSha256: str,
        validationReportSha256: str,
    ) -> dict[str, object]:
        import shutil
        import tempfile
        from pathlib import Path
        from frontend.server.deployment_source import DeploymentSourceError
        from frontend.server.intelligent_development_source import (
            materialize_intelligent_development_source,
        )

        owner = owner_resolver(request)
        destination = Path(tempfile.mkdtemp(prefix="intelligent-summary-"))
        try:
            trusted = await materialize_intelligent_development_source(
                destination,
                {
                    "kind": "intelligentDevelopment",
                    "sessionId": sessionId,
                    "artifactSha256": artifactSha256,
                    "validationReportSha256": validationReportSha256,
                },
                owner_id=owner,
                service=service,
            )
        except DeploymentSourceError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except SandboxSessionNotFoundError as error:
            raise _http_error(error) from error
        except SandboxSessionUnavailableError as error:
            raise _http_error(error) from error
        except Exception as error:
            raise HTTPException(
                status_code=502,
                detail="无法校验已验证交付物。",
            ) from error
        finally:
            shutil.rmtree(destination, ignore_errors=True)
        return {
            "sessionId": sessionId,
            "artifactSha256": trusted.artifact_sha256,
            "validationReportSha256": trusted.validation_report_sha256,
            "agentName": trusted.agent_name,
            "entryPoint": trusted.entry_point,
            "fileCount": trusted.file_count,
            "artifactSize": trusted.artifact_size,
            "validatedAt": trusted.validated_at,
            "gateSummary": list(trusted.gate_summary),
        }

    @app.get(f"{INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/{{session_id}}/skills")
    async def _skills_unavailable(session_id: str, request: Request) -> None:
        del session_id
        owner_resolver(request)
        raise HTTPException(status_code=404, detail="Not Found")

    @app.post(f"{INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/{{session_id}}/interrupt")
    async def _interrupt(session_id: str, request: Request) -> dict[str, bool]:
        owner = owner_resolver(request)
        try:
            await resolve_intelligent_development_session(service, session_id, owner)
            conversation = service._owned(session_id, owner)
            await conversation.codex.interrupt()
        except SandboxError as error:
            raise _http_error(error) from error
        return {"interrupted": True}

    @app.post(f"{INTELLIGENT_DEVELOPMENT_PREFIX}/sessions/{{session_id}}/messages")
    async def _message(session_id: str, request: Request) -> StreamingResponse:
        owner = owner_resolver(request)
        try:
            data = await _request_object(request, 128 * 1024)
            if set(data) != {"message"}:
                raise SandboxValidationError("智能开发会话只接受文本消息。")
            prompt = data.get("message")
            if not isinstance(prompt, str) or not prompt.strip():
                raise SandboxValidationError("message must not be empty")
            if len(prompt) > 100_000:
                raise SandboxValidationError("message is too large")
            service.require_owned(session_id, owner)
        except SandboxError as error:
            raise _http_error(error) from error

        async def stream() -> AsyncIterator[str]:
            try:
                async for event in service.stream_message(
                    session_id,
                    owner,
                    prompt.strip(),
                ):
                    if event.kind == "text":
                        payload = {"text": event.text}
                        yield f"event: delta\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    elif event.approval is not None:
                        yield (
                            "event: approval\n"
                            f"data: {json.dumps(event.approval, ensure_ascii=False)}\n\n"
                        )
                    elif event.approval_resolved_id:
                        payload = {"approvalId": event.approval_resolved_id}
                        yield (
                            "event: approval_resolved\n"
                            f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        )
                    elif event.kind == "usage" and event.usage is not None:
                        payload = {
                            "turnId": event.turn_id,
                            "usage": event.usage.public_dict(),
                            **(
                                {"threadTotal": event.thread_total.public_dict()}
                                if event.thread_total is not None
                                else {}
                            ),
                            **(
                                {"modelContextWindow": event.model_context_window}
                                if event.model_context_window is not None
                                else {}
                            ),
                        }
                        yield f"event: usage\ndata: {json.dumps(payload)}\n\n"
                    else:
                        payload = {
                            "id": event.item_id,
                            "kind": event.kind,
                            "status": event.status,
                            "text": event.text or None,
                            "name": event.name or None,
                            "args": event.arguments,
                            "response": event.response,
                        }
                        yield f"event: activity\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                yield "event: done\ndata: {}\n\n"
            except SandboxError as error:
                payload = {
                    "code": error.code,
                    "message": str(error),
                    "retryable": error.retryable,
                }
                yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                yield 'event: done\ndata: {"reason":"failed"}\n\n'

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    app.mount(
        INTELLIGENT_DEVELOPMENT_PREFIX,
        _SandboxSurfaceAdapter(delegated, service, owner_resolver),
    )

    cleanup_task: asyncio.Task[None] | None = None

    async def _cleanup_loop() -> None:
        while True:
            await asyncio.sleep(60)
            await service.cleanup_expired()
            if cleanup_stale_runtimes is not None:
                try:
                    result = cleanup_stale_runtimes()
                    if result is not None:
                        await result
                except Exception:
                    # The next bounded cycle retries; conversation cleanup must continue.
                    pass

    async def _start() -> None:
        nonlocal cleanup_task
        cleanup_task = asyncio.create_task(_cleanup_loop())

    async def _stop() -> None:
        if cleanup_task is not None:
            cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cleanup_task
        await service.close_all()

    app.router.on_startup.append(_start)
    app.router.on_shutdown.append(_stop)


__all__ = [
    "INTELLIGENT_DEVELOPMENT_PREFIX",
    "INTELLIGENT_DEVELOPMENT_SCHEMA_VERSION",
    "INTELLIGENT_DEVELOPMENT_TOOL_NAME",
    "INTELLIGENT_DEVELOPMENT_WORKLOAD",
    "IntelligentDevelopmentGateway",
    "mount_intelligent_development_routes",
]
