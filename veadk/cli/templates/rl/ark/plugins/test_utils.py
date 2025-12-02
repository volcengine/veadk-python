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
import os
from ark_sdk.core.plugin.rollout.proxy import InferenceProxy, Mode
from ark_sdk.types.pipeline_plugin.rollout import (
    Trajectory,
    ChatCompletionSample,
)
import json

from loguru import logger
import contextvars


async def test_with_dataset(
    jsonl_file_path: str,
    demo_rollout,
    llm_grader,
    limit: int = 100,
    max_concurrent: int = 5,
):
    """
    Test with dataset with concurrency control.

    Args:
        jsonl_file_path: Path to the JSONL dataset file
        demo_rollout: The rollout function to test
        llm_grader: The grader function to evaluate results
        limit: Maximum number of samples to process
        max_concurrent: Maximum number of concurrent tasks (default: 5)
    """
    mode = Mode.Inference
    rewards = []
    semaphore = asyncio.Semaphore(max_concurrent)

    async def rollout_and_grader_with_semaphore(line: str, line_num: int):
        async with semaphore:
            try:
                data = json.loads(line.strip())
                sample = ChatCompletionSample(**data)
                proxy = InferenceProxy(
                    sample,
                    url="https://ark.cn-beijing.volces.com/api/v3",
                    jwt_token=os.getenv("ARK_API_KEY", "xxx"),
                    mode=mode,
                )
                await demo_rollout({}, proxy, sample)
                logger.info(f"rollout finished - {line_num}")
                grader_res = await llm_grader(
                    {},
                    sample,
                    [
                        Trajectory(
                            messages=proxy.messages,
                            usage=proxy.usage,
                            finish_reason=proxy.finish_reason,
                        )
                    ],
                )
                rewards.extend(grader_res.rewards)
                logger.info(
                    f"grader finished - {line_num}, rewards: {grader_res.rewards}"
                )
            except Exception as e:
                logger.error(f"Error processing line {line_num}: {e}")
                # Continue processing other tasks even if one fails

    tasks = []
    with open(jsonl_file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if line_num > limit:
                break
            if line.strip():
                ctx = contextvars.Context()
                task = ctx.run(
                    asyncio.create_task,
                    rollout_and_grader_with_semaphore(line, line_num),
                )
                tasks.append(task)

    # Wait for all tasks to complete, handling exceptions gracefully
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Log any exceptions that occurred
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Task {i + 1} failed with exception: {result}")

    logger.info(f"Processed {len(tasks)} samples with {len(rewards)} total rewards")
    return rewards
