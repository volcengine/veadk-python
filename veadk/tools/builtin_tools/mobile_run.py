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

"""
Mobile Automation Tool (Mobile Use Tool)
=======================================
Purpose: Execute automated tasks on a virtual mobile device via the Volcano Engine
mobile-use service (app operations, screenshots, account actions, etc.). An Agent plans
the workflow in the background, supporting custom user instructions and system constraints.

Prerequisites:
1. Subscribe to the Cloud Phone service with your Volcano Engine account to obtain
   `product_id` and `pod_id`.
2. Required environment variables (set before running):
   - VOLCENGINE_ACCESS_KEY: Volcano Engine access key AK
   - VOLCENGINE_SECRET_KEY: Volcano Engine secret key SK
   - TOOL_MOBILE_USE_TOOL_ID: Product ID and Virtual phone Pod identifier (from the console). For complex
     tasks requiring parallel execution across multiple pods, provide multiple IDs. available in the console: https://console.volcengine.com/ACEP/)
     "业务ID" is product_id, "实例 ID" is pod_id. tool_id = {product_id}-{pod_id}.


YAML configuration format
  tool:
    mobile_use:
      tool_id:
        - product_id-pod_id
        - product_id-pod_id

  volcengine:
    access_key: xxx
    secret_key: xxx

Core usage (closure functions):
1. Initialize tool configuration (outer function, run once):
   Pass the system prompt, timeout, and other static configurations. Environment validation
   and Agent configuration are handled internally.

2. Execute specific tasks (inner function, callable multiple times):
   Pass user task instructions; the initialized configuration is reused to perform automation
   and return results.

Example code:
---------
import asyncio
from this_module import create_mobile_use_tool

# 1. Initialize the tool (static configuration, run once)
system_prompt = '''
You are a mobile testing agent. Follow these rules:
1. Strictly follow user instructions; do not add unrelated steps.
2. Avoid unauthorized access; follow the principle of least privilege.
3. Return a clear result describing whether key actions succeeded.
'''
mobile_tool = create_mobile_use_tool(
    system_prompt=system_prompt,
    timeout_seconds=300,  # 5-minute task timeout
    step_interval_seconds=3  # 3-second polling interval
)

# 2. Reuse the configuration to execute multiple tasks (asynchronous)
async def main():
    # Task 1: Open the app and take a screenshot
    result1 = await mobile_tool(
        "Open Douyin, wait for the home page to load, then capture a full-screen screenshot"
    )
    print("Task 1 result:", result1)

    # Task 2: Search and follow an account (reusing the same system prompt and timeouts)
    result2 = await mobile_tool(
        "Search 'Volcano Engine' in Douyin, find the official account, and tap Follow"
    )
    print("Task 2 result:", result2)

if __name__ == "__main__":
    asyncio.run(main())
"""

import ast
import asyncio
import os
import time
from dataclasses import dataclass
from typing import Type, TypeVar, List, Dict, Any, Callable
from queue import Queue
from threading import Lock

from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)

ak = os.getenv("VOLCENGINE_ACCESS_KEY")
sk = os.getenv("VOLCENGINE_SECRET_KEY")
tool_ids = ast.literal_eval(os.getenv("TOOL_MOBILE_USE_TOOL_ID", "[]"))
product_id = None
pod_ids = None

service_name = "ipaas"
region = "cn-north-1"
version = "2023-08-01"
host = "open.volcengineapi.com"

REQUIRED_ENV_VARS = [
    "VOLCENGINE_ACCESS_KEY",
    "VOLCENGINE_SECRET_KEY",
    "TOOL_MOBILE_USE_TOOL_ID",
]


class MobileUseToolError(Exception):
    def __init__(self, msg: str):
        self.msg = msg
        logger.error(f"mobile use tool execute error :{msg}")


@dataclass
class ResponseMetadata:
    RequestId: str
    Action: str
    Version: str
    Service: str
    Region: str


@dataclass
class RunAgentTaskResult:
    RunId: str
    RunName: str
    ThreadId: str


@dataclass
class RunAgentTaskResponse:
    ResponseMetadata: ResponseMetadata
    Result: RunAgentTaskResult


@dataclass
class GetAgentResultResult:
    IsSuccess: int
    Content: str
    StructOutput: str
    ScreenShots: List[str]


@dataclass
class GetAgentResultResponse:
    ResponseMetadata: ResponseMetadata
    Result: GetAgentResultResult


@dataclass
class StepResult:
    IsSuccess: bool
    Result: str


@dataclass
class AgentRunCurrentStepInfo:
    Action: str
    Param: dict[str, str]
    StepResult: StepResult


@dataclass
class ListAgentRunCurrentResponseResult:
    RunId: str
    ThreadId: str
    Results: List[AgentRunCurrentStepInfo]


@dataclass
class ListAgentRunCurrentResponse:
    Result: ListAgentRunCurrentResponseResult
    ResponseMetadata: ResponseMetadata


T = TypeVar("T")


