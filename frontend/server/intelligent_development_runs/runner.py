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

"""Recover the full build lifecycle using Codex and Sandbox execution facts."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from frontend.server.intelligent_development import DeliveryReference, StudioCredentials
from frontend.server.intelligent_development_projects import (
    IntelligentDevelopmentProjectNotFound,
    IntelligentDevelopmentProjectService,
    IntelligentDevelopmentProjectStorageUnavailable,
    IntelligentDevelopmentVersionIntegrityError,
)
from frontend.server.intelligent_development_task import (
    BUILD_RESULT_TOOL,
    COMPLETION_FILE_PREFIX,
    CompletionContract,
    CredentialResolver,
    DeliveryPublisher,
    IntentDecision,
    TaskCredentialLease,
    builder_prompt,
    create_credential_lease,
    invalidate_current_delivery,
    parse_build_result,
    read_completion_contract,
    remove_completion_file,
    result_reporting_prompt,
)
from veadk.cli.codex_app_server import (
    CodexAppServerEvent,
    CodexAppServerRequestError,
    CodexAppServerSession,
    CodexPermissionSettings,
)
from veadk.cli.frontend_sandbox import (
    SandboxCloudSession,
    SandboxSessionNotFoundError,
    redact_sandbox_text,
)
from veadk.utils.logger import get_logger

from .models import Run
from .output import TaskTextProjection
from .repository import RunCapacity, RunConflict, RunLeaseLost, RunRepository
from .shell import RunShell

if TYPE_CHECKING:
    from frontend.server.sandbox_remote import SandboxRemoteTransport
else:

    def SandboxRemoteTransport(endpoint: str):  # noqa: N802
        """Load the injectable transport only when a development run needs it."""
        from frontend.server.sandbox_remote import (
            SandboxRemoteTransport as _SandboxRemoteTransport,
        )

        return _SandboxRemoteTransport(endpoint)


logger = get_logger(__name__)
_PERMISSIONS = CodexPermissionSettings(
    approval_policy="never",
    approvals_reviewer="auto_review",
    sandbox_mode="danger-full-access",
    network_access=True,
)
_REPORT_PERMISSIONS = CodexPermissionSettings(
    approval_policy="never",
    approvals_reviewer="auto_review",
    sandbox_mode="read-only",
    network_access=False,
)


class StopRequested(Exception):
    pass


class InputUnconfirmed(Exception):
    pass


class NativeTurnFailed(Exception):
    """An authoritative terminal turn needs corrected input or configuration."""


def _public_issue(run: Run, error: Exception) -> dict[str, Any]:
    code, message, retryable = (
        "INTELLIGENT_DEVELOPMENT_FAILED",
        "任务暂时无法恢复，请稍后继续。",
        True,
    )
    if isinstance(error, InputUnconfirmed):
        code, message = (
            "INTELLIGENT_DEVELOPMENT_INPUT_UNCONFIRMED",
            "消息是否送达暂时无法确认，请稍后恢复以核对状态。",
        )
    elif isinstance(error, NativeTurnFailed):
        code, message = (
            "SANDBOX_INVOCATION_FAILED",
            "Codex 本轮未完成，请检查模型配置或补充要求后继续。",
        )
    elif isinstance(error, IntelligentDevelopmentVersionIntegrityError):
        code, message, retryable = (
            "INTELLIGENT_DEVELOPMENT_VERSION_INVALID",
            "项目版本源码完整性校验失败。请重新构建。",
            False,
        )
    elif isinstance(error, IntelligentDevelopmentProjectStorageUnavailable):
        code, message = (
            "INTELLIGENT_DEVELOPMENT_STORAGE_UNAVAILABLE",
            "源码已生成，但项目版本暂时无法保存。请稍后继续保存。",
        )
    elif run.phase == "outcome_read":
        code, message = (
            "INTELLIGENT_DEVELOPMENT_OUTCOME_INVALID",
            "Codex 未能确认本轮结果，未发布新版本。请继续以补齐验证结果。",
        )
    elif run.phase == "cycle_complete":
        code, message = (
            "INTELLIGENT_DEVELOPMENT_CLEANUP_INCOMPLETE",
            "任务清理暂未完成，请稍后继续。",
        )
    elif run.phase == "delivery":
        message = "源码交付暂未完成，请稍后继续。系统会核对已有结果。"
    elif run.phase == "prepare":
        message = "开发环境准备暂未完成，请检查配置或稍后继续。"
    return {
        "code": code,
        "message": message,
        "retryable": retryable,
        "phase": run.phase,
    }


class DevelopmentRunner:
    def __init__(
        self,
        repository: RunRepository,
        *,
        resolve_session: Callable[[str, str], Awaitable[SandboxCloudSession]],
        workspace: Callable[[SandboxCloudSession], str],
        credentials: CredentialResolver,
        render_event: Callable[
            [CodexAppServerEvent, TaskCredentialLease],
            tuple[str, dict[str, Any]] | None,
        ],
        renew_session: Callable[[SandboxCloudSession], Awaitable[SandboxCloudSession]]
        | None = None,
        project_service: IntelligentDevelopmentProjectService | None = None,
        validation_region: str = "cn-beijing",
        validation_project: str = "default",
        codex_factory: Callable[[str], CodexAppServerSession] = CodexAppServerSession,
        command_progress: Callable[[CodexAppServerEvent], str | None] = lambda _: None,
    ) -> None:
        self.repository = repository
        self.resolve_session = resolve_session
        self.workspace = workspace
        self.credentials = credentials
        self.render_event = render_event
        self.renew_session = renew_session
        self.project_service = project_service
        self.validation_region = validation_region
        self.validation_project = validation_project
        self.codex_factory = codex_factory
        self.command_progress = command_progress
        self.retry_delays = (1, 2, 4, 8, 16)

    async def __call__(self, initial: Run, token: str) -> None:
        owner, run_id = initial.owner_id, initial.id
        for attempt in range(len(self.retry_delays) + 1):
            run = await self.repository.get(owner, run_id)
            if run.terminal:
                return
            try:
                await self._attempt(run, token)
                return
            except asyncio.CancelledError:
                # Local shutdown detaches observation; it never requests interruption.
                raise
            except RunLeaseLost:
                raise
            except RunCapacity:
                await self.repository.update(
                    owner,
                    run_id,
                    token,
                    state="waiting_user",
                    state_message="任务输出已达到短期存储上限，已有内容已保留。可停止任务后发起新任务。",
                )
                return
            except SandboxSessionNotFoundError:
                await self.repository.update(
                    owner,
                    run_id,
                    token,
                    state="failed",
                    state_message="开发环境已失效，已有输出已保留。请创建新的开发环境。",
                )
                return
            except Exception as error:
                run = await self.repository.get(owner, run_id)
                logger.warning(
                    "Development recovery run_id=%s session_id=%s thread_id=%s phase=%s attempt=%s error_type=%s",
                    run_id,
                    run.session_id,
                    run.thread_id,
                    run.phase,
                    attempt + 1,
                    type(error).__name__,
                )
                if run.terminal:
                    return
                issue = _public_issue(run, error)
                await self.repository.checkpoint(owner, run_id, token, issue=issue)
                if not issue["retryable"] and not run.stop_requested:
                    await self.repository.update(
                        owner,
                        run_id,
                        token,
                        state="failed",
                        state_message=issue["message"] + "已有输出已保留。",
                    )
                    return
                if attempt == len(self.retry_delays) or isinstance(
                    error, NativeTurnFailed
                ):
                    state = "stopping" if run.stop_requested else "waiting_user"
                    message = (
                        "已请求停止，正在等待开发环境恢复以确认停止状态。"
                        if run.stop_requested
                        else issue["message"] + "已有输出已保留。"
                    )
                else:
                    state = "stopping" if run.stop_requested else "recovering"
                    message = (
                        "正在确认停止状态。"
                        if run.stop_requested
                        else "正在重新连接并恢复任务。"
                    )
                await self.repository.update(
                    owner, run_id, token, state=state, state_message=message
                )
                if isinstance(error, NativeTurnFailed):
                    return
                if attempt < len(self.retry_delays):
                    await asyncio.sleep(self.retry_delays[attempt])

    async def _attempt(self, run: Run, token: str) -> None:
        owner, run_id = run.owner_id, run.id
        await self.repository.heartbeat(owner, run_id, token)
        cloud = await self.resolve_session(run.session_id, owner)
        if cloud.created_by != owner:
            raise SandboxSessionNotFoundError("开发环境不属于当前用户。")
        if self.renew_session is not None and not run.stop_requested:
            cloud = await self.renew_session(cloud)
        root = self.workspace(cloud)
        transport = SandboxRemoteTransport(cloud.endpoint)
        task_root = f"/home/gem/.intelligent-development/tasks/{run_id}"
        lease = TaskCredentialLease(
            transport,
            task_root,
            f"{task_root}/with-agentkit-credentials",
            f"{task_root}/credentials.json",
            self.credentials().secret_values,
        )
        if run.checkpoint.get("lease_ready") and run.phase in {
            "coding",
            "reporting",
            "outcome_read",
            "delivery",
            "version",
        }:
            # A credential rotation must not make old in-flight output unredactable.
            # Read the existing lease only into memory; secrets never enter SQLite.
            value = json.loads(
                await transport.download(lease.credential_path, max_bytes=16_384)
            )
            previous = StudioCredentials(
                value["accessKeyId"],
                value["secretAccessKey"],
                value.get("sessionToken", ""),
            )
            lease.exact_secrets = tuple(
                set((*lease.exact_secrets, *previous.secret_values))
            )
        codex = self.codex_factory(cloud.endpoint)
        codex.cwd = root
        codex.permissions = _PERMISSIONS
        if run.checkpoint.get("result_protocol") == "tool-v1":
            codex.dynamic_tools = (BUILD_RESULT_TOOL,)

            async def submit_result(params):
                return await self._submit_result(owner, run_id, token, params, lease)

            codex.dynamic_tool_handler = submit_result
        # Bind before connect, so restart cannot select an unrelated "latest" thread.
        controller: asyncio.Task[None] | None = None
        work: asyncio.Task[None] | None = None
        try:
            if run.thread_id:
                inputs = await self.repository.inputs(owner, run_id)
                history = await self.repository.session_runs(owner, run.session_id)
                unused = (
                    run.phase == "prepare"
                    and not run.turn_id
                    and not run.checkpoint.get("continuation_sending")
                    and all(item["status"] == "pending" for item in inputs)
                    and not any(item.id != run_id for item in history)
                )
                # Codex does not persist a rollout before the first accepted turn.
                # Replacing that empty preparation is safe only before submission.
                await codex.attach_thread(run.thread_id, allow_empty_restart=unused)
            else:
                await codex.connect()
            await self.repository.update(
                owner, run_id, token, thread_id=codex.thread_id
            )
            if not run.stop_requested:
                await self.repository.append_event(
                    owner,
                    run_id,
                    token,
                    "progress",
                    {"text": "Codex 正在处理本次请求。"},
                )
            controller = asyncio.create_task(self._control(run, token, codex))

            async def drive():
                nonlocal run, lease
                while True:
                    run = await self.repository.get(owner, run_id)
                    if run.stop_requested:
                        await self._confirm_stop(run, token, codex)
                        raise StopRequested
                    if not run.checkpoint.get("lease_ready"):
                        lease = await create_credential_lease(
                            cloud.endpoint, self.credentials, lease_id=run_id
                        )
                        run = await self.repository.checkpoint(
                            owner, run_id, token, lease_ready=True
                        )
                    if run.phase in {"prepare", "coding", "reporting"}:
                        await self._coding(run, token, codex, lease, cloud, root)
                    run = await self.repository.get(owner, run_id)
                    await self._check_stop(run)
                    if run.phase == "outcome_read":
                        tool_protocol = (
                            run.checkpoint.get("result_protocol") == "tool-v1"
                        )
                        if tool_protocol:
                            sending = await self.repository.inputs(
                                owner, run_id, statuses=("sending",)
                            )
                            await self._reconcile_inputs(run, token, codex, sending)
                            run = await self.repository.get(owner, run_id)
                            if await self.repository.inputs(
                                owner, run_id, statuses=("pending",)
                            ):
                                await self._next_input(run, token)
                                continue
                        try:
                            if tool_protocol:
                                result = await self.repository.result_for_turn(
                                    owner, run_id, token
                                )
                                if result is None:
                                    raise ValueError(
                                        "No current build result submitted"
                                    )
                                completion = CompletionContract(**result)
                            else:
                                completion = await read_completion_contract(
                                    transport, str(run.checkpoint["completion_path"])
                                )
                            if not completion.answered and (
                                not completion.intent_summary
                                or not completion.acceptance_criteria
                            ):
                                raise ValueError("Incomplete delivery context")
                        except (ValueError, FileNotFoundError):
                            if await self._continue_turn(
                                run,
                                token,
                                report_only=tool_protocol,
                                force=bool(run.checkpoint.get("manual_resume")),
                            ):
                                continue
                            raise

                        def public(text: str) -> str:
                            for secret in lease.exact_secrets:
                                if secret:
                                    text = text.replace(secret, "***")
                            return redact_sandbox_text(text)

                        completion = replace(
                            completion,
                            summary=public(completion.summary),
                            intent_summary=public(completion.intent_summary),
                            acceptance_criteria=tuple(
                                public(item) for item in completion.acceptance_criteria
                            ),
                        )
                        await self.repository.checkpoint(
                            owner,
                            run_id,
                            token,
                            completion=asdict(completion),
                            completion_revision=int(
                                run.checkpoint.get("accepted_revision", 1)
                            ),
                        )
                        await self.repository.update(
                            owner,
                            run_id,
                            token,
                            phase="delivery"
                            if not completion.answered
                            else "cycle_complete",
                            state_message="正在整理产物"
                            if not completion.answered
                            else "正在完成请求",
                        )
                    run = await self.repository.get(owner, run_id)
                    await self._check_stop(run)
                    if run.phase in {"delivery", "version"}:
                        if run.checkpoint.get(
                            "result_protocol"
                        ) == "tool-v1" and not await self.repository.revision_current(
                            owner,
                            run_id,
                            token,
                            int(run.checkpoint["completion_revision"]),
                        ):
                            await self._next_input(run, token)
                            continue
                        await self._deliver(run, token, transport, lease, root)
                    run = await self.repository.get(owner, run_id)
                    await self._check_stop(run)
                    if run.phase == "cycle_complete":
                        sending = await self.repository.inputs(
                            owner, run_id, statuses=("sending",)
                        )
                        if sending:
                            await self._reconcile_inputs(run, token, codex, sending)
                        # Input may arrive during cleanup. finish() atomically detects it.
                        if run.checkpoint.get("completion_path"):
                            await remove_completion_file(
                                transport, str(run.checkpoint["completion_path"])
                            )
                        await lease.cleanup()
                        logger.info(
                            "Development lifecycle run_id=%s session_id=%s thread_id=%s reason=task_cleanup_completed",
                            run_id,
                            run.session_id,
                            run.thread_id,
                        )
                        await self.repository.checkpoint(
                            owner, run_id, token, lease_ready=False
                        )
                        run = await self.repository.get(owner, run_id)
                        await self._check_stop(run)
                        revision = int(run.checkpoint.get("accepted_revision", 1))
                        if (
                            run.checkpoint.get("result_protocol") != "tool-v1"
                            and run.checkpoint.get("version")
                            and not run.checkpoint.get("delivery_emitted")
                        ):
                            delivery_view = run.checkpoint["version"]
                            await self.repository.append_event(
                                owner,
                                run_id,
                                token,
                                "development.succeeded"
                                if delivery_view.get("verified")
                                else "development.source_ready",
                                {
                                    "payload": {"delivery": delivery_view},
                                    "inputRevision": revision,
                                },
                            )
                            await self.repository.checkpoint(
                                owner, run_id, token, delivery_emitted=True
                            )
                        if await self.repository.finish(owner, run_id, token, revision):
                            return
                        run = await self.repository.get(owner, run_id)
                        await self._check_stop(run)
                        await self._next_input(run, token)

            work = asyncio.create_task(drive())
            done, _ = await asyncio.wait(
                {work, controller}, return_when=asyncio.FIRST_COMPLETED
            )
            if controller in done:
                await controller
                raise RuntimeError("Task controller stopped unexpectedly")
            await work
        except StopRequested:
            run = await self.repository.get(owner, run_id)
            await self._confirm_stop(run, token, codex)
            if run.checkpoint.get("completion_path"):
                await remove_completion_file(
                    transport, str(run.checkpoint["completion_path"])
                )
            await lease.cleanup()
            await self.repository.update(
                owner,
                run_id,
                token,
                state="cancelled",
                phase="complete",
                state_message="任务已停止，已有输出和修改已保留。",
            )
        finally:
            tasks = [task for task in (controller, work) if task is not None]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await codex.close()

    @staticmethod
    async def _check_stop(run: Run) -> None:
        if run.stop_requested:
            raise StopRequested

    async def _submit_result(
        self,
        owner: str,
        run_id: str,
        token: str,
        params: dict[str, Any],
        lease: TaskCredentialLease,
    ) -> dict[str, Any]:
        try:
            arguments = params.get("arguments")
            encoded = json.dumps(arguments, sort_keys=True, allow_nan=False).encode()
            if len(encoded) > 65_536:
                raise ValueError("Result exceeds the size limit.")
            revision, completion = parse_build_result(arguments)
            # turn/start and replayed requests can arrive before the stream
            # consumer commits its turn association. Never derive it from a tool.
            for _ in range(40):
                run = await self.repository.get(owner, run_id)
                if run.turn_id or run.stop_requested or run.terminal:
                    break
                await asyncio.sleep(0.05)

            def public(value: str) -> str:
                for secret in lease.exact_secrets:
                    if secret:
                        value = value.replace(secret, "***")
                return redact_sandbox_text(value)

            completion = replace(
                completion,
                summary=public(completion.summary),
                intent_summary=public(completion.intent_summary),
                acceptance_criteria=tuple(
                    public(item) for item in completion.acceptance_criteria
                ),
            )
            response = {
                "success": True,
                "contentItems": [
                    {
                        "type": "inputText",
                        "text": f"Result saved for input revision {revision}. Finish this turn with your user-facing summary. Do not modify deliverable files after submitting. If new requirements arrive, apply them and resubmit.",
                    }
                ],
            }
            return await self.repository.submit_result(
                owner,
                run_id,
                token,
                thread_id=params["threadId"],
                turn_id=params["turnId"],
                call_id=params["callId"],
                revision=revision,
                digest=hashlib.sha256(encoded).hexdigest(),
                completion=asdict(completion),
                response=response,
            )
        except (ValueError, RunConflict) as error:
            return {
                "success": False,
                "contentItems": [{"type": "inputText", "text": str(error)}],
            }

    async def _next_input(self, run: Run, token: str) -> None:
        await self.repository.update(
            run.owner_id,
            run.id,
            token,
            checkpoint_updates={
                "completion": None,
                "completion_revision": None,
                "delivery": None,
                "version": None,
                "completion_path": "",
                "publish_time": "",
                "shell_root": "",
                "delivery_emitted": False,
                "continuation": None,
                "continuation_sending": False,
                "continuation_count": 0,
                "report_only": False,
                "report_count": 0,
                "manual_resume": False,
            },
            phase="prepare",
            turn_id="",
            state_message="正在处理最新要求",
        )

    async def _coding(
        self,
        run: Run,
        token: str,
        codex: CodexAppServerSession,
        lease: TaskCredentialLease,
        cloud: SandboxCloudSession,
        root: str,
    ) -> None:
        owner, run_id = run.owner_id, run.id
        inputs = await self.repository.inputs(owner, run_id)
        resume_id = run.turn_id if run.phase in {"coding", "reporting"} else ""
        if resume_id and run.checkpoint.get("manual_resume"):
            turn = await codex.read_turn(resume_id)
            if turn and turn.get("status") in {"failed", "interrupted"}:
                await self.repository.checkpoint(
                    owner, run_id, token, manual_resume=False
                )
                pending = await self.repository.inputs(
                    owner, run_id, statuses=("pending",)
                )
                if pending:
                    await self._next_input(run, token)
                else:
                    await self._continue_turn(
                        run,
                        token,
                        force=True,
                        report_only=bool(run.checkpoint.get("report_only")),
                    )
                return
        continuation = run.checkpoint.get("continuation")
        report_only = bool(run.checkpoint.get("report_only"))
        tool_protocol = run.checkpoint.get("result_protocol") == "tool-v1"
        current = (
            None
            if resume_id or continuation
            else next(
                (item for item in inputs if item["status"] in {"sending", "pending"}),
                None,
            )
        )
        if not resume_id and current is not None and current["status"] == "sending":
            found = await codex.find_input_turn(current["client_id"])
            if found is None:
                raise InputUnconfirmed
            resume_id = str(found["id"])
        if continuation and not resume_id:
            current = None
            if run.checkpoint.get("continuation_sending"):
                found = await codex.find_input_turn(str(continuation))
                if found is None:
                    raise InputUnconfirmed
                resume_id = str(found["id"])
        if not resume_id and current is None and not continuation:
            raise InputUnconfirmed
        revision = (
            current["revision"]
            if current
            else int(run.checkpoint.get("accepted_revision", 1))
        )
        completion_path = (
            ""
            if tool_protocol
            else str(
                run.checkpoint.get("completion_path")
                or f"{root}/{COMPLETION_FILE_PREFIX}{run_id}-{revision}.json"
            )
        )
        await self.repository.checkpoint(
            owner, run_id, token, completion_path=completion_path
        )
        await self.repository.update(
            owner,
            run_id,
            token,
            state="running",
            phase="reporting" if report_only else "coding",
            state_message="正在补齐交付信息" if report_only else "正在处理请求",
        )
        prompt = ""
        client_id = ""
        text_projection = TaskTextProjection(lease.exact_secrets)
        thinking_projection = TaskTextProjection(lease.exact_secrets)
        tool_projection = TaskTextProjection(lease.exact_secrets)
        if not resume_id:
            if continuation:
                client_id = str(continuation)
                await self.repository.checkpoint(
                    owner, run_id, token, continuation_sending=True
                )
                message = (
                    "继续完成当前对话中尚未完成的要求。先检查工作区、已有验证结果和远端资源，"
                    "避免重复已成功的操作；完成后写入本轮结果文件。"
                )
            else:
                assert current is not None
                client_id = current["client_id"]
                await self.repository.input_status(
                    owner, run_id, token, client_id, "sending"
                )
                message = current["message"]
            prompt = (
                result_reporting_prompt(
                    revision,
                    [
                        item["message"]
                        for item in inputs
                        if item["status"] == "delivered"
                    ],
                    await self._project_context(run),
                )
                if report_only
                else builder_prompt(
                    message,
                    launcher_path=lease.launcher_path,
                    completion_path=completion_path,
                    expire_at=cloud.expire_at,
                    remaining_lifetime_minutes=max(
                        1,
                        int(
                            (
                                datetime.fromisoformat(
                                    cloud.expire_at.replace("Z", "+00:00")
                                )
                                - datetime.now(timezone.utc)
                            ).total_seconds()
                            / 60
                        ),
                    )
                    if cloud.expire_at
                    else 480,
                    validation_region=self.validation_region,
                    validation_project=self.validation_project,
                    project_context=await self._project_context(run),
                    input_revision=revision if tool_protocol else None,
                )
            )
        try:
            async for event in codex.stream_turn(
                prompt,
                permissions=_REPORT_PERMISSIONS if report_only else _PERMISSIONS,
                timeout_seconds=120 if report_only else 3300,
                client_user_message_id=client_id,
                resume_turn_id=resume_id,
                interrupt_on_cancel=False,
                output_schema=None,
            ):
                if event.kind == "thread_ready":
                    await self._check_stop(await self.repository.get(owner, run_id))
                    await self.repository.update(
                        owner, run_id, token, thread_id=codex.thread_id
                    )
                elif event.kind == "turn_started":
                    await self.repository.update(
                        owner,
                        run_id,
                        token,
                        thread_id=codex.thread_id,
                        turn_id=event.turn_id,
                    )
                    if current is not None:
                        await self.repository.input_status(
                            owner,
                            run_id,
                            token,
                            current["client_id"],
                            "delivered",
                            turn_id=event.turn_id,
                        )
                        await self.repository.checkpoint(
                            owner, run_id, token, accepted_revision=revision
                        )
                    await self.repository.record_turn(
                        owner,
                        run_id,
                        token,
                        thread_id=codex.thread_id,
                        turn_id=event.turn_id,
                        revision=revision,
                        status="inProgress",
                        metrics={
                            **(
                                event.response
                                if isinstance(event.response, dict)
                                else {}
                            ),
                            "resumed": bool(resume_id),
                        },
                    )
                elif event.kind in {"turn_completed", "usage"}:
                    metrics = event.response if isinstance(event.response, dict) else {}
                    if event.usage is not None:
                        metrics = {
                            **metrics,
                            "usage": event.usage.public_dict(),
                            "threadTotal": event.thread_total.public_dict()
                            if event.thread_total
                            else None,
                        }
                    await self.repository.record_turn(
                        owner,
                        run_id,
                        token,
                        thread_id=codex.thread_id,
                        turn_id=event.turn_id or codex.active_turn_id,
                        revision=revision,
                        status=event.status
                        if event.kind == "turn_completed"
                        else "inProgress",
                        metrics=metrics,
                    )
                    if event.kind == "usage":
                        projected = self.render_event(event, lease)
                        if projected is not None:
                            kind, payload = projected
                            await self.repository.append_event(
                                owner,
                                run_id,
                                token,
                                kind,
                                {**payload, "turnId": event.turn_id},
                            )
                elif event.kind == "user_input":
                    response = (
                        event.response if isinstance(event.response, dict) else {}
                    )
                    client = response.get("clientId")
                    match = next(
                        (
                            item
                            for item in await self.repository.inputs(owner, run_id)
                            if item["client_id"] == client
                        ),
                        None,
                    )
                    if match:
                        await self.repository.input_status(
                            owner,
                            run_id,
                            token,
                            match["client_id"],
                            "delivered",
                            turn_id=event.turn_id,
                        )
                        await self.repository.checkpoint(
                            owner, run_id, token, accepted_revision=match["revision"]
                        )
                else:
                    if event.kind in {
                        "text",
                        "text_snapshot",
                        "assistant_final",
                        "commentary",
                    }:
                        event = text_projection.apply(
                            event, event.turn_id or codex.active_turn_id
                        )
                    elif event.kind == "thinking":
                        event = thinking_projection.apply(
                            event,
                            event.turn_id or codex.active_turn_id,
                            snapshot_only=True,
                        )
                    elif event.kind == "tool_output":
                        event = tool_projection.apply(
                            event, event.turn_id or codex.active_turn_id
                        )
                    projected = self.render_event(event, lease)
                    progress = self.command_progress(event)
                    if progress:
                        await self.repository.append_event(
                            owner, run_id, token, "progress", {"text": progress}
                        )
                    if projected is not None:
                        kind, payload = projected
                        payload["turnId"] = event.turn_id or codex.active_turn_id
                        await self.repository.append_event(
                            owner, run_id, token, kind, payload
                        )
        except (RunLeaseLost, RunCapacity):
            raise
        except Exception:
            latest = await self.repository.get(owner, run_id)
            if latest.stop_requested:
                await self._confirm_stop(latest, token, codex)
                raise StopRequested
            if latest.turn_id:
                turn = await codex.read_turn(latest.turn_id)
                if turn and turn.get("status") in {"failed", "interrupted"}:
                    await self.repository.record_turn(
                        owner,
                        run_id,
                        token,
                        thread_id=codex.thread_id,
                        turn_id=latest.turn_id,
                        revision=revision,
                        status=str(turn["status"]),
                        metrics=turn,
                    )
                    failure = turn.get("error") or {}
                    info = (
                        failure.get("codexErrorInfo")
                        if isinstance(failure, dict)
                        else None
                    )
                    code = next(iter(info), "") if isinstance(info, dict) else info
                    transient = turn.get("status") == "interrupted" or code in {
                        "serverOverloaded",
                        "rateLimitExceeded",
                        "internalServerError",
                        "httpConnectionFailed",
                        "responseStreamConnectionFailed",
                        "responseStreamDisconnected",
                        "responseTooManyFailedAttempts",
                    }
                    if transient:
                        sending = await self.repository.inputs(
                            owner, run_id, statuses=("sending",)
                        )
                        await self._reconcile_inputs(latest, token, codex, sending)
                        if await self._continue_turn(
                            latest, token, report_only=report_only
                        ):
                            return
                    raise NativeTurnFailed from None
            raise
        latest = await self.repository.get(owner, run_id)
        await self._check_stop(latest)
        for event in text_projection.finish(latest.turn_id):
            projected = self.render_event(event, lease)
            if projected is not None:
                kind, payload = projected
                await self.repository.append_event(
                    owner, run_id, token, kind, {**payload, "turnId": latest.turn_id}
                )
        await self.repository.record_turn(
            owner,
            run_id,
            token,
            thread_id=codex.thread_id,
            turn_id=latest.turn_id,
            revision=int(latest.checkpoint.get("accepted_revision", revision)),
            status="completed",
        )
        await self.repository.checkpoint(
            owner, run_id, token, continuation=None, continuation_sending=False
        )
        await self.repository.update(
            owner, run_id, token, phase="outcome_read", state_message="正在整理产物"
        )

    async def _continue_turn(
        self, run: Run, token: str, *, force: bool = False, report_only: bool = False
    ) -> bool:
        counter = "report_count" if report_only else "continuation_count"
        count = int(run.checkpoint.get(counter, 0))
        if count >= (1 if report_only else 2) and not force:
            return False
        # Only called after an authoritative terminal turn, never after an
        # ambiguous start. Continuations inspect existing effects in the same thread.
        await self.repository.update(
            run.owner_id,
            run.id,
            token,
            checkpoint_updates={
                "continuation": f"{run.id}-{'report' if report_only else 'recover'}-{run.input_revision}-{count + 1}",
                counter: count + 1,
                "report_only": report_only,
                "report_deadline": self.repository.clock() + 120
                if report_only
                else None,
                "continuation_sending": False,
                "manual_resume": False,
            },
            phase="reporting" if report_only else "prepare",
            turn_id="",
            state="recovering",
            state_message="正在补齐交付信息"
            if report_only
            else "Codex 本轮执行已结束，正在继续未完成的工作。",
        )
        return True

    async def _project_context(self, run: Run) -> str:
        if self.project_service is None:
            return ""
        import json

        try:
            await self.project_service.get_binding(run.owner_id, run.session_id)
        except IntelligentDevelopmentProjectNotFound:
            await self.project_service.create_binding(
                owner_id=run.owner_id,
                session_id=run.session_id,
                display_name=run.message[:80],
            )
        base = await self.project_service.base_metadata(run.owner_id, run.session_id)
        if base is None:
            return ""
        return json.dumps(
            {
                "intentSummary": base.intent_summary,
                "acceptanceCriteria": base.acceptance_criteria,
                "agentName": base.agent_name,
                "entryPoint": base.entry_point,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    async def _deliver(
        self,
        run: Run,
        token: str,
        transport: SandboxRemoteTransport,
        lease: TaskCredentialLease,
        root: str,
    ) -> None:
        owner, run_id = run.owner_id, run.id
        completion = CompletionContract(**run.checkpoint["completion"])
        revision = int(run.checkpoint.get("accepted_revision", 1))
        delivery_id = hashlib.sha256(f"{run_id}:{revision}".encode()).hexdigest()[:32]
        publish_time = str(
            run.checkpoint.get("publish_time") or datetime.now(timezone.utc).isoformat()
        )
        if run.phase == "delivery":
            shell_root = f"{lease.root}/command-{delivery_id}"
            await self.repository.checkpoint(
                owner, run_id, token, publish_time=publish_time, shell_root=shell_root
            )
            shell = RunShell(self.repository, run, token, transport, shell_root)
            metadata = None
            if self.project_service is not None:
                base = await self.project_service.base_metadata(owner, run.session_id)
                if base is not None:
                    metadata = (base.agent_name, base.entry_point)
            await invalidate_current_delivery(transport)
            delivery = await DeliveryPublisher(transport).publish(
                session_id=run.session_id,
                project_root=root,
                task_root=lease.root,
                completion=completion,
                exact_secrets=lease.exact_secrets,
                acceptance_criteria=tuple(completion.acceptance_criteria),
                trusted_manifest_metadata=metadata,
                delivery_id=delivery_id,
                validated_at=publish_time,
                execute_command=shell.execute,
            )
            await self.repository.checkpoint(
                owner, run_id, token, delivery=asdict(delivery)
            )
            if run.checkpoint.get("result_protocol") != "tool-v1":
                await self.repository.append_event(
                    owner,
                    run_id,
                    token,
                    "development.source_ready",
                    {
                        "payload": {
                            "delivery": {**delivery.as_dict(), "verified": False}
                        },
                        "inputRevision": revision,
                    },
                )
            await self.repository.update(
                owner,
                run_id,
                token,
                phase="version",
                state_message="正在保存版本",
            )
        else:
            delivery = DeliveryReference(**run.checkpoint["delivery"])
        run = await self.repository.get(owner, run_id)
        await self._check_stop(run)
        if run.checkpoint.get(
            "result_protocol"
        ) == "tool-v1" and not await self.repository.revision_current(
            owner, run_id, token, revision
        ):
            await self._next_input(run, token)
            return
        public = delivery.as_dict()
        if self.project_service is not None:
            decision = IntentDecision(
                "accept",
                "",
                completion.intent_summary,
                tuple(completion.acceptance_criteria),
                True,
            )
            _, version = await self.project_service.persist_delivery(
                owner_id=owner,
                session_id=run.session_id,
                transport=transport,
                delivery=delivery,
                decision=decision,
                version_id=delivery_id,
                created_at=datetime.fromisoformat(publish_time),
            )
            public.update(
                {
                    "projectId": version.project_id,
                    "versionId": version.version_id,
                    "parentVersionId": version.parent_version_id,
                }
            )
            await self.repository.checkpoint(owner, run_id, token, version=public)
        await self._check_stop(await self.repository.get(owner, run_id))
        await self.repository.checkpoint(owner, run_id, token, version=public)
        await self.repository.update(
            owner, run_id, token, phase="cycle_complete", state_message="正在完成请求"
        )

    async def _control(
        self, initial: Run, token: str, codex: CodexAppServerSession
    ) -> None:
        owner, run_id = initial.owner_id, initial.id
        renew_at = 0.0
        while True:
            await asyncio.sleep(0.3)
            run = await self.repository.get(owner, run_id)
            if run.terminal:
                return
            try:
                await self.repository.heartbeat(owner, run_id, token)
                if (
                    self.repository.clock() - run.created_at
                    >= self.repository.max_active_seconds
                ):
                    run = await self.repository.request_stop(owner, run_id)
                if run.stop_requested:
                    if run.turn_id and codex.active:
                        await codex.interrupt_turn(run.turn_id)
                    await asyncio.sleep(1)
                    continue
                if run.phase == "reporting":
                    if (
                        run.turn_id
                        and codex.active
                        and self.repository.clock()
                        >= float(run.checkpoint.get("report_deadline") or 0)
                    ):
                        await codex.interrupt_turn(run.turn_id)
                    continue
                if run.phase != "coding" or not run.turn_id:
                    continue
                if asyncio.get_running_loop().time() >= renew_at:
                    cloud = await self.resolve_session(run.session_id, owner)
                    if self.renew_session is not None:
                        cloud = await self.renew_session(cloud)
                    codex.refresh_endpoint(cloud.endpoint)
                    renew_at = asyncio.get_running_loop().time() + 60
                sending = await self.repository.inputs(
                    owner, run_id, statuses=("sending",)
                )
                if sending:
                    await self._reconcile_inputs(run, token, codex, sending)
                    continue
                pending = await self.repository.inputs(
                    owner, run_id, statuses=("pending",)
                )
                if not pending or run.checkpoint.get("steer_wait_turn") == run.turn_id:
                    continue
                item = pending[0]
                await self.repository.input_status(
                    owner,
                    run_id,
                    token,
                    item["client_id"],
                    "sending",
                    turn_id=run.turn_id,
                )
                try:
                    await codex.steer_turn(
                        (
                            f"[Studio inputRevision={item['revision']}; resubmit submit_build_result after applying these requirements]\n{item['message']}"
                            if run.checkpoint.get("result_protocol") == "tool-v1"
                            else item["message"]
                        ),
                        run.turn_id,
                        item["client_id"],
                    )
                except Exception as error:
                    # A definite precondition rejection can safely become the next turn.
                    if (
                        isinstance(error, CodexAppServerRequestError)
                        and error.code == -32600
                    ):
                        await self.repository.input_status(
                            owner, run_id, token, item["client_id"], "pending"
                        )
                        await self.repository.checkpoint(
                            owner, run_id, token, steer_wait_turn=run.turn_id
                        )
                    raise
                await self.repository.input_status(
                    owner,
                    run_id,
                    token,
                    item["client_id"],
                    "delivered",
                    turn_id=run.turn_id,
                )
                await self.repository.checkpoint(
                    owner, run_id, token, accepted_revision=item["revision"]
                )
            except (RunLeaseLost, asyncio.CancelledError):
                raise
            except Exception as error:
                logger.info(
                    "Development control pending run_id=%s error_type=%s",
                    run_id,
                    type(error).__name__,
                )
                await asyncio.sleep(2)

    async def _reconcile_inputs(
        self,
        run: Run,
        token: str,
        codex: CodexAppServerSession,
        inputs: list[dict[str, Any]],
    ) -> None:
        for item in inputs:
            found = await codex.find_input_turn(item["client_id"])
            if found is None:
                raise InputUnconfirmed
            await self.repository.input_status(
                run.owner_id,
                run.id,
                token,
                item["client_id"],
                "delivered",
                turn_id=str(found["id"]),
            )
            await self.repository.checkpoint(
                run.owner_id, run.id, token, accepted_revision=item["revision"]
            )

    async def _confirm_stop(
        self, run: Run, token: str, codex: CodexAppServerSession
    ) -> None:
        shell_root = run.checkpoint.get("shell_root")
        if (
            shell_root
            and run.phase == "delivery"
            and run.checkpoint.get(f"{str(shell_root).rsplit('/', 1)[-1]}_submitted")
        ):
            cloud = await self.resolve_session(run.session_id, run.owner_id)
            shell = RunShell(
                self.repository,
                run,
                token,
                SandboxRemoteTransport(cloud.endpoint),
                str(shell_root),
            )
            if not await shell.confirm_stopped():
                raise RuntimeError("Delivery command stop is not yet confirmed")
        turn_id = run.turn_id
        if not turn_id and run.checkpoint.get("continuation_sending"):
            found = await codex.find_input_turn(str(run.checkpoint["continuation"]))
            if found is None:
                raise RuntimeError(
                    "Cannot confirm whether the continuation was accepted"
                )
            turn_id = str(found["id"])
        if not turn_id:
            sending = await self.repository.inputs(
                run.owner_id, run.id, statuses=("sending",)
            )
            if sending:
                found = await codex.find_input_turn(sending[0]["client_id"])
                if found is None:
                    raise RuntimeError(
                        "Cannot confirm whether the initial turn was accepted"
                    )
                turn_id = str(found["id"])
        if turn_id:
            turn = await codex.read_turn(turn_id)
            if turn is None:
                raise RuntimeError("Cannot confirm the remote turn state")
            if turn.get("status") == "inProgress":
                await codex.interrupt_turn(turn_id)
                for _ in range(20):
                    await asyncio.sleep(0.5)
                    turn = await codex.read_turn(turn_id)
                    if turn is not None and turn.get("status") in {
                        "completed",
                        "failed",
                        "interrupted",
                    }:
                        await self.repository.record_turn(
                            run.owner_id,
                            run.id,
                            token,
                            thread_id=codex.thread_id,
                            turn_id=turn_id,
                            revision=run.input_revision,
                            status=str(turn["status"]),
                            metrics=turn,
                        )
                        return
                raise RuntimeError("Remote interruption is not confirmed")
            if turn.get("status") in {"completed", "failed", "interrupted"}:
                await self.repository.record_turn(
                    run.owner_id,
                    run.id,
                    token,
                    thread_id=codex.thread_id,
                    turn_id=turn_id,
                    revision=run.input_revision,
                    status=str(turn["status"]),
                    metrics=turn,
                )
