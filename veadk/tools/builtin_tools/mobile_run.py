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
虚拟手机自动化工具（Mobile Use Tool）
====================================
功能：通过火山引擎 mobile-use 服务，在虚拟手机上执行自动化任务（APP操作、截图、账号操作等），
      后台由 Agent 自动规划任务流程，支持自定义用户指令和系统约束。

前置要求：
1. 使用火山账号订购云手机服务，获取product_id、pod_id
2. 环境变量配置（必需，运行前需手动设置）：
   - VOLCENGINE_ACCESS_KEY: 火山引擎访问密钥 AK（需具备 IPAAS + TOS 操作权限）
   - VOLCENGINE_SECRET_KEY: 火山引擎访问密钥 SK
   - TOOL_MOBILE_USE_TOS_BUCKET: 任务结果（如截图）存储的 TOS 桶名
   - TOOL_MOBILE_USE_TOS_ENDPOINT: TOS 服务端点（示例：tos-cn-north-1.volces.com）
   - TOOL_MOBILE_USE_TOS_REGION: TOS 地域（需与端点一致，示例：cn-north-1）
   - TOOL_MOBILE_USE_POD_ID: 虚拟手机 Pod 唯一标识（从火山引擎控制台获取），如果希望复杂任务多个pod并行执行，则传入多个
   - TOOL_MOBILE_USE_PRODUCT_ID: 产品 ID（关联虚拟手机资源池，从控制台获取）

  yaml文件配置格式
   tool:
      mobile_use:
        product_id: xxxx
        pod_id:
            - xxxx
            - xxxx
        tos_bucket: xxx
        tos_region: xxx
        tos_endpoint: xxx
   volcengine:
      access_key: xxx
      secret_key: xxx

核心用法（闭包函数）：
1. 初始化工具配置（外层函数，仅需执行1次）：
   传入系统提示、超时时间等固定配置，内部自动完成环境变量校验和 Agent 配置创建。

2. 执行具体任务（内层函数，可多次调用）：
   传入用户任务指令，复用初始化的配置执行自动化操作，返回任务结果。

示例代码：
---------
import asyncio
from this_module import create_mobile_use_tool

# 1. 初始化工具（固定配置，只执行1次）
system_prompt = '''
你是移动测试Agent，遵循以下规则：
1. 严格按照用户指令执行操作，不额外添加无关步骤；
2. 操作过程中避免未授权访问，遵循最小权限原则；
3. 执行完成后返回清晰的结果描述，包含关键操作是否成功。
'''
mobile_tool = create_mobile_use_tool(
    system_prompt=system_prompt,
    timeout_seconds=300,  # 任务超时时间：5分钟
    step_interval_seconds=3  # 状态查询间隔：3秒
)

# 2. 复用配置执行多个任务（异步调用）
async def main():
    # 任务1：打开APP并截图
    result1 = await mobile_tool("打开「抖音」APP，等待首页加载完成后截取全屏")
    print("任务1结果：", result1)

    # 任务2：搜索并关注账号（复用同一套系统提示和超时配置）
    result2 = await mobile_tool("在抖音搜索「火山引擎」，找到官方账号并点击关注")
    print("任务2结果：", result2)

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
tos_bucket = os.getenv("TOOL_MOBILE_USE_TOS_BUCKET")
tos_endpoint = os.getenv("TOOL_MOBILE_USE_TOS_ENDPOINT")
tos_region = os.getenv("TOOL_MOBILE_USE_TOS_REGION")
pod_ids = ast.literal_eval(os.getenv("TOOL_MOBILE_USE_POD_ID", "[]"))
product_id = os.getenv("TOOL_MOBILE_USE_PRODUCT_ID")

# 接口固定参数，不需要修改
service_name = "ipaas"
region = "cn-north-1"
version = "2023-08-01"
host = "open.volcengineapi.com"

REQUIRED_ENV_VARS = [
    "VOLCENGINE_ACCESS_KEY",
    "VOLCENGINE_SECRET_KEY",
    "TOOL_MOBILE_USE_TOS_BUCKET",
    "TOOL_MOBILE_USE_TOS_ENDPOINT",
    "TOOL_MOBILE_USE_TOS_REGION",
    "TOOL_MOBILE_USE_POD_ID",
    "TOOL_MOBILE_USE_PRODUCT_ID",
]


class MobileUseToolError(Exception):
    """在工具执行异常时抛出，用于提示代理重新决策。"""

    def __init__(self, msg: str):
        self.msg = msg
        logger.error(f"mobile use tool execute error :{msg}")


def _require_env_vars() -> None:
    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        raise MobileUseToolError(f"缺少必要的环境变量: {', '.join(missing)}")


@dataclass
class ResponseMetadata:
    RequestId: str  # 请求唯一ID
    Action: str  # 接口动作
    Version: str  # 接口版本
    Service: str  # 服务名称
    Region: str  # 地域


