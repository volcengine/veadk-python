"""
VeADK Web App - 多部门 IT 运维助手
---------------------------------

将 Notebook 中的配置加载、Runbook 同步、Agent 装配逻辑整理为模块，以便 `veadk web`
能够自动发现 `root_agent` 并运行。代码风格与 `code style example.py` 保持一致：
大量注释、结构化函数、显式日志，方便调试与运维。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types as genai_types
from veadk import Agent, Runner
from veadk.knowledgebase import KnowledgeBase
from veadk.memory.long_term_memory import LongTermMemory
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
#                                   日志配置
# ============================================================================
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "it_ops_web.log"

log_formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
root_logger = logging.getLogger("it_ops_web")
root_logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
file_handler.setFormatter(log_formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)

root_logger.handlers.clear()
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = root_logger
logger.info("VeADK Web 日志输出: %s", LOG_FILE)

# ============================================================================
#                                   配置
# ============================================================================
DOCS_DIR = Path(__file__).resolve().parents[1]
KB_BASE_DIR = DOCS_DIR / "knowledgebase" / "多部门IT运维助手_example"
CONFIG_PATH = KB_BASE_DIR / "app" / "config.yaml"


@dataclass
class AppConfig:
    """统一管理 AK/SK、项目、集合、TOS bucket 等信息。"""

    access_key: str
    secret_key: str
    project: str
    region: str
    bucket: str
    collections: Dict[str, str]


def _resolve_value(value: str) -> str:
    """支持 ${ENV} 占位符."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_key = value[2:-1]
        resolved = os.getenv(env_key)
        if not resolved:
            raise KeyError(f"环境变量 {env_key} 未设置")
        return resolved
    return value


def load_app_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"未找到配置文件: {CONFIG_PATH}")

    raw_cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    volc_cfg = raw_cfg.get("volcengine", {})
    vk_cfg = raw_cfg.get("database", {}).get("viking", {})
    cfg = AppConfig(
        access_key=_resolve_value(volc_cfg["access_key"]),
        secret_key=_resolve_value(volc_cfg["secret_key"]),
        project=vk_cfg.get("project", "default"),
        region=vk_cfg.get("region", "cn-beijing"),
        bucket=vk_cfg.get("tos_bucket", "veadk-itops-assistant-kb"),
        collections=vk_cfg.get(
            "collections",
            {"network": "itops_network", "host": "itops_host", "app": "itops_app", "sec": "itops_sec"},
        ),
    )
    logger.info("配置加载完成，Viking collections=%s", cfg.collections)
    return cfg


def apply_environment(cfg: AppConfig) -> None:
    env_mapping = {
        "VOLCENGINE_ACCESS_KEY": cfg.access_key,
        "VOLCENGINE_SECRET_KEY": cfg.secret_key,
        "DATABASE_VIKING_PROJECT": cfg.project,
        "DATABASE_VIKING_REGION": cfg.region,
        "DATABASE_TOS_BUCKET": cfg.bucket,
        "MODEL_AGENT_API_KEY": cfg.access_key,
    }
    for key, value in env_mapping.items():
        os.environ[key] = value
    logger.info("环境变量已注入: %s", list(env_mapping.keys()))


APP_CONFIG = load_app_config()
apply_environment(APP_CONFIG)

# ============================================================================
#                              Runbook & 知识库
# ============================================================================


def load_runbook_directories() -> Dict[str, Path]:
    candidate = KB_BASE_DIR / "kb"
    if not candidate.exists():
        raise FileNotFoundError(f"未找到 Runbook 目录: {candidate}")
    dirs = {
        "network": candidate / "network",
        "host": candidate / "host",
        "app": candidate / "app",
        "sec": candidate / "sec",
    }
    for name, folder in dirs.items():
        files = [f.name for f in folder.glob("*.md")]
        logger.info("[%s] Runbook: %s", name, files)
    return dirs


