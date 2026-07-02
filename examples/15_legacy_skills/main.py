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
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv

# VeADK reads model settings during import, so load the local env first.
AGENT_ROOT = Path(__file__).parent
load_dotenv(AGENT_ROOT / ".env")

from google.adk.skills import load_skill_from_dir  # noqa: E402
from google.adk.tools.skill_toolset import SkillToolset  # noqa: E402
from google.genai import types  # noqa: E402

from veadk import Agent, Runner  # noqa: E402
from veadk.skills import VeSkillRegistry  # noqa: E402
from veadk.utils.logger import get_logger  # noqa: E402

# 本地测试 Skill 目录
SKILLS_ROOT = AGENT_ROOT / "local_skills"
SKILL_DIR = SKILLS_ROOT / "company-qa"

# 远端 SkillSpace，ss- 开头会走旧 SkillSpace 加载逻辑
SKILLSPACE_ID = "ss-yep2o9dgxswl3fpmpdle"

# 远端 skill 下载后的本地缓存目录
SKILLS_CACHE_DIR = AGENT_ROOT / ".veadk_skills_cache"

logger = get_logger(__name__)


MODEL_REQUEST_CONFIG = types.GenerateContentConfig(
    temperature=float(os.getenv("MODEL_AGENT_TEMPERATURE", "0.2")),
    top_p=float(os.getenv("MODEL_AGENT_TOP_P", "0.8")),
    max_output_tokens=int(os.getenv("MODEL_AGENT_MAX_OUTPUT_TOKENS", "1024")),
)

MODEL_EXTRA_CONFIG = {
    "extra_body": {
        "thinking": {
            "type": os.getenv("MODEL_AGENT_THINKING_TYPE", "disabled"),
        },
    },
}

