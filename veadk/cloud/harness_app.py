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

import io
import os
import shutil
import zipfile
from pathlib import Path
from typing import Literal

import frontmatter
import httpx
from fastapi import FastAPI
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from pydantic import BaseModel, Field

from veadk import Agent
from veadk.consts import DEFAULT_MODEL_AGENT_NAME
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runner import Runner
from veadk.utils.logger import get_logger
from veadk.utils.misc import formatted_timestamp

logger = get_logger(__name__)

# Skill hub download endpoint. A skill name in a harness is the path after
# `/download/`, e.g. "clawhub/lgwventrue/system-file-handler".
SKILL_HUB_DOWNLOAD_URL = os.getenv(
    "SKILL_HUB_DOWNLOAD_URL", "https://skills.volces.com/v1/skills/download"
)


def _split_csv(value: str) -> list[str]:
    """Split a comma-separated string into a list of trimmed, non-empty names.

    ``"web_search, web_fetch"`` -> ``["web_search", "web_fetch"]``; ``""`` -> ``[]``.
    """
    return [item.strip() for item in value.split(",") if item.strip()]


def _download_and_extract_skill(skill: str, dest_dir: Path) -> Path:
    """Download a skill zip from the skill hub and extract it.

    Args:
        skill: Skill identifier — the hub path after ``/download/``
            (e.g. ``"clawhub/lgwventrue/system-file-handler"``).
        dest_dir: Base directory to extract into; the skill is placed in a
            subdirectory named after the identifier's last path segment.

    Returns:
        The directory the skill was extracted to. Its name matches the skill's
        declared name in ``SKILL.md`` (required by ``load_skill_from_dir``).
    """
    name = skill.strip("/")
    url = f"{SKILL_HUB_DOWNLOAD_URL.rstrip('/')}/{name}"
    logger.info(f"Downloading skill '{skill}' from {url}")

    response = httpx.get(url, timeout=60, follow_redirects=True)
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to download skill '{skill}': HTTP {response.status_code}"
        )

    # Extract to a staging dir first; the final directory must be named after
    # the skill's declared name (ADK's load_skill_from_dir enforces this).
    staging = dest_dir / f"{name.split('/')[-1]}__staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    staging_root = staging.resolve()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        for member in zf.namelist():
            # Guard against path traversal (zip-slip).
            if not (staging / member).resolve().is_relative_to(staging_root):
                raise RuntimeError(f"Unsafe path in skill '{skill}' zip: {member}")
        zf.extractall(staging)

    skill_md = staging / "SKILL.md"
    if not skill_md.exists():
        skill_md = staging / "skill.md"
    if not skill_md.exists():
        raise RuntimeError(f"Skill '{skill}' has no SKILL.md")
    declared_name = frontmatter.loads(
        skill_md.read_text(encoding="utf-8")
    ).metadata.get("name")
    if not declared_name:
        raise RuntimeError(f"Skill '{skill}' SKILL.md has no 'name' in frontmatter")

    skill_dir = dest_dir / str(declared_name)
    if skill_dir.exists():
        shutil.rmtree(skill_dir)
    staging.rename(skill_dir)

    logger.info(f"Extracted skill '{skill}' (name='{declared_name}') to {skill_dir}")
    return skill_dir


class Harness(BaseModel):
    model_name: str = Field(default=DEFAULT_MODEL_AGENT_NAME)
    # `tools` and `skills` are comma-separated strings (e.g. "web_search,web_fetch").
    # The app splits them into names via _split_csv(); clients (CLI/curl) just
    # pass the raw string.
    tools: str = Field(default="")
    skills: str = Field(default="")
    system_prompt: str = Field(default="You are a helpful assistant.")
    # Agent runtime backend: "adk" (default) or "codex". Passed through to the
    # Agent; "codex" requires the optional codex extra on the server.
    runtime: Literal["adk", "codex"] = Field(default="adk")


class AddHarnessRequest(BaseModel):
    harness_name: str
    harness: Harness


class AddHarnessResponse(BaseModel):
    code: int = Field(default=200)
    msg: str = Field(default="Harness added successfully.")
    harness_name: str


