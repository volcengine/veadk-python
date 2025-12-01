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

import random
from typing import List
from ark_sdk.resources.pipeline_plugin import group_grader
from ark_sdk.types.pipeline_plugin.pipeline_plugin import PluginStatus, PluginContext
from ark_sdk.types.pipeline_plugin.rollout import Trajectory, ChatCompletionSample
from ark_sdk.types.pipeline_plugin import (
    Runtime,
    PluginInstance,
    GroupGraderResult,
)


@group_grader(
    name="randaom_reward",
    runtime=Runtime(
        instance=PluginInstance.CPU1MEM2,
        max_concurrency=100,
        timeout=300,
    ),
)
def random_reward_fn(
    context: PluginContext,
    sample: ChatCompletionSample,
    trajectories: List[Trajectory],
) -> GroupGraderResult:
    """
    奖励函数：返回随机奖励

    参数:
    - trajectories: 完整的对话历史
    - sample: 样本数据，包含标准答案的字典

    返回:
    - list[float]: 奖励分数列表，每个分数对应一个候选回复（1.0表示完全匹配，0.0表示不匹配）

    依赖:
    - 数据集里的字典字段 extra 内需要携带 answer 字段。
    """
    rewards = [
        t.extra["reward"] if (t.extra and "reward" in t.extra) else random.random()
        for t in trajectories
    ]
    return GroupGraderResult(
        rewards=rewards, status=PluginStatus.SUCCESS, error="", metrics={}
    )
