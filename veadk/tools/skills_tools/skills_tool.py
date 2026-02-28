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

from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict

from google.adk.tools import BaseTool, ToolContext
from google.genai import types
from opentelemetry import trace
from opentelemetry.sdk.trace import _Span
from opentelemetry.trace.status import Status, StatusCode

from veadk.skills.skill import Skill
from veadk.tools.skills_tools.session_path import get_session_path
from veadk.tracing.telemetry.telemetry import set_common_attributes_on_tool_span
from veadk.utils.logger import get_logger

tracer = trace.get_tracer("veadk.skills_tool")

logger = get_logger(__name__)


class SkillsTool(BaseTool):
    """Discover and load skill instructions.

    This tool dynamically discovers available skills and embeds their metadata in the
    tool description. Agent invokes a skill by name to load its full instructions.
    """

    def __init__(self, skills: Dict[str, Skill]):
        self.skills = skills

        # Generate description with available skills embedded
        description = self._generate_description()

        super().__init__(
            name="skills_tool",
            description=description,
        )

    def _generate_description(self) -> str:
        """Generate tool description with available skills embedded."""
        base_description = (
            "Execute a skill within the main conversation\n\n"
            "<skills_instructions>\n"
            "When users ask you to perform tasks, check if any of the available skills below can help "
            "complete the task more effectively. Skills provide specialized capabilities and domain knowledge.\n\n"
            "How to use skills:\n"
            "- Invoke skills using this tool with the skill name only (no arguments)\n"
            "- When you invoke a skill, the skill's full SKILL.md will load with detailed instructions\n"
            "- Follow the skill's instructions and use the bash tool to execute commands\n"
            "- Examples:\n"
            '  - command: "data-analysis" - invoke the data-analysis skill\n'
            '  - command: "pdf-processing" - invoke the pdf-processing skill\n\n'
            "Important:\n"
            "- If the invoked skills are not in the available skills, this tool will automatically download these skills from the remote object storage bucket\n"
            "- Do not invoke a skill that is already loaded in the conversation\n"
            "- After loading a skill, use the bash tool for execution\n"
            "- If not specified, scripts are located in the skill-name/scripts subdirectory\n"
            "</skills_instructions>\n\n"
        )

        available_skills_description = "<available_skills>\n"
        for skill_name, skill in self.skills.items():
            available_skills_description += (
                f"  <skill>\n"
                f"    <name>{skill_name}</name>\n"
                f"    <description>{skill.description}</description>\n"
                f"  </skill>\n"
            )
        available_skills_description += "</available_skills>"

        return base_description + available_skills_description

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "command": types.Schema(
                        type=types.Type.STRING,
                        description='The skill name (no arguments). E.g., "data-analysis" or "pdf-processing"',
                    ),
                },
                required=["command"],
            ),
        )

    async def run_async(
        self, *, args: Dict[str, Any], tool_context: ToolContext
    ) -> str:
        """Execute skill loading by name."""
        skill_name = args.get("command", "").strip()

        if not skill_name:
            return "Error: No skill name provided"

        with tracer.start_as_current_span(f"execute_skill {skill_name}") as span:
            result = self._invoke_skill(skill_name, tool_context)
            self._add_skill_span_attributes(span, skill_name, result)
            self._upload_skill_metrics(span, skill_name, result)
            return result

    def _invoke_skill(self, skill_name: str, tool_context: ToolContext) -> str:
        """Load and return the full content of a skill."""

        working_dir = get_session_path(session_id=tool_context.session.id)
        skill_dir = working_dir / "skills"
        region = os.getenv("AGENTKIT_TOOL_REGION", "cn-beijing")

        if skill_name not in self.skills:
            # 1. Download skill from TOS if not found locally
            user_skill_dir = skill_dir / skill_name
            if not user_skill_dir.exists() or not user_skill_dir.is_dir():
                # Try to download from TOS
                logger.info(
                    f"Skill '{skill_name}' not found locally or in skill space, attempting to download from TOS..."
                )

                try:
                    from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
                    from veadk.integrations.ve_tos.ve_tos import VeTOS

                    access_key = os.getenv("VOLCENGINE_ACCESS_KEY")
                    secret_key = os.getenv("VOLCENGINE_SECRET_KEY")
                    session_token = ""

                    if not (access_key and secret_key):
                        # Try to get from vefaas iam
                        cred = get_credential_from_vefaas_iam()
                        access_key = cred.access_key_id
                        secret_key = cred.secret_access_key
                        session_token = cred.session_token

                    tos_skills_dir = os.getenv(
                        "TOS_SKILLS_DIR"
                    )  # e.g. tos://agentkit-skills/skills/

                    # Parse bucket and prefix from TOS_SKILLS_DIR
                    if not tos_skills_dir:
                        error_msg = (
                            f"Error: TOS_SKILLS_DIR environment variable is not set. "
                            f"Cannot download skill '{skill_name}' from TOS. "
                            f"Please set TOS_SKILLS_DIR"
                        )
                        logger.error(error_msg)
                        return error_msg

                    # Validate TOS_SKILLS_DIR format
                    if not tos_skills_dir.startswith("tos://"):
                        error_msg = (
                            f"Error: TOS_SKILLS_DIR format is invalid: '{tos_skills_dir}'. "
                            f"Expected format: tos://agentkit-platform-xxxxxx/skills/ "
                            f"Cannot download skill '{skill_name}'."
                        )
                        logger.error(error_msg)
                        return error_msg

                    # Parse bucket and prefix from TOS_SKILLS_DIR
                    # Remove "tos://" prefix and split by first "/"
                    path_without_protocol = tos_skills_dir[6:]  # Remove "tos://"

                    if "/" not in path_without_protocol:
                        # Only bucket name, no path
                        tos_bucket = path_without_protocol.rstrip("/")
                        tos_prefix = skill_name
                    else:
                        # Split bucket and path
                        first_slash_idx = path_without_protocol.index("/")
                        tos_bucket = path_without_protocol[:first_slash_idx]
                        base_path = path_without_protocol[first_slash_idx + 1 :].rstrip(
                            "/"
                        )

                        # Combine base path with skill name
                        if base_path:
                            tos_prefix = f"{base_path}/{skill_name}"
                        else:
                            tos_prefix = skill_name

                    logger.info(
                        f"Parsed TOS location - Bucket: {tos_bucket}, Prefix: {tos_prefix}"
                    )

                    # Initialize VeTOS client
                    tos_client = VeTOS(
                        ak=access_key,
                        sk=secret_key,
                        session_token=session_token,
                        bucket_name=tos_bucket,
                        region=region,
                    )

                    # Download the skill directory from TOS
                    success = tos_client.download_directory(
                        bucket_name=tos_bucket,
                        prefix=tos_prefix,
                        local_dir=str(user_skill_dir),
                    )

                    if not success:
                        return f"Error: Skill '{skill_name}' not found in TOS: {tos_bucket}/{tos_prefix}."

                    logger.info(
                        f"Successfully downloaded skill '{skill_name}' from TOS: {tos_bucket}/{tos_prefix}."
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to download skill '{skill_name}' from TOS: {e}"
                    )
                    return f"Error: Skill '{skill_name}' not found locally or in the skill space, and it failed to download from TOS: {e}."
        else:
            skill = self.skills[skill_name]

            if skill.skill_space_id:
                # 2. Download skill from skill space if not found locally
                logger.info(
                    f"Attempting to download skill '{skill_name}' from skill space..."
                )
                try:
                    from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
                    from veadk.integrations.ve_tos.ve_tos import VeTOS

                    access_key = os.getenv("VOLCENGINE_ACCESS_KEY")
                    secret_key = os.getenv("VOLCENGINE_SECRET_KEY")
                    session_token = ""

                    if not (access_key and secret_key):
                        # Try to get from vefaas iam
                        cred = get_credential_from_vefaas_iam()
                        access_key = cred.access_key_id
                        secret_key = cred.secret_access_key
                        session_token = cred.session_token

                    tos_bucket, tos_path = skill.bucket_name, skill.path

                    # Initialize VeTOS client
                    tos_client = VeTOS(
                        ak=access_key,
                        sk=secret_key,
                        session_token=session_token,
                        bucket_name=tos_bucket,
                        region=region,
                    )

                    save_path = skill_dir / f"{skill_name}.zip"

                    success = tos_client.download(
                        bucket_name=tos_bucket,
                        object_key=tos_path,
                        save_path=save_path,
                    )

                    if not success:
                        return (
                            f"Error: Failed to download skill '{skill_name}' from TOS."
                        )

                    # Extract downloaded zip into the skill directory
                    import zipfile
                    import shutil

                    # Remove existing skill directory to ensure clean extraction
                    target_skill_dir = skill_dir / skill_name
                    if target_skill_dir.exists():
                        try:
                            shutil.rmtree(target_skill_dir)
                            logger.info(
                                f"Removed existing skill directory: {target_skill_dir}"
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to remove existing skill directory {target_skill_dir}: {e}"
                            )

                    try:
                        with zipfile.ZipFile(save_path, "r") as z:
                            z.extractall(path=str(skill_dir))
                    except zipfile.BadZipFile:
                        logger.error(
                            f"Downloaded file for '{skill_name}' is not a valid zip"
                        )
                        return f"Error: Downloaded file for skill '{skill_name}' is not a valid zip archive."
                    except Exception as e:
                        logger.error(
                            f"Failed to extract skill zip for '{skill_name}': {e}"
                        )
                        return f"Error: Failed to extract skill '{skill_name}' from zip: {e}"

                    logger.info(
                        f"Successfully downloaded skill '{skill_name}' from skill space"
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to download skill '{skill_name}' from skill space: {e}"
                    )
                    return (
                        f"Error: Skill '{skill_name}' not found locally and failed to download from skill space: {e}. "
                        f"Check the available skills list in the tool description."
                    )
            else:
                # 3. Use the local skill
                # Create symlink to skills directory
                skills_mount = Path(skill.path)
                skills_link = skill_dir / skill_name
                if skills_mount.exists() and not skills_link.exists():
                    try:
                        skills_link.symlink_to(skills_mount)
                        logger.debug(
                            f"Created symlink: {skills_link} -> {skills_mount}"
                        )
                    except FileExistsError:
                        # Symlink already exists (race condition from concurrent session setup)
                        pass
                    except Exception as e:
                        # Log but don't fail - skills can still be accessed via absolute path
                        logger.warning(
                            f"Failed to create skills symlink for {str(skills_mount)}: {e}"
                        )

        skill_file = skill_dir / skill_name / "SKILL.md"
        if not skill_file.exists():
            return f"Error: Skill '{skill_name}' has no SKILL.md file."

        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                content = f.read()

            formatted_content = self._format_skill_content(
                skill_name, content, str(skill_dir)
            )

            logger.info(f"Invoke skill '{skill_name}' successfully.")
            return formatted_content

        except Exception as e:
            logger.error(f"Failed to invoke skill {skill_name}: {e}")
            return f"Error invoking skill '{skill_name}': {e}"

    def _format_skill_content(self, skill_name: str, content: str, skill_dir) -> str:
        """Format skill content for display to the agent."""
        header = (
            f'<command-message>The "{skill_name}" skill is loading</command-message>\n\n'
            f"Base directory for this skill: {skill_dir}/{skill_name}\n\n"
        )
        footer = (
            "\n\n---\n"
            "The skill has been loaded. Follow the instructions above and use the bash tool to execute commands."
        )
        return header + content + footer

    def _add_skill_span_attributes(
        self,
        span: _Span,
        skill_name: str,
        result: str,
    ) -> None:
        """Add attributes to the skill execution span."""
        try:
            set_common_attributes_on_tool_span(current_span=span)

            if result:
                if result.startswith("Error:"):
                    span.set_status(Status(StatusCode.ERROR, result))

            span.set_attribute("skill.name", skill_name)
            span.set_attribute("tool.name", self.name)
            span.set_attribute("gen_ai.operation.name", "execute_skill")
            span.set_attribute("gen_ai.span.kind", "tool")
            if skill_name in self.skills:
                skill = self.skills[skill_name]
                if hasattr(skill, "skill_space_id") and skill.skill_space_id:
                    span.set_attribute("skill.space_id", skill.skill_space_id)
                if hasattr(skill, "bucket_name") and skill.bucket_name:
                    span.set_attribute("skill.bucket_name", skill.bucket_name)
                if hasattr(skill, "path") and skill.path:
                    span.set_attribute("skill.path", skill.path)
                if hasattr(skill, "id") and skill.id:
                    span.set_attribute("skill.id", skill.id)
            logger.debug(f"Added skill span attributes for {skill_name}")
        except Exception as e:
            logger.warning(f"Failed to add skill span attributes: {e}")

    def _upload_skill_metrics(self, span: _Span, skill_name: str, result: str) -> None:
        """Upload skill metrics to the telemetry system."""
        try:
            import time
            from veadk.tracing.telemetry.telemetry import meter_uploader

            if meter_uploader:
                # 初始化属性，包含技能相关信息
                skill = self.skills.get(skill_name)
                attributes = {
                    "skill_name": skill_name,
                    "tool_name": self.name,
                    "skill_space_id": (
                        skill.skill_space_id if skill and skill.skill_space_id else ""
                    ),
                    "skill_id": skill.id if skill and skill.id else "",
                    "gen_ai.operation.name": "execute_skill",
                    "error_type": (
                        "skill_execution_error" if result.startswith("Error:") else ""
                    ),
                }

                # 计算 span 执行耗时（秒）
                latency_seconds = 0
                if hasattr(span, "start_time"):
                    # 计算耗时（秒）
                    latency_seconds = (time.time_ns() - span.start_time) / 1e9  # type: ignore

                # 记录技能执行延迟
                if hasattr(meter_uploader, "skill_invoke_latency"):
                    # 使用 skill_invoke_latency 记录技能执行延迟（秒）
                    meter_uploader.skill_invoke_latency.record(
                        latency_seconds, attributes
                    )
                    logger.debug(
                        f"Uploaded skill metrics for {skill_name} with latency {latency_seconds:.4f}s and attributes {attributes}"
                    )
        except Exception as e:
            logger.warning(f"Failed to upload skill metrics: {e}")