@dataclass
class RunAgentTaskResult:
    RunId: str  # 运行ID（字符串类型）
    RunName: str  # 运行名称（字符串类型）
    ThreadId: str  # 线程ID（字符串类型）


@dataclass
class RunAgentTaskResponse:
    ResponseMetadata: ResponseMetadata  # 公共元数据
    Result: RunAgentTaskResult  # 该接口专属结果


@dataclass
class GetAgentResultResult:
    IsSuccess: int  # 执行是否成功（1=成功，2=失败）
    Content: str  # 执行结果描述（字符串类型）
    StructOutput: str
    ScreenShots: List[str]


@dataclass
class GetAgentResultResponse:
    ResponseMetadata: ResponseMetadata  # 公共元数据
    Result: GetAgentResultResult  # 该接口专属结果


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
        # 从字典中获取字段值（容错：字段不存在或为 None 时不报错）
        field_value = data.get(field_name)
        if field_value is None:
            field_values[field_name] = None
            continue

        # 递归处理嵌套 dataclass
        if hasattr(field_type.type, "__dataclass_fields__"):
            field_values[field_name] = _dict_to_dataclass(field_value, field_type.type)
        else:
            field_values[field_name] = field_value
    return cls(**field_values)


class PodPool:
    """Pod池管理类，负责pod的分配、释放和状态管理"""

    def __init__(self, pod_ids: List[str]):
        self.pod_ids = pod_ids
        self.available_pods = Queue()
        self.pod_lock = Lock()
        self.task_map: Dict[str, str] = {}

        for pid in pod_ids:
            self.available_pods.put(str(pid))
        logger.info(f"初始化Pod池完成，可用pod数量: {len(pod_ids)}")

    def acquire_pod(self) -> Any | None:
        """获取一个可用pod，超时返回None"""
        try:
            # 从队列获取pod，支持超时等待
            pid = self.available_pods.get(block=True)
            with self.pod_lock:
                self.task_map[pid] = "pending"  # 标记为待分配任务
            logger.debug(
                f"成功获取pod: {pid}，当前可用pod数量: {self.available_pods.qsize()}"
            )
            return pid
        except Exception as e:
            logger.warning(f"获取pod超时: {e}")
            return None

    def release_pod(self, pid: str) -> None:
        """释放pod，使其可重新被分配"""
        with self.pod_lock:
            if pid in self.task_map:
                del self.task_map[pid]
            self.available_pods.put(pid)
        logger.debug(f"释放pod: {pid}，当前可用pod数量: {self.available_pods.qsize()}")

    def get_pod_status(self, pid: str) -> str:
        """获取pod当前状态"""
        with self.pod_lock:
            return self.task_map.get(pid, "available")

    def get_available_count(self) -> int:
        """获取当前可用pod数量"""
        return self.available_pods.qsize()