def _dict_to_dataclass(data: dict, cls: Type[T]) -> T:
    field_values = {}
    for field_name, field_type in cls.__dataclass_fields__.items():
        field_value = data.get(field_name)
        if field_value is None:
            field_values[field_name] = None
            continue

        if hasattr(field_type.type, "__dataclass_fields__"):
            field_values[field_name] = _dict_to_dataclass(field_value, field_type.type)
        else:
            field_values[field_name] = field_value
    return cls(**field_values)


class PodPool:
    def __init__(self, pod_ids: List[str]):
        self.pod_ids = pod_ids
        self.available_pods = Queue()
        self.pod_lock = Lock()
        self.task_map: Dict[str, str] = {}

        for pid in pod_ids:
            self.available_pods.put(str(pid))
        logger.info(f"Pod pool initialized, available pods: {len(pod_ids)}")

    def acquire_pod(self) -> Any | None:
        try:
            pid = self.available_pods.get(block=True)
            with self.pod_lock:
                self.task_map[pid] = "pending"
            logger.debug(
                f"Acquired pod: {pid}, available pods: {self.available_pods.qsize()}"
            )
            return pid
        except Exception as e:
            logger.warning(f"Pod acquisition timeout: {e}")
            return None

    def release_pod(self, pid: str) -> None:
        with self.pod_lock:
            if pid in self.task_map:
                del self.task_map[pid]
            self.available_pods.put(pid)
        logger.debug(
            f"Released pod: {pid}, available pods: {self.available_pods.qsize()}"
        )

    def get_pod_status(self, pid: str) -> str:
        with self.pod_lock:
            return self.task_map.get(pid, "available")

    def get_available_count(self) -> int:
        return self.available_pods.qsize()


def _run_agent_task(
        system_prompt: str,
        user_prompt: str,
        pid: str,
        max_step: int,
        step_interval: int,
        timeout: int,
) -> RunAgentTaskResponse:
    try:
        run_task = ve_request(
            request_body={
                "RunName": "test-run",
                "PodId": pid,
                "ProductId": product_id,
                "SystemPrompt": system_prompt,
                "UserPrompt": user_prompt,
                "MaxStep": max_step,
                "StepInterval": step_interval,
                "Timeout": timeout,
            },
            action="RunAgentTaskOneStep",
            ak=ak,
            sk=sk,
            service=service_name,
            version=version,
            region=region,
            content_type="application/json",
            host=host,
        )
    except Exception as e:
        raise MobileUseToolError(f"RunAgentTask invocation failed: {e}") from e

    run_task_response = _dict_to_dataclass(run_task, RunAgentTaskResponse)
    if (
            not getattr(run_task_response, "Result", None)
            or not run_task_response.Result
            or not run_task_response.Result.RunId
    ):
        raise MobileUseToolError(f"RunAgentTask returned invalid result: {run_task}")
    logger.debug(f"Agent run started: {run_task_response}")
    return run_task_response


def _get_task_result(task_id: str) -> GetAgentResultResponse:
    try:
        task_result = ve_request(
            request_body={},
            query={
                "RunId": task_id,
            },
            action="GetAgentResult",
            ak=ak,
            sk=sk,
            service=service_name,
            version=version,
            region=region,
            content_type="application/json",
            host=host,
            method="GET",
        )
    except Exception as e:
        raise MobileUseToolError(f"GetAgentResult invocation failed: {e}") from e

    result = _dict_to_dataclass(task_result, GetAgentResultResponse)
    if not getattr(result, "Result", None):
        raise MobileUseToolError(
            f"GetAgentResult returned invalid result: {task_result}"
        )
    logger.debug(f"Fetched agent result: {result}")
    return result


def _get_current_step(task_id: str) -> ListAgentRunCurrentResponse:
    try:
        current_step = ve_request(
            request_body={},
            query={"RunId": task_id},
            action="ListAgentRunCurrentStep",
            ak=ak,
            sk=sk,
            service=service_name,
            version=version,
            region=region,
            content_type="application/json",
            host=host,
            method="GET",
        )
    except Exception as e:
        raise MobileUseToolError(
            f"ListAgentRunCurrentStep invocation failed: {e}"
        ) from e

    result = _dict_to_dataclass(current_step, ListAgentRunCurrentResponse)
    if not getattr(result, "Result", None):
        raise MobileUseToolError(
            f"ListAgentRunCurrentStep returned invalid result: {current_step}"
        )
    logger.debug(f"Fetched agent current step: {result}")
    return result


def _cancel_task(task_id: str) -> None:
    try:
        _ = ve_request(
            request_body={},
            query={"RunId": task_id},
            action="CancelTask",
            ak=ak,
            sk=sk,
            service=service_name,
            version=version,
            region=region,
            content_type="application/json",
            host=host,
            method="POST",
        )
        logger.debug(f"Cancelled agent task: {task_id}")
    except Exception as e:
        raise MobileUseToolError(f"CancelAgentTask invocation failed: {e}") from e


