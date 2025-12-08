import os
from veadk import Agent, Runner
import datetime
import logging
from dotenv import load_dotenv
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.short_term_memory import ShortTermMemory
import asyncio
import json

from google.genai import types

logging.basicConfig(level=logging.INFO)
load_dotenv()
logger = logging.getLogger(__name__)

# 应用/用户上下文与 STM（与 ADK 文档示例保持一致的资源共享）
APP_NAME = os.getenv("APP_NAME", "local_memory_demo")
USER_ID = os.getenv("USER_ID", "demo_user")
os.environ["DATABASE_VIKING_PROJECT"] = "default"
os.environ["DATABASE_VIKING_REGION"] = "cn-beijing"
# short_term_memory = ShortTermMemory(backend="sqlite", db_url="sqlite:///./veadk_stm_1.db")
short_term_memory = ShortTermMemory(backend="local")
long_term_memory = LongTermMemory(backend="viking", app_name=APP_NAME, user_id=USER_ID)

root_agent = Agent(
    name="minimal_agent",
    description="A minimal agent for memory workflow demo.",
    instruction="Acknowledge user input and maintain simple conversation.",
    long_term_memory=long_term_memory,
)


# --- 记忆使用的流程演示（五步） ---
async def demo_memory_flow():
    """演示将会话写入长期记忆并检索验证的完整流程。

    步骤：
    1) 创建 session
    2) 对话
    3) 获取完整 session
    4) 使用 memory_service.add_session_to_memory
    5) 验证检索
    """

    # 1. 创建 Runner 与 Session
    logger.info("[Step 1] Creating Runner and Session")
    runner1 = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        user_id=USER_ID,
        short_term_memory=short_term_memory,
    )
    logger.info(f"Runner1 initialized: app_name={APP_NAME}, user_id={USER_ID}")
    session_id = f"memory_demo_session_{int(datetime.datetime.now().timestamp())}"
    logger.debug(f"Target session_id={session_id}")
    await runner1.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    logger.info(f"Session created: id={session_id}")

    # 2. 对话（写入一段需要被记住的信息）
    logger.info("[Step 2] Running dialogue to populate session events")
    runner1_question = "My favorite project is Project Alpha."
    logger.info(f"Runner1 Question: {runner1_question}")
    user_input = types.Content(role="user", parts=[types.Part(text=runner1_question)])
    final_response_text = "(No final response)"
    async for event in runner1.run_async(
        user_id=USER_ID, session_id=session_id, new_message=user_input
    ):
        if (
            event.is_final_response()
            and event.content
            and event.content.parts
            and hasattr(event.content.parts[0], "text")
            and event.content.parts[0].text
        ):
            final_response_text = event.content.parts[0].text.strip()
    logger.info(f"Runner1 Answer: {final_response_text}")

    # 3. 获取完整 Session
    logger.info("[Step 3] Fetching completed session from session_service")
    completed_session = await runner1.session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    try:
        logger.info(f"Completed session fetched: id={completed_session.id}")
    except Exception:
        logger.debug(
            "Completed session fetched, unable to log event count due to unexpected structure"
        )

    # 4. 使用 memory_service（LongTermMemory）进行 add_session_to_memory
    logger.info("[Step 4] Archiving session to Long-Term Memory via memory_service")
    root_agent.long_term_memory.add_session_to_memory(completed_session)
    logger.info("Session archived to Long-Term Memory")

    # 5.1 使用 runner2 进行问答（favorite project）
    logger.info("[Step 5.1] Runner2 Q&A using memory")
    runner2 = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        user_id=USER_ID,
        short_term_memory=short_term_memory,
    )
    try:
        qa_question = "favorite project"
        logger.info(f"Runner2 Question: {qa_question}")
        qa_content = types.Content(role="user", parts=[types.Part(text=qa_question)])
        final_text = None
        async for event in runner2.run_async(
            user_id=USER_ID, session_id=session_id, new_message=qa_content
        ):
            if (
                event.is_final_response()
                and event.content
                and event.content.parts
                and hasattr(event.content.parts[0], "text")
                and event.content.parts[0].text
            ):
                final_text = event.content.parts[0].text.strip()
        logger.info(f"Runner2 Answer: {final_text or '(no text)'}")
    except Exception as e:
        logger.warning(f"Runner2 QA error: {str(e)}")

    # 5.2 直接使用 search_memory 进行检索
    logger.info("[Step 5.2] Direct memory search")
    try:
        query = "favorite project"
        logger.debug(f"Searching LTM with query='{query}'")
        res = await root_agent.long_term_memory.search_memory(
            app_name=APP_NAME, user_id=USER_ID, query=query
        )
        payload = res.model_dump() if hasattr(res, "model_dump") else res
        logger.info(f"Memory search result: {json.dumps(payload, ensure_ascii=False)}")
    except Exception as e:
        logger.warning(f"Memory search error: {str(e)}")


if __name__ == "__main__":
    try:
        asyncio.run(demo_memory_flow())
    except Exception as e:
        print("Demo run failed:", e)