def _run_agent_task(system_prompt: str, user_prompt: str, pid: str, max_step: int, step_interval: int,
                    timeout: int) -> RunAgentTaskResponse:
    try:
        run_task = ve_request(
            request_body={
                "RunName": "test-run",
                "PodId": pid,
                "ProductId": product_id,
                "SystemPrompt": system_prompt,
                "UserPrompt": user_prompt,
                "EndpointId": tos_endpoint,
                "MaxStep": max_step,
                "StepInterval": step_interval,
                "Timeout": timeout
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
        raise MobileUseToolError(f"RunAgentTask 调用失败: {e}") from e

    run_task_response = _dict_to_dataclass(run_task, RunAgentTaskResponse)
    if (
            not getattr(run_task_response, "Result", None)
            or not run_task_response.Result
            or not run_task_response.Result.RunId
    ):
        raise MobileUseToolError(f"RunAgentTask 返回无效结果: {run_task}")
    logger.debug(f"启动 Agent 运行成功：{run_task_response}")
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
        raise MobileUseToolError(f"GetAgentResult 调用失败: {e}") from e

    result = _dict_to_dataclass(task_result, GetAgentResultResponse)
    if not getattr(result, "Result", None):
        raise MobileUseToolError(f"GetAgentResult 返回无效结果: {task_result}")
    logger.debug(f"获取 Agent 结果：{result}")
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
        raise MobileUseToolError(f"ListAgentRunCurrentStep 调用失败: {e}") from e

    result = _dict_to_dataclass(current_step, ListAgentRunCurrentResponse)
    if not getattr(result, "Result", None):
        raise MobileUseToolError(f"GetAgentResult 返回无效结果: {current_step}")
    logger.debug(f"获取 Agent 当前步骤：{result}")
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
        logger.debug(f"取消 Agent 任务成功：{task_id}")
    except Exception as e:
        raise MobileUseToolError(f"CancelAgentTask 调用失败: {e}") from e


def create_mobile_use_tool(
        system_prompt: str,
        timeout_seconds: int = 900,
        max_step: int = 100,
        step_interval_seconds: int = 1,
):
    """
    闭包外层函数：初始化虚拟手机工具的固定配置（系统提示、超时/轮询参数）
    调用后返回内层工具函数，可复用配置执行多个用户任务

    Args:
        system_prompt (str):
            系统级指令，定义Agent的角色、行为规范、约束条件和安全边界。
            示例：
              * "You are a mobile testing agent. Follow least-privilege principles and avoid unauthorized access."
        max_step (int): 每个agent最大执行步骤数
        timeout_seconds (int):
            最大等待时间（秒），超时未完成则抛出异常。默认：600。
        step_interval_seconds (int):
            状态查询间隔（秒）。默认：1。

    Returns:
        Callable[[str], str]: 内层工具函数，接收 user_prompt 执行具体任务并返回结果
    """
    # 初始化pod池
    _require_env_vars()
    pod_pool = PodPool(pod_ids)

    async def mobile_use_tool(user_prompts: List[str]) -> list[None]:
        """
        虚拟手机执行任务工具。当需要使用手机完成某些任务的时候，可以使用此工具。
        参数是一个任务列表，每个任务都是一个字符串，描述了需要手机完成的任务。
        如果任务需要独立在一个手机上完成，则参数数组中之后一个元素。
            例子： 下载并安装微信。 参数["下载并安装微信"]
        如果任务可以拆分成多个子任务，每个子任务可以在不同的手机上完成，则参数数组中每个元素都是一个子任务列表。
            例子： 搜索deepseek和千问查看最新的动态。 参数[["搜索deepseek查看状态"], ["搜索千问查看状态"]]

        Args:
            user_prompts: 任务列表，系统中存在多个手机的沙箱环境。

        Returns:
            任务结果列表，与输入顺序一致
        """
        logger.info(
            f"开始处理任务列表，共{len(user_prompts)}个任务，可用pod数量: {pod_pool.get_available_count()}"
        )

        # 存储任务结果（保持输入顺序）
        results = [None] * len(user_prompts)
        # 并发执行任务的协程列表
        coroutines = []

        def task_worker(index: int, prompt: str) -> Callable:
            """任务工作函数，封装单个任务的执行逻辑"""
            # 1. 获取可用pod（最多等待总超时时间）
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
                                f"任务{index}获取pod超时，超过{timeout_seconds}s"
                            )
                        logger.debug(
                            f"任务{index}等待pod中，当前可用pod数量: {pod_pool.get_available_count()}"
                        )
                        await asyncio.sleep(1)  # 等待1秒后重试

                    # 2. 执行任务
                    logger.info(f"任务{index}分配到pod: {pod_id}，开始执行: {prompt}")
                    task_response = _run_agent_task(system_prompt, prompt, pod_id, max_step, step_interval_seconds, timeout_seconds)
                    task_id = task_response.Result.RunId

                    # 3. 轮询任务结果
                    while True:
                        result_response = _get_task_result(task_id)
                        if result_response.Result.IsSuccess == 1:
                            # 任务成功
                            results[index] = (
                                f"任务执行成功: {result_response.Result.Content}\n"
                            )
                            logger.info(
                                f"任务{index}执行成功, pod: {pod_id}），结果为{result_response.Result.Content}"
                            )
                            break
                        elif result_response.Result.IsSuccess == 2:
                            # 任务失败
                            results[index] = (
                                f"任务执行失败: {result_response.Result.Content}"
                            )
                            logger.error(f"任务{index}执行失败（pod: {pod_id}）")
                            break

                        # 打印当前步骤信息
                        current_step = _get_current_step(task_id)
                        if current_step.Result.Results:
                            last_step = current_step.Result.Results[-1]
                            logger.debug(
                                f"任务{index}，thread_id={task_response.Result.ThreadId}, run_id={task_id}.当前步骤: {last_step['Action']}，状态: {'成功' if last_step['StepResult']['IsSuccess'] else '失败'}"
                            )
                        await asyncio.sleep(5)

                except Exception as e:
                    # 任务执行异常
                    error_msg = f"任务{index}执行异常: {str(e)}"
                    results[index] = error_msg
                    logger.error(error_msg)
                finally:
                    # 无论成功失败，释放pod
                    if pod_id:
                        _cancel_task(pod_pool.task_map[pod_id])
                        pod_pool.release_pod(pod_id)

            return run

        # 创建所有任务的协程
        for i, prompt in enumerate(user_prompts):
            coroutines.append(task_worker(i, prompt)())

        # 并发执行所有任务
        await asyncio.gather(*coroutines)
        return results

    # 外层函数返回内层工具函数（闭包特性：保留外层配置的引用）
    return mobile_use_tool
