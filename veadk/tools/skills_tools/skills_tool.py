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
import asyncio
import os
import shutil
import tempfile
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
from veadk.utils.misc import download_url_to_file

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

        return base_description

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
            # `_invoke_skill` does blocking disk and network I/O (skill
            # download). Awaiting it inline would stall the event loop for
            # every other session in the process.
            result = await asyncio.to_thread(
                self._invoke_skill, skill_name, tool_context
            )
            self._add_skill_span_attributes(span, skill_name, result)
            self._upload_skill_metrics(span, skill_name, result)
            return result

    def _invoke_skill(self, skill_name: str, tool_context: ToolContext) -> str:
        """Load and return the full content of a skill."""

        working_dir = get_session_path(session_id=tool_context.session.id)
        skill_dir = working_dir / "skills"
        cloud_provider = (os.getenv("CLOUD_PROVIDER") or "").lower()
        default_region = (
            "ap-southeast-1" if cloud_provider == "byteplus" else "cn-beijing"
        )
        region = (
            os.getenv("AGENTKIT_TOOL_REGION")
            or (os.getenv("REGION") if cloud_provider != "byteplus" else None)
            or default_region
        )

        if skill_name not in self.skills:
            # 1. Download skill from TOS if not found locally
            user_skill_dir = skill_dir / skill_name
            if not user_skill_dir.exists() or not user_skill_dir.is_dir():
                if cloud_provider == "vestack":
                    error_msg = f"Error: Skill '{skill_name}' not found locally or in skill space. Downloading from TOS_SKILLS_DIR is not supported in vestack environment."
                    logger.error(error_msg)
                    return error_msg

                # Try to download from TOS
                logger.info(
                    f"Skill '{skill_name}' not found locally or in skill space, attempting to download from TOS..."
                )

                try:
                    from veadk.integrations.ve_tos.ve_tos import VeTOS
                    from veadk.skills.utils import _get_cloud_credentials

                    access_key, secret_key, session_token = _get_cloud_credentials()

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
                    if Path(skill_name).name != skill_name or skill_name in {".", ".."}:
                        raise ValueError("Skill name must be a single directory name")
                    # Stage on the same filesystem as the destination. ZIPs never
                    # enter the public skill directory and are removed on failure too.
                    with tempfile.TemporaryDirectory(
                        prefix=".skill-install-", dir=working_dir
                    ) as temp:
                        stage = Path(temp)
                        save_path = stage / "package.zip"
                        logger.info(
                            f"Downloading skill '{skill_name}' (id={skill.id}, version={skill.version_id})"
                        )
                        self._download_space_archive(skill, save_path, region)
                        self._install_skill_archive(save_path, skill_dir, skill_name)
                    legacy_zip = skill_dir / f"{skill_name}.zip"
                    try:
                        legacy_zip.unlink(missing_ok=True)
                    except OSError as exc:
                        logger.warning(
                            f"Skill '{skill_name}' installed but legacy ZIP cleanup failed: {type(exc).__name__}"
                        )
                    logger.info(
                        f"Installed skill '{skill_name}' at {skill_dir / skill_name}; temporary ZIP cleaned"
                    )
                except Exception as exc:
                    logger.error(
                        f"Failed to install skill '{skill_name}': {type(exc).__name__}: {exc}"
                    )
                    return f"Error: Failed to install skill '{skill_name}': {exc}"

            else:
                # Refresh an existing link when a configured local source moves.
                skills_mount = Path(skill.path).resolve()
                skills_link = skill_dir / skill_name
                try:
                    if Path(skill_name).name != skill_name or skill_name in {".", ".."}:
                        raise ValueError("Skill name must be a single directory name")
                    if not skills_mount.is_dir():
                        raise FileNotFoundError(
                            "Configured local skill directory is missing"
                        )
                    if skills_link.exists() and not skills_link.is_symlink():
                        raise FileExistsError(
                            "Skill destination is not a managed symlink"
                        )
                    if (
                        not skills_link.is_symlink()
                        or skills_link.resolve() != skills_mount
                    ):
                        with tempfile.TemporaryDirectory(
                            prefix=".skill-link-", dir=working_dir
                        ) as temp:
                            staging = Path(temp) / "link"
                            staging.symlink_to(skills_mount)
                            os.replace(staging, skills_link)
                        logger.info(
                            "Updated local skill link: %s -> %s",
                            skills_link,
                            skills_mount,
                        )
                except Exception as exc:
                    logger.warning(
                        "Failed to link local skill '%s': %s",
                        skill_name,
                        type(exc).__name__,
                    )
                    return f"Error: Failed to link local skill '{skill_name}': {exc}"

        skill_file = self._find_skill_file(skill_dir, skill_name)
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

    def _download_space_archive(
        self, skill: Skill, save_path: Path, region: str
    ) -> None:
        skill_name = skill.name
        if skill.source_type == "skillhub":
            from veadk.skills.utils import download_skillhub_skill

            success = download_skillhub_skill(skill, save_path)
        else:
            from veadk.integrations.ve_tos.ve_tos import VeTOS
            from veadk.skills.utils import _get_cloud_credentials

            access_key, secret_key, session_token = _get_cloud_credentials()

            tos_bucket, tos_path = skill.bucket_name, skill.path

            cloud_provider = (os.getenv("CLOUD_PROVIDER") or "").lower()
            if cloud_provider == "vestack":
                success = self._download_skill_via_vestack(
                    skill=skill,
                    tos_path=tos_path,
                    cloud_provider=cloud_provider,
                    access_key=access_key,
                    secret_key=secret_key,
                    session_token=session_token,
                    skill_name=skill_name,
                    save_path=save_path,
                )
            else:
                # Initialize VeTOS client
                tos_client = VeTOS(
                    ak=access_key,
                    sk=secret_key,
                    session_token=session_token,
                    bucket_name=tos_bucket,
                    region=region,
                )

                success = tos_client.download(
                    bucket_name=tos_bucket,
                    object_key=tos_path,
                    save_path=save_path,
                )
        if not success:
            raise RuntimeError("Skill archive download failed")

    def _install_skill_archive(
        self, zip_path: Path, skill_dir: Path, skill_name: str
    ) -> None:
        extracted = zip_path.parent / "extracted"
        extracted.mkdir()
        self._safe_extract_zip(zip_path, extracted)
        root_readme = extracted / "SKILL.md"
        if root_readme.is_file():
            selected = root_readme
            layout = "root"
        else:
            candidates = sorted(
                (p for p in extracted.rglob("SKILL.md") if p.is_file()),
                key=lambda p: (len(p.relative_to(extracted).parts), str(p)),
            )
            if not candidates:
                raise ValueError("Skill archive has no SKILL.md file")
            selected = candidates[0]
            layout = (
                "wrapped"
                if len(selected.relative_to(extracted).parts) == 2
                else "nested fallback"
            )
            if len(candidates) > 1 or layout == "nested fallback":
                logger.warning(
                    f"Skill '{skill_name}' package fallback: {len(candidates)} SKILL.md candidates; "
                    f"selected {selected.relative_to(extracted)} by depth and path"
                )
        # Validate readability before moving the existing installation aside.
        selected.read_text(encoding="utf-8")
        logger.info(
            f"Skill '{skill_name}' package layout={layout}; selected={selected.relative_to(extracted)}; "
            f"destination={skill_dir / skill_name}"
        )
        target = skill_dir / skill_name
        backup_root = None
        if target.exists() or target.is_symlink():
            backup_root = Path(
                tempfile.mkdtemp(prefix=".skill-backup-", dir=skill_dir.parent)
            )
            try:
                target.rename(backup_root / "previous")
            except BaseException:
                backup_root.rmdir()
                raise
        try:
            selected.parent.rename(target)
        except BaseException:
            if backup_root is not None:
                try:
                    (backup_root / "previous").rename(target)
                except OSError:
                    logger.error(
                        f"Skill '{skill_name}' rollback failed; previous installation retained at {backup_root}"
                    )
                    raise
                backup_root.rmdir()
                logger.warning(
                    f"Skill '{skill_name}' installation failed; previous installation restored"
                )
            raise
        if backup_root is not None:
            try:
                shutil.rmtree(backup_root)
            except OSError as exc:
                logger.warning(
                    f"Skill '{skill_name}' installed but backup cleanup failed at {backup_root}: {type(exc).__name__}"
                )

    def _find_skill_file(self, skill_dir: Path, skill_name: str) -> Path:
        skill_root = skill_dir / skill_name
        skill_file = skill_root / "SKILL.md"
        if skill_file.exists():
            return skill_file

        if skill_root.exists():
            # Pick the shallowest SKILL.md to avoid matching nested examples,
            # and sort for deterministic results.
            nested_skill_files = sorted(
                skill_root.rglob("SKILL.md"),
                key=lambda p: (len(p.relative_to(skill_root).parts), str(p)),
            )
            if nested_skill_files:
                return nested_skill_files[0]

        return skill_file

    def _safe_extract_zip(self, zip_path: Path, dest_dir: Path) -> None:
        """Extract a zip archive while guarding against path traversal.

        Rejects any member whose resolved path would escape ``dest_dir``
        (e.g. absolute paths or paths containing ``..``).
        """
        import zipfile

        dest_root = Path(dest_dir).resolve()
        with zipfile.ZipFile(zip_path, "r") as z:
            for member in z.namelist():
                target = (dest_root / member).resolve()
                if target != dest_root and dest_root not in target.parents:
                    raise ValueError(f"Unsafe path detected in zip archive: '{member}'")
            z.extractall(path=str(dest_root))

    def _download_skill_via_vestack(
        self,
        skill: Any,
        tos_path: str,
        cloud_provider: str,
        access_key: str,
        secret_key: str,
        session_token: str,
        skill_name: str,
        save_path: Any,
    ) -> bool:
        """Download a skill using the vestack environment GenTempTosObjectDownloadUrl API."""
        import json
        from veadk.utils.volcengine_sign import ve_request

        # Extract skill_id and skill_version from TosPath
        # skills/s-yeh6iwdnggwobasystug/v1/web-search.zip
        skill_id = skill.id
        skill_version = ""
        try:
            path_parts = tos_path.split("/")
            if len(path_parts) >= 3:
                skill_id = path_parts[1]
                skill_version = path_parts[2]
        except Exception:
            pass

        # Call GenTempTosObjectDownloadUrl API
        temp_url_request_body = {
            "SkillId": skill_id,
            "SkillVersion": skill_version,
        }

        agentkit_tool_service = os.getenv("AGENTKIT_TOOL_SERVICE_CODE", "agentkit")
        default_region = (
            "ap-southeast-1" if cloud_provider == "byteplus" else "cn-beijing"
        )
        region = (
            os.getenv("AGENTKIT_TOOL_REGION")
            or (os.getenv("REGION") if cloud_provider != "byteplus" else None)
            or default_region
        )
        default_sld = "byteplusapi" if cloud_provider == "byteplus" else "volcengineapi"
        agentkit_skill_host = os.getenv(
            "AGENTKIT_SKILL_HOST",
            agentkit_tool_service + "." + region + f".{default_sld}.com",
        )
        scheme = os.getenv("AGENTKIT_TOP_SCHEME", "https").lower()

        temp_url_res = ve_request(
            request_body=temp_url_request_body,
            action="GenTempTosObjectDownloadUrl",
            ak=access_key,
            sk=secret_key,
            service=agentkit_tool_service,
            version="2025-10-30",
            region=region,
            host=agentkit_skill_host,
            header={"X-Security-Token": session_token},
            scheme=scheme,
        )

        if isinstance(temp_url_res, str):
            temp_url_res = json.loads(temp_url_res)

        if (
            "ResponseMetadata" in temp_url_res
            and "Error" in temp_url_res["ResponseMetadata"]
        ):
            error_details = temp_url_res["ResponseMetadata"]["Error"]
            logger.error(
                f"Failed to get temporary download URL for '{skill_name}': {error_details}"
            )
            return False
        else:
            signed_url = temp_url_res.get("Result", {}).get("SignedUrl")
            if not signed_url:
                logger.error(
                    f"Failed to get SignedUrl from GenTempTosObjectDownloadUrl response: {temp_url_res}"
                )
                return False
            else:
                try:
                    download_url_to_file(signed_url, save_path)
                    return True
                except Exception as e:
                    logger.error(
                        f"Failed to download skill '{skill_name}' from minio: {e}"
                    )
                    return False

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
            from veadk.tracing.telemetry import portal_metrics

            portal_metrics.portal_metric_recorder.record_skill_call(
                span,
                skill_name,
                self.name,
                self.skills.get(skill_name),
                result,
            )
        except Exception as e:
            logger.warning(f"Failed to upload skill metrics: {e}")