def _require_env_vars() -> None:
    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        raise MobileUseToolError(
            f"Missing required environment variables: {', '.join(missing)}"
        )


def _get_product_and_pod():
    if tool_ids is None or tool_ids.__len__() == 0:
        raise MobileUseToolError("TOOL_MOBILE_USE_TOOL_ID is None")
    global product_id
    global pod_ids
    if "-" in tool_ids[0]:
        product_id = tool_ids[0].split("-")[0]
        pod_ids = [tool_id.split("-")[1] for tool_id in tool_ids]
    else:
        raise MobileUseToolError(
            "TOOL_MOBILE_USE_TOOL_ID is invalid, please check the tool id from https://console.volcengine.com/ACEP/")


def create_mobile_use_tool(
        system_prompt: str,
        timeout_seconds: int = 900,
        max_step: int = 100,
        step_interval_seconds: int = 1,
):
    """
    Outer closure: initialize fixed configuration for the virtual mobile tool
    (system prompt, timeout/polling parameters). Returns an inner tool
    function that reuses the configuration to execute multiple user tasks.

    Args:
        system_prompt (str):
            System-level instruction defining the agent role, behavior rules,
            constraints, and security boundaries.
            Example:
              * "You are a mobile testing agent. Follow least-privilege principles and avoid unauthorized access."
        max_step (int): Maximum execution steps per agent.
        timeout_seconds (int):
            Maximum wait time in seconds. Raises if not finished. Default: 600.
        step_interval_seconds (int):
            Status polling interval in seconds. Default: 1.

    Returns:
        Callable[[str], str]: Inner tool function that accepts user prompts to
        perform tasks and returns results.
    """
    _require_env_vars()
    _get_product_and_pod()
    pod_pool = PodPool(pod_ids)

    async def mobile_use_tool(user_prompts: List[str]) -> list[None]:
        """
        Virtual mobile execution tool. Use this when tasks require a mobile
        device. The argument is a list of task prompts; each task is a string
        describing the required operation.
        If a task must run on a single device, pass a single-element list.
            Example: ["Download and install WeChat"]
        If a task can be split into subtasks across devices, pass each subtask
        as an element.
            Example: ["Search DeepSeek status", "Search Qianwen status"]

        Args:
            user_prompts: Task list; multiple sandbox devices exist in the system.

        Returns:
            List of results, aligned with the input order.
        """
        logger.info(
            f"Processing task list, total {len(user_prompts)} tasks, available pods: {pod_pool.get_available_count()}"
        )

        results = [None] * len(user_prompts)
        coroutines = []

        def task_worker(index: int, prompt: str) -> Callable:
            wait_start = time.time()

            async def run():
                nonlocal results
                pod_id = None
                try:
                    while True:
                        pod_id = pod_pool.acquire_pod()
                        if pod_id:
                            break
                        if time.time() - wait_start >= timeout_seconds:
                            raise MobileUseToolError(
                                f"Task {index} timed out acquiring pod after {timeout_seconds}s"
                            )
                        logger.debug(
                            f"Task {index} waiting for pod, available pods: {pod_pool.get_available_count()}"
                        )
                        await asyncio.sleep(1)

                    logger.info(
                        f"Task {index} assigned to pod: {pod_id}, starting: {prompt}"
                    )
                    task_response = _run_agent_task(
                        system_prompt,
                        prompt,
                        pod_id,
                        max_step,
                        step_interval_seconds,
                        timeout_seconds,
                    )
                    task_id = task_response.Result.RunId
                    pod_pool.task_map[pod_id] = task_id

                    while True:
                        result_response = _get_task_result(task_id)
                        if result_response.Result.IsSuccess == 1:
                            results[index] = (
                                f"task success: {result_response.Result.Content}\n"
                            )
                            logger.info(
                                f"Task {index} succeeded on pod: {pod_id}, result: {result_response.Result.Content}"
                            )
                            break
                        elif result_response.Result.IsSuccess == 2:
                            results[index] = (
                                f"task failed: {result_response.Result.Content}"
                            )
                            logger.error(f"Task {index} failed on pod: {pod_id}")
                            break

                        current_step = _get_current_step(task_id)
                        if current_step.Result.Results:
                            last_step = current_step.Result.Results[-1]
                            logger.debug(
                                f"Task {index}, thread_id={task_response.Result.ThreadId}, run_id={task_id}. Current step: {last_step['Action']}, status: {'success' if last_step['StepResult']['IsSuccess'] else 'failed'}"
                            )
                        await asyncio.sleep(5)

                except Exception as e:
                    error_msg = f"Task {index} raised exception: {str(e)}"
                    results[index] = error_msg
                    logger.error(error_msg)
                finally:
                    if pod_id:
                        _cancel_task(pod_pool.task_map[pod_id])
                        pod_pool.release_pod(pod_id)

            return run

        for i, prompt in enumerate(user_prompts):
            coroutines.append(task_worker(i, prompt)())

        # 并发执行所有任务
        await asyncio.gather(*coroutines)
        return results

    return mobile_use_tool