class RunAgentRequest(BaseModel):
    user_id: str
    session_id: str


class InvokeHarnessRequest(BaseModel):
    prompt: str
    harness_name: str
    harness: Harness | None = None
    run_agent_request: RunAgentRequest


class InvokeHarnessResponse(BaseModel):
    harness_name: str
    overwrite: bool = Field(
        default=False
    )  # Whether the agent is created with once-time harness or not.
    output: str


class HarnessApp:
    def __init__(self):
        self.app = FastAPI()
        self.agents = {}

        self.short_term_memory = ShortTermMemory(backend="local")

        self.mount()

    def mount(self):
        @self.app.post("/harness/add")
        def add_harness(request: AddHarnessRequest) -> AddHarnessResponse:
            if request.harness_name in self.agents:
                logger.warning(
                    f"Harness with name {request.harness_name} already exists."
                )
                return AddHarnessResponse(
                    code=400,
                    msg=f"Harness with name {request.harness_name} already exists.",
                    harness_name=request.harness_name,
                )

            agent = self._create_agent(request.harness)
            self.agents[request.harness_name] = agent
            return AddHarnessResponse(harness_name=request.harness_name)

        @self.app.post("/harness/invoke")
        async def invoke_harness(
            request: InvokeHarnessRequest,
        ) -> InvokeHarnessResponse:
            if request.harness_name not in self.agents:
                logger.error(
                    f"Harness with name {request.harness_name} does not exist."
                )
                return InvokeHarnessResponse(
                    harness_name=request.harness_name,
                    output=f"Harness with name {request.harness_name} does not exist. Please add it first.",
                )

            if request.harness:
                logger.info(
                    f"Temporarily create agent with once-time harness {request.harness}."
                )
                agent = self._create_agent(request.harness)
            else:
                agent = self.agents[request.harness_name]

            agent_runner = Runner(
                agent=agent,
                short_term_memory=self.short_term_memory,
                app_name=request.harness_name,
            )
            output = await agent_runner.run(
                messages=[request.prompt],
                user_id=request.run_agent_request.user_id,
                session_id=request.run_agent_request.session_id,
            )

            return InvokeHarnessResponse(
                harness_name=request.harness_name,
                overwrite=request.harness is not None,
                output=output,
            )

    def _create_skill_toolset(self, skills: list[str]) -> SkillToolset | None:
        # Pull each skill zip from the hub into a fresh /tmp/<timestamp> dir,
        # extract it, and load it as an ADK skill. Skills that fail to download
        # or load (e.g. a malformed SKILL.md name) are skipped with a warning so
        # the rest still load. Returns None if none loaded.
        base_dir = Path("/tmp") / formatted_timestamp()
        loaded_skills = []
        for skill in skills:
            try:
                loaded_skills.append(
                    load_skill_from_dir(_download_and_extract_skill(skill, base_dir))
                )
            except Exception as e:
                logger.warning(f"Skipping skill '{skill}': {e}")

        if not loaded_skills:
            logger.warning("No skills loaded successfully; skipping skill toolset.")
            return None
        return SkillToolset(skills=loaded_skills)

    def _create_agent(self, harness: Harness) -> Agent:
        from veadk.tools import get_builtin_tool

        tools = [get_builtin_tool(name) for name in _split_csv(harness.tools)]
        skills = _split_csv(harness.skills)
        if skills:
            logger.info(f"Loading skills {skills} for harness.")
            skill_toolset = self._create_skill_toolset(skills)
            if skill_toolset is not None:
                tools = tools + [skill_toolset]

        agent = Agent(
            name="temp_agent",
            model_name=harness.model_name,
            instruction=harness.system_prompt,
            tools=tools,
            runtime=harness.runtime,
        )
        return agent

    def serve(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        import uvicorn

        uvicorn.run(self.app, host=host, port=port)


if __name__ == "__main__":
    # Entry for `python -m veadk.cloud.harness_app` (e.g. the AgentKit runtime),
    # serving the API on 0.0.0.0:8000.
    HarnessApp().serve()