def sync_runbooks_to_viking(runbook_dirs: Dict[str, Path], cfg: AppConfig) -> Dict[str, KnowledgeBase]:
    skip_upload = os.getenv("SKIP_VIKING_UPLOAD", "0") == "1" or os.getenv("VEADK_WEB_MODE") == "1"
    if skip_upload:
        logger.warning("WEB/SHELL 配置跳过上传，本次不向 VikingDB 写入文档。")
    kb_map: Dict[str, KnowledgeBase] = {}
    for dept, directory in runbook_dirs.items():
        index = cfg.collections.get(dept, f"itops_{dept}")
        try:
            kb = KnowledgeBase(
                backend="viking",
                backend_config={"index": index, "volcengine_project": cfg.project, "region": cfg.region},
            )
            logger.info("加载 [%s] -> collection=%s%s", dept, index, " (skip upload)" if skip_upload else "")
            if not skip_upload:
                kb.add_from_directory(str(directory))
        except Exception as exc:
            logger.error("Viking backend 初始化失败，自动切换到 local。error=%s", exc)
            kb = KnowledgeBase(backend="local", backend_config={"index": f"local_{dept}"})
        kb_map[dept] = kb
    return kb_map


RUNBOOK_DIRS = load_runbook_directories()
DEPARTMENT_KB = sync_runbooks_to_viking(RUNBOOK_DIRS, APP_CONFIG)

# ============================================================================
#                              Agent 装配
# ============================================================================


class MockLlm(BaseLlm):
    """离线 demo 使用的简单 LLM。"""

    async def generate_content_async(self, llm_request, stream: bool = False):
        user_queries = []
        for content in llm_request.contents:
            if content.role == "user":
                for part in content.parts or []:
                    if getattr(part, "text", None):
                        user_queries.append(part.text)
        query = user_queries[-1] if user_queries else "未提供问题"
        text = f"[MockLLM] {query}"
        response_content = genai_types.Content(role="model", parts=[genai_types.Part.from_text(text=text)])
        yield LlmResponse(content=response_content)


def build_department_agents() -> Dict[str, Agent]:
    llms = {
        "network": MockLlm(model="mock-network"),
        "host": MockLlm(model="mock-host"),
        "app": MockLlm(model="mock-app"),
        "sec": MockLlm(model="mock-sec"),
        "planner": MockLlm(model="mock-planner"),
    }
    agents = {
        "network": Agent(
            name="network_agent",
            description="网络排障助手",
            instruction="仅根据你的知识库回答网络排障问题。",
            knowledgebase=DEPARTMENT_KB["network"],
            model=llms["network"],
        ),
        "host": Agent(
            name="host_agent",
            description="主机/中间件助手",
            instruction="仅根据你的知识库回答主机/中间件排障问题。",
            knowledgebase=DEPARTMENT_KB["host"],
            model=llms["host"],
        ),
        "app": Agent(
            name="app_agent",
            description="业务应用助手",
            instruction="仅根据你的知识库回答业务应用排障问题。",
            knowledgebase=DEPARTMENT_KB["app"],
            model=llms["app"],
        ),
        "sec": Agent(
            name="sec_agent",
            description="安全事件助手",
            instruction="仅根据你的知识库回答安全相关问题。",
            knowledgebase=DEPARTMENT_KB["sec"],
            model=llms["sec"],
        ),
    }
    root = Agent(
        name="itops_root",
        description="运维总控台",
        instruction=(
            "你是 IT 运维总控台。先判断用户问题属于 网络/主机/应用/安全 哪一类，"
            "然后调用相应子 Agent 获取答案并整合。"
        ),
        tools=[],
        sub_agents=list(agents.values()),
        model=llms["planner"],
    )
    agents["root"] = root
    return agents


DEPARTMENT_AGENTS = build_department_agents()
root_agent = DEPARTMENT_AGENTS["root"]

# ============================================================================
#                             记忆 & Tracing
# ============================================================================
root_agent.long_term_memory = LongTermMemory(backend="local", index="itops_ltm_demo")
root_agent.tracers = [OpentelemetryTracer()]
logger.info("长期记忆 backend=local，Tracer 已启用")

# ============================================================================
#                             Runner (可选)
# ============================================================================
runner = Runner(agent=root_agent, app_name="itops_demo_app", user_id="demo_user")