MODEL_DEBUG_ENABLED = os.getenv("MODEL_AGENT_DEBUG", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
MODEL_DEBUG_INCLUDE_CONTENT = os.getenv(
    "MODEL_AGENT_DEBUG_INCLUDE_CONTENT",
    "true",
).lower() in {"1", "true", "yes", "on"}
MODEL_DEBUG_MAX_TEXT_CHARS = int(os.getenv("MODEL_AGENT_DEBUG_MAX_TEXT_CHARS", "0"))


def _truncate_text(text: str) -> str:
    if MODEL_DEBUG_MAX_TEXT_CHARS <= 0 or len(text) <= MODEL_DEBUG_MAX_TEXT_CHARS:
        return text
    return text[:MODEL_DEBUG_MAX_TEXT_CHARS] + (
        f"...<truncated {len(text) - MODEL_DEBUG_MAX_TEXT_CHARS} chars>"
    )


def _text_debug_value(text: str) -> str:
    if not MODEL_DEBUG_INCLUDE_CONTENT:
        return "<omitted; set MODEL_AGENT_DEBUG_INCLUDE_CONTENT=true>"
    return repr(_truncate_text(text))


def _model_dump(value):
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        return {key: _model_dump(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_model_dump(item) for item in value]
    return value


def _dump_function_call(function_call) -> dict:
    return {
        "id": function_call.id,
        "name": function_call.name,
        "args": _model_dump(function_call.args),
        "partial_args": _model_dump(function_call.partial_args),
        "will_continue": function_call.will_continue,
    }


def _dump_function_response(function_response) -> dict:
    return {
        "id": function_response.id,
        "name": function_response.name,
        "response": _model_dump(function_response.response),
        "parts": _model_dump(function_response.parts),
        "will_continue": function_response.will_continue,
        "scheduling": function_response.scheduling,
    }


def _dump_part(part: types.Part) -> dict:
    payload = {
        "thought": part.thought,
        "thought_signature": part.thought_signature,
        "part_metadata": _model_dump(part.part_metadata),
    }

    if part.text is not None:
        payload["type"] = "text"
        payload["text_repr"] = _text_debug_value(part.text)
    elif part.function_call is not None:
        payload["type"] = "function_call"
        payload["function_call"] = _dump_function_call(part.function_call)
    elif part.function_response is not None:
        payload["type"] = "function_response"
        payload["function_response"] = _dump_function_response(part.function_response)
    elif part.tool_call is not None:
        payload["type"] = "tool_call"
        payload["tool_call"] = _model_dump(part.tool_call)
    elif part.tool_response is not None:
        payload["type"] = "tool_response"
        payload["tool_response"] = _model_dump(part.tool_response)
    elif part.executable_code is not None:
        payload["type"] = "executable_code"
        payload["executable_code"] = _model_dump(part.executable_code)
    elif part.code_execution_result is not None:
        payload["type"] = "code_execution_result"
        payload["code_execution_result"] = _model_dump(part.code_execution_result)
    elif part.file_data is not None:
        payload["type"] = "file_data"
        payload["file_data"] = _model_dump(part.file_data)
        payload["video_metadata"] = _model_dump(part.video_metadata)
    elif part.inline_data is not None:
        payload["type"] = "inline_data"
        payload["inline_data"] = {
            "mime_type": part.inline_data.mime_type,
            "data_bytes": len(part.inline_data.data or b""),
        }
        payload["video_metadata"] = _model_dump(part.video_metadata)
    else:
        payload["type"] = "unknown"
        payload["raw"] = _model_dump(part)

    return {key: value for key, value in payload.items() if value is not None}


def _dump_contents(contents: list[types.Content]) -> list[dict]:
    dumped = []
    for index, content in enumerate(contents):
        parts = [_dump_part(part) for part in content.parts or []]
        dumped.append(
            {
                "index": index,
                "role": content.role,
                "parts_count": len(parts),
                "parts": parts,
            }
        )
    return dumped


def _to_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _debug_model_request(callback_context, llm_request):
    if not MODEL_DEBUG_ENABLED:
        return None

    callback_context.state["_model_request_started_at"] = perf_counter()
    request_index = int(callback_context.state.get("_model_debug_request_index", 0)) + 1
    callback_context.state["_model_debug_request_index"] = request_index
    config = llm_request.config.model_dump(exclude_none=True)

    logger.info(
        "model_request_start\n"
        + _to_json(
            {
                "request_index": request_index,
                "agent_name": getattr(callback_context, "agent_name", None),
                "invocation_id": getattr(callback_context, "invocation_id", None),
                "model": llm_request.model,
                "config": config,
                "tools": sorted(llm_request.tools_dict.keys()),
                "contents": _dump_contents(llm_request.contents),
                "cache_config": _model_dump(llm_request.cache_config),
                "cache_metadata": _model_dump(llm_request.cache_metadata),
                "cacheable_contents_token_count": (
                    llm_request.cacheable_contents_token_count
                ),
                "previous_interaction_id": llm_request.previous_interaction_id,
            }
        )
    )
    return None


def _debug_model_response(callback_context, llm_response):
    if not MODEL_DEBUG_ENABLED:
        return None

    started_at = callback_context.state.get("_model_request_started_at")
    elapsed_ms = (
        round((perf_counter() - started_at) * 1000, 2)
        if isinstance(started_at, float)
        else None
    )
    usage = (
        llm_response.usage_metadata.model_dump(exclude_none=True)
        if llm_response.usage_metadata
        else None
    )

    logger.info(
        "model_response_end\n"
        + _to_json(
            {
                "elapsed_ms": elapsed_ms,
                "model_version": llm_response.model_version,
                "content": _dump_contents([llm_response.content])
                if llm_response.content
                else None,
                "finish_reason": llm_response.finish_reason,
                "turn_complete": llm_response.turn_complete,
                "partial": llm_response.partial,
                "usage": usage,
                "error_code": llm_response.error_code,
                "error_message": llm_response.error_message,
            }
        )
    )
    return None


def _debug_model_error(callback_context, llm_request, error):
    if not MODEL_DEBUG_ENABLED:
        return None

    started_at = callback_context.state.get("_model_request_started_at")
    elapsed_ms = (
        round((perf_counter() - started_at) * 1000, 2)
        if isinstance(started_at, float)
        else None
    )

    logger.exception(
        "model_request_error\n"
        + _to_json(
            {
                "elapsed_ms": elapsed_ms,
                "model": llm_request.model,
                "error": repr(error),
            }
        )
    )
    return None


def _debug_tool_start(tool, args, tool_context):
    if not MODEL_DEBUG_ENABLED:
        return None

    logger.info(
        "tool_start\n"
        + _to_json(
            {
                "tool": getattr(tool, "name", type(tool).__name__),
                "args": _model_dump(args),
                "agent_name": getattr(tool_context, "agent_name", None),
                "invocation_id": getattr(tool_context, "invocation_id", None),
            }
        )
    )
    return None


def _debug_tool_end(tool, args, tool_context, tool_response):
    if not MODEL_DEBUG_ENABLED:
        return None

    logger.info(
        "tool_end\n"
        + _to_json(
            {
                "tool": getattr(tool, "name", type(tool).__name__),
                "args": _model_dump(args),
                "response": _model_dump(tool_response),
                "agent_name": getattr(tool_context, "agent_name", None),
                "invocation_id": getattr(tool_context, "invocation_id", None),
            }
        )
    )
    return None


def _debug_tool_error(tool, args, tool_context, error):
    if not MODEL_DEBUG_ENABLED:
        return None

    logger.exception(
        "tool_error\n"
        + _to_json(
            {
                "tool": getattr(tool, "name", type(tool).__name__),
                "args": _model_dump(args),
                "error": repr(error),
                "agent_name": getattr(tool_context, "agent_name", None),
                "invocation_id": getattr(tool_context, "invocation_id", None),
            }
        )
    )
    return None


def ensure_demo_skill():
    """创建一个真实的本地 VeADK Skill，用于测试旧入口。"""
    references_dir = SKILL_DIR / "references"
    references_dir.mkdir(parents=True, exist_ok=True)

    (SKILL_DIR / "SKILL.md").write_text(
        """---
name: company-qa
description: 根据公司资料回答问题，并在回答中说明依据。
---

当用户询问公司制度、团队流程或报销规则时：
1. 先读取 references/company.md。
2. 只根据资料回答。
3. 如果资料里没有答案，明确说资料未覆盖。
""",
        encoding="utf-8",
    )

    (references_dir / "company.md").write_text(
        """公司报销规则：
- 单笔超过 500 元需要直属负责人审批。
- 差旅报销需要提供发票和行程单。
- 餐补标准为每人每天 80 元。
""",
        encoding="utf-8",
    )


def check_skillspace_env():
    """检查加载远端 SkillSpace 所需的凭证。"""
    if not os.getenv("VOLCENGINE_ACCESS_KEY"):
        raise ValueError("VOLCENGINE_ACCESS_KEY environment variable is not set")
    if not os.getenv("VOLCENGINE_SECRET_KEY"):
        raise ValueError("VOLCENGINE_SECRET_KEY environment variable is not set")


# 创建本地测试 Skill
ensure_demo_skill()

# 本地 skill 走 ADK 原生加载，远端 SkillSpace 走 VeSkillRegistry 按需加载。
check_skillspace_env()
local_skill = load_skill_from_dir(SKILL_DIR)
remote_registry = VeSkillRegistry(
    skill_source_id=SKILLSPACE_ID,
    cache_dir=SKILLS_CACHE_DIR,
)
skill_toolset = SkillToolset(
    skills=[local_skill],
    registry=remote_registry,
)

# 定义测试 Agent
personal_assistant = Agent(
    name="legacy_skill_test_agent",
    description="一个用于验证 VeADK 旧 skills 入口的测试助手。",
    instruction="""你是一个友好的智能测试助手，请用简洁明了的中文回答用户的问题。
回答时请说明依据来自哪个 skill 或资料。
如果资料中没有相关信息，请明确说明资料未覆盖。
""",
    model_name=os.getenv("MODEL_AGENT_NAME", "doubao-seed-1-8-251228"),
    model_provider=os.getenv("MODEL_AGENT_PROVIDER", "openai"),
    model_api_base=os.getenv(
        "MODEL_AGENT_API_BASE",
        "https://ark.cn-beijing.volces.com/api/v3/",
    ),
    model_api_key=os.getenv("MODEL_AGENT_API_KEY", "test-key"),
    generate_content_config=MODEL_REQUEST_CONFIG,
    model_extra_config=MODEL_EXTRA_CONFIG,
    before_model_callback=_debug_model_request,
    after_model_callback=_debug_model_response,
    on_model_error_callback=_debug_model_error,
    before_tool_callback=_debug_tool_start,
    after_tool_callback=_debug_tool_end,
    on_tool_error_callback=_debug_tool_error,
    tools=[skill_toolset],
)

# 使用 veadk web 进行调试
root_agent = personal_assistant


async def main():
    """运行测试助手的主函数"""
    print("欢迎使用 VeADK 旧 skills 入口测试助手！")
    print("输入 'exit' 或 'quit' 退出程序。")
    print("=" * 50)

    print("已加载本地 Skills:", [local_skill.name])
    print("SkillSpace ID:", SKILLSPACE_ID)
    print("Skill 缓存目录:", SKILLS_CACHE_DIR)
    print("Agent 工具:", [type(tool).__name__ for tool in personal_assistant.tools])
    print("是否使用旧 skills_tool:", "skills_tool" in personal_assistant.instruction)
    print("=" * 50)

    if not os.getenv("MODEL_AGENT_API_KEY"):
        print("提示：当前未设置 MODEL_AGENT_API_KEY。")
        print("如果只是验证 Agent 构建和 Skill 加载，这是正常的。")
        print("如果要真实对话，请先在 .env 中配置 MODEL_AGENT_API_KEY。")
        print("=" * 50)

    runner = Runner(
        agent=personal_assistant,
        app_name="legacy_skill_test_demo",
        user_id="demo_user",
    )

    while True:
        user_input = input("请输入您的问题:  ")

        if user_input.lower() in ["exit", "quit", "退出"]:
            print("再见！")
            break

        try:
            response = await runner.run(messages=user_input)
            print(f"助手: {response}")
        except Exception as e:
            print(f"发生错误: {e}")

        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
