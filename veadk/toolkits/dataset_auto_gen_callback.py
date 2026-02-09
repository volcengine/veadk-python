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

import json
import os
import re
from pathlib import Path
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

JUDGE_PROMPT = """You are an AI quality evaluator. Analyze the agent interaction trace and classify it.

## Trace Data
{trace}

## Evaluation Dimensions

### 1. Task Completion
- Did the agent understand the user's intent correctly?
- Was the user's request fully addressed?
- Did the agent provide the expected output?

### 2. Tool Usage (if applicable)
- Were the correct tools/functions selected for the task?
- Were the function arguments accurate and complete?
- Was the function response handled properly?
- Did the agent interpret tool results correctly?

### 3. Response Quality
- Is the response accurate and factually correct?
- Is the response complete without missing information?
- Is the response clear and well-structured?
- Does it match the tool/function output when applicable?

### 4. Error Handling
- Were there any errors or exceptions in the trace?
- Did the agent handle edge cases appropriately?
- Were error messages helpful if errors occurred?

### 5. Conversation Flow
- Is the dialogue natural and coherent?
- Did the agent maintain context across turns?
- Were there any unnecessary or redundant steps?

## Classification Criteria
- **good (1)**: Task completed successfully with correct tool usage, accurate response, and smooth conversation flow
- **general (0)**: Normal interaction without notable issues or achievements, routine responses
- **bad (-1)**: Contains errors, incorrect tool usage, wrong/incomplete response, or failed to address user needs

## Output Format (JSON only, no other text)
{{"type": <-1|0|1>, "reason": "<brief explanation covering key evaluation points>"}}"""


async def dataset_auto_gen_callback(
    callback_context: CallbackContext,
) -> Optional[types.Content]:
    """After agent callback to auto-generate dataset from traces."""
    ctx = callback_context._invocation_context
    agent = ctx.agent
    session = ctx.session

    if not session or not session.events:
        return None

    # Build trace json
    trace_data = {
        "session_id": session.id,
        "events": [
            {
                "author": e.author,
                "content": e.content.model_dump() if e.content else None,
            }
            for e in session.events
        ],
    }
    trace_json = json.dumps(trace_data, ensure_ascii=False)

    # Judge using LLM
    try:
        from litellm import acompletion

        model_name = getattr(agent.model, "model", "openai/gpt-4o-mini")
        api_key = getattr(agent, "model_api_key", None) or getattr(
            agent.model, "api_key", None
        )
        api_base = getattr(agent, "model_api_base", None) or getattr(
            agent.model, "api_base", None
        )

        response = await acompletion(
            model=model_name,
            messages=[
                {"role": "user", "content": JUDGE_PROMPT.format(trace=trace_json)}
            ],
            api_key=api_key,
            api_base=api_base,
        )
        raw_content = response.choices[0].message.content

        # Extract JSON from response
        json_match = re.search(r'\{[^{}]*"type"[^{}]*\}', raw_content)
        if not json_match:
            logger.debug("No valid JSON found in LLM response")
            return None
        result = json.loads(json_match.group())
    except Exception as e:
        logger.warning(f"Dataset auto gen failed: {e}")
        return None

    # Save to file based on type
    case_type = result.get("type", 0)

    output_dir = Path(os.getcwd()) / "dataset" / agent.name
    output_dir.mkdir(parents=True, exist_ok=True)

    if case_type == 1:
        file_name = "good_case.jsonl"
    elif case_type == -1:
        file_name = "bad_case.jsonl"
    else:
        file_name = "general_case.jsonl"
    record = {"trace": trace_data, "reason": result.get("reason", "")}

    with open(output_dir / file_name, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    logger.info(f"Dataset case saved to {output_dir / file_name}")
    return None
