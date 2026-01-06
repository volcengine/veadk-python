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

import json
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from google.adk.tools import BaseTool, ToolContext
from google.genai import types

from veadk.utils.volcengine_sign import ve_request
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class SkillsTool(BaseTool):
    """Discover and load skill instructions.

    This tool dynamically discovers available skills and embeds their metadata in the
    tool description. Agent invokes a skill by name to load its full instructions.
    """

    def __init__(self, skills_directory: str | Path, skills_space_name: Optional[str]):
        self.skills_directory = Path(skills_directory).resolve()
        if not self.skills_directory.exists():
            raise ValueError(
                f"Skills directory does not exist: {self.skills_directory}"
            )

        self.skills_space_name = skills_space_name

        self._skill_cache: Dict[str, str] = {}

        # Generate description with available skills embedded
        description = self._generate_description_with_skills()

        super().__init__(
            name="skills",
            description=description,
        )

    def _generate_description_with_skills(self) -> str:
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
            "- Avaliable skills listed in <available_skills> below\n"
            "- If the invoked skills are not in the available skills, this tool will automatically download these skills from the remote object storage bucket."
            "- Do not invoke a skill that is already loaded in the conversation\n"
            "- After loading a skill, use the bash tool for execution\n"
            "- If not specified, scripts are located in the skill-name/scripts subdirectory\n"
            "</skills_instructions>\n\n"
        )

        # Discover and append available skills
        skills_xml = self._discover_skills()
        return base_description + skills_xml

    def _discover_skills(self) -> str:
        """Discover available skills and format as XML."""

        skills_entries = []

        # Discover skills from local directory
        if self.skills_directory.exists():
            for skill_dir in sorted(self.skills_directory.iterdir()):
                if not skill_dir.is_dir():
                    continue

                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    continue

                try:
                    metadata = self._parse_skill_metadata(skill_file)
                    if metadata:
                        skill_xml = (
                            "<skill>\n"
                            f"<name>{metadata['name']}</name>\n"
                            f"<description>{metadata['description']}</description>\n"
                            "</skill>"
                        )
                        skills_entries.append(skill_xml)
                except Exception as e:
                    logger.error(f"Failed to parse skill {skill_dir.name}: {e}")

        # Discover skills from remote skill space
        if self.skills_space_name:
            try:
                from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
                import os

                service = os.getenv("AGENTKIT_TOOL_SERVICE_CODE", "agentkit")
                region = os.getenv("AGENTKIT_TOOL_REGION", "cn-beijing")
                host = os.getenv("AGENTKIT_SKILL_HOST", "open.volcengineapi.com")
                if not host:
                    raise RuntimeError(
                        "AGENTKIT_SKILL_HOST is not set; please provide it via environment variables"
                    )

                access_key = os.getenv("VOLCENGINE_ACCESS_KEY")
                secret_key = os.getenv("VOLCENGINE_SECRET_KEY")
                session_token = ""

                if not (access_key and secret_key):
                    # Try to get from vefaas iam
                    cred = get_credential_from_vefaas_iam()
                    access_key = cred.access_key_id
                    secret_key = cred.secret_access_key
                    session_token = cred.session_token

                response = ve_request(
                    request_body={"SkillSpaceName": self.skills_space_name},
                    action="ListSkillsBySpaceName",
                    ak=access_key,
                    sk=secret_key,
                    service=service,
                    version="2025-10-30",
                    region=region,
                    host=host,
                    header={"X-Security-Token": session_token},
                )

                if isinstance(response, str):
                    response = json.loads(response)

                result = response.get("Result")
                items = result.get("Items")

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("Name")
                    description = item.get("Description")
                    if not name:
                        continue
                    skill_xml = (
                        "<skill>\n"
                        f"<name>{name}</name>\n"
                        f"<description>{description}</description>\n"
                        "</skill>"
                    )
                    skills_entries.append(skill_xml)

            except Exception as e:
                logger.error(f"Failed to discover skill from skill space: {e}")

        if not skills_entries:
            return "<available_skills>\n<!-- No skills found in skills directory and skill space -->\n</available_skills>\n"

        return (
            "<available_skills>\n"
            + "\n".join(skills_entries)
            + "\n</available_skills>\n"
        )

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

        return self._invoke_skill(skill_name)

    def _invoke_skill(self, skill_name: str) -> str:
        """Load and return the full content of a skill."""
        # Check cache first
        if skill_name in self._skill_cache:
            return self._skill_cache[skill_name]

        # Find skill directory
        skill_dir = self.skills_directory / skill_name
        if not skill_dir.exists() or not skill_dir.is_dir() and self.skills_space_name:
            # Try to download from skill space
            logger.info(
                f"Skill '{skill_name}' not found locally, attempting to download from skill space"
            )

            try:
                from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
                from veadk.integrations.ve_tos.ve_tos import VeTOS
                import os

                service = os.getenv("AGENTKIT_TOOL_SERVICE_CODE", "agentkit")
                region = os.getenv("AGENTKIT_TOOL_REGION", "cn-beijing")
                host = os.getenv("AGENTKIT_SKILL_HOST", "open.volcengineapi.com")
                if not host:
                    raise RuntimeError(
                        "AGENTKIT_SKILL_HOST is not set; please provide it via environment variables"
                    )

                access_key = os.getenv("VOLCENGINE_ACCESS_KEY")
                secret_key = os.getenv("VOLCENGINE_SECRET_KEY")
                session_token = ""

                if not (access_key and secret_key):
                    # Try to get from vefaas iam
                    cred = get_credential_from_vefaas_iam()
                    access_key = cred.access_key_id
                    secret_key = cred.secret_access_key
                    session_token = cred.session_token

                response = ve_request(
                    request_body={
                        "SkillSpaceName": self.skills_space_name,
                        "SkillName": skill_name,
                    },
                    action="GetSkillInfo",
                    ak=access_key,
                    sk=secret_key,
                    service=service,
                    version="2025-10-30",
                    region=region,
                    host=host,
                    header={"X-Security-Token": session_token},
                )

                if isinstance(response, str):
                    response = json.loads(response)

                result = response.get("Result")

                tos_bucket, tos_path = result["BucketName"], result["TosPath"]

                # Initialize VeTOS client
                tos_client = VeTOS(
                    ak=access_key,
                    sk=secret_key,
                    session_token=session_token,
                    bucket_name=tos_bucket,
                )

                save_path = skill_dir.parent / f"{skill_dir.name}.zip"

                success = tos_client.download(
                    bucket_name=tos_bucket,
                    object_key=tos_path,
                    save_path=save_path,
                )

                if not success:
                    return f"Error: Failed to download skill '{skill_name}' from TOS."

                # Extract downloaded zip into the skill directory
                import zipfile

                skill_dir.parent.mkdir(parents=True, exist_ok=True)

                try:
                    with zipfile.ZipFile(save_path, "r") as z:
                        z.extractall(path=str(skill_dir.parent))
                except Exception as e:
                    logger.error(f"Failed to extract skill zip for '{skill_name}': {e}")
                    return (
                        f"Error: Failed to extract skill '{skill_name}' from zip: {e}"
                    )

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

        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            return f"Error: Skill '{skill_name}' has no SKILL.md file."

        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                content = f.read()

            formatted_content = self._format_skill_content(skill_name, content)

            # Cache the formatted content
            self._skill_cache[skill_name] = formatted_content

            logger.info(f"Loaded skill '{skill_name}' successfully.")
            return formatted_content

        except Exception as e:
            logger.error(f"Failed to load skill {skill_name}: {e}")
            return f"Error loading skill '{skill_name}': {e}"

    def _parse_skill_metadata(self, skill_file: Path) -> Dict[str, str] | None:
        """Parse YAML frontmatter from a SKILL.md file."""
        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.startswith("---"):
                return None

            parts = content.split("---", 2)
            if len(parts) < 3:
                return None

            metadata = yaml.safe_load(parts[1])
            if (
                isinstance(metadata, dict)
                and "name" in metadata
                and "description" in metadata
            ):
                return {
                    "name": metadata["name"],
                    "description": metadata["description"],
                }
            return None
        except Exception as e:
            logger.error(f"Failed to parse metadata from {skill_file}: {e}")
            return None

    def _format_skill_content(self, skill_name: str, content: str) -> str:
        """Format skill content for display to the agent."""
        header = (
            f'<command-message>The "{skill_name}" skill is loading</command-message>\n\n'
            f"Base directory for this skill: {self.skills_directory}/{skill_name}\n\n"
        )
        footer = (
            "\n\n---\n"
            "The skill has been loaded. Follow the instructions above and use the bash tool to execute commands."
        )
        return header + content + footer
