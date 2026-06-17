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
from pathlib import Path
import os
import frontmatter
from typing import Literal

from google.adk.tools import BaseTool, ToolContext
from typing import Any, Dict, Optional, Callable

from veadk.skills.skill import Skill
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request, volcengine_signed_request

logger = get_logger(__name__)


def _build_state_key(*parts: str) -> str:
    return ":".join([part for part in parts if part])


def update_check_list(
    tool_context: ToolContext, skill_name: str, check_item: str, state: bool
):
    """
    Update the checklist item state for a specific skill.
    Use this tool to mark checklist items as completed during skill execution.

    eg:
    update_check_list(skill_name="skill-creator", check_item="analyze_content", state=True)
    """
    agent_name = tool_context.agent_name
    state_key = _build_state_key(agent_name, skill_name, "check_list", check_item)
    tool_context.state.update({state_key: state})
    logger.info(
        f"Updated agent[{agent_name}] skill[{skill_name}] check_list[{check_item}] state: {state}"
    )


def create_init_skill_check_list_callback(
    skills_with_checklist: Dict[str, Skill],
) -> Callable[[BaseTool, Dict[str, Any], ToolContext], Optional[Dict]]:
    """
    Create a callback function to initialize checklist when a skill is invoked.

    Args:
        skills_with_checklist: Dictionary mapping skill names to Skill objects

    Returns:
        A callback function for before_tool_callback
    """

    def init_skill_check_list(
        tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext
    ) -> Optional[Dict]:
        """Callback to initialize checklist when a skill is invoked."""
        if tool.name == "skills_tool":
            skill_name = args.get("command")
            agent_name = tool_context.agent_name
            if skill_name in skills_with_checklist:
                skill = skills_with_checklist[skill_name]
                check_list_items = skill.get_checklist_items()
                check_list_state = {
                    _build_state_key(agent_name, skill_name, "check_list", item): False
                    for item in check_list_items
                }
                tool_context.state.update(check_list_state)
                logger.info(
                    f"Initialized agent[{agent_name}] skill[{skill_name}] check_list: {check_list_state}"
                )
        return None

    return init_skill_check_list


def load_skill_from_directory(skill_directory: Path) -> Optional[Skill]:
    logger.info(f"Load skill from {skill_directory}")
    skill_readme = skill_directory / "SKILL.md"
    if not skill_readme.exists():
        logger.error(f"Skill '{skill_directory}' has no SKILL.md file.")
        return None

    try:
        skill = frontmatter.load(str(skill_readme))

        skill_name = skill.get("name", "")
        skill_description = skill.get("description", "")
        checklist = skill.get("checklist", [])

        if not skill_name or not skill_description:
            logger.error(
                f"Skill {skill_readme} is missing name or description. Please check the SKILL.md file."
            )
            return None

        logger.info(
            f"Successfully loaded skill {skill_name} locally from {skill_readme}, name={skill_name}, description={skill_description}"
        )
        if checklist:
            logger.info(f"Skill {skill_name} checklist: {checklist}")

        return Skill(
            name=skill_name,  # type: ignore
            description=skill_description,  # type: ignore
            path=str(skill_directory),
            checklist=checklist,
        )
    except Exception as e:
        logger.error(f"Failed to load skill from {skill_directory}: {e}")
        return None


def load_skills_from_directory(skills_directory: Path) -> list[Skill]:
    skills = []
    logger.info(f"Load skills from {skills_directory}")
    for skill_directory in skills_directory.iterdir():
        if skill_directory.is_dir():
            skill = load_skill_from_directory(skill_directory)
            if skill is not None:
                skills.append(skill)
    return skills


def load_skills_from_cloud(skill_space_ids: str) -> list[Skill]:
    skill_space_ids_list = [x.strip() for x in skill_space_ids.split(",") if x.strip()]
    logger.info(f"Load skills from cloud skill sources: {skill_space_ids_list}")

    skills = []

    for skill_space_id in skill_space_ids_list:
        # SkillHub space ids use the `sp-` prefix; all other ids keep the
        # legacy AgentKit skill-space behavior for backward compatibility.
        if skill_space_id.startswith("sp-"):
            skills.extend(_load_skills_from_skillhub_space_id(skill_space_id))
        else:
            skills.extend(_load_skills_from_space_id(skill_space_id))

    return skills


def _get_cloud_credentials() -> tuple[str, str, str]:
    from veadk.auth.veauth.utils import get_credential_from_vefaas_iam

    access_key = os.getenv("VOLCENGINE_ACCESS_KEY")
    secret_key = os.getenv("VOLCENGINE_SECRET_KEY")
    session_token = os.getenv("VOLCENGINE_SESSION_TOKEN", "")

    if not (access_key and secret_key):
        cred = get_credential_from_vefaas_iam()
        access_key = cred.access_key_id
        secret_key = cred.secret_access_key
        session_token = cred.session_token

    return access_key, secret_key, session_token


def _get_agentkit_endpoint() -> tuple[str, str, str]:
    service = os.getenv("AGENTKIT_TOOL_SERVICE_CODE", "agentkit")

    provider = (os.getenv("CLOUD_PROVIDER") or "").lower()
    if provider == "byteplus":
        sld = "byteplusapi"
        default_region = "ap-southeast-1"
    else:
        sld = "volcengineapi"
        default_region = "cn-beijing"

    region = os.getenv("AGENTKIT_TOOL_REGION", default_region)
    host = os.getenv("AGENTKIT_SKILL_HOST", service + "." + region + f".{sld}.com")
    return service, region, host


def _get_skillhub_endpoint() -> tuple[str, str, str]:
    service = os.getenv("SKILLHUB_SERVICE_NAME", "skillhub")
    region = os.getenv("SKILLHUB_REGION", "cn-guilin-boe")
    host = os.getenv("SKILLHUB_HOST", "skills.volces.com")
    return service, region, host


def _extract_items(response: Any) -> list[Any]:
    if isinstance(response, str):
        response = json.loads(response)

    if not isinstance(response, dict):
        return []

    result = response.get("Result")
    if isinstance(result, dict):
        items = result.get("Items", [])
    else:
        items = response.get("Items", [])

    return items if isinstance(items, list) else []


def _build_skill_from_space_item(
    item: dict[str, Any], skill_space_id: str
) -> Optional[Skill]:
    skill_name = item.get("Name")
    if not skill_name:
        return None

    return Skill(
        name=skill_name,
        description=item.get("Description") or "",
        path=item.get("TosPath") or "",
        skill_space_id=skill_space_id,
        bucket_name=item.get("BucketName"),
        id=item.get("SkillId"),
    )


def _build_skill_from_skillhub_item(
    item: dict[str, Any], skill_space_id: str
) -> Optional[Skill]:
    skill_name = item.get("Name")
    skill_id = item.get("Id") or item.get("SkillId")
    if not skill_name or not skill_id:
        return None

    metadata = item.get("Metadata") if isinstance(item.get("Metadata"), dict) else {}
    related_version = (
        item.get("RelatedSkillVersion")
        if isinstance(item.get("RelatedSkillVersion"), dict)
        else {}
    )
    latest_version = (
        item.get("LatestVersionStatus")
        if isinstance(item.get("LatestVersionStatus"), dict)
        else {}
    )
    version_id = related_version.get("Id") or latest_version.get("VersionId")
    slug = item.get("Slug")

    return Skill(
        name=skill_name,
        description=metadata.get("DisplayDescription") or item.get("Description", ""),
        path=slug or skill_id,
        skill_space_id=skill_space_id,
        id=skill_id,
        slug=slug,
        source_type="skillhub",
        version_id=version_id,
    )


def _load_skills_from_space_id(skill_space_id: str) -> list[Skill]:
    logger.info(f"Load skills from skill space: {skill_space_id}")

    skills = []

    try:
        service, region, host = _get_agentkit_endpoint()
        access_key, secret_key, session_token = _get_cloud_credentials()

        request_body = {
            "SkillSpaceId": skill_space_id,
            "InnerTags": {"source": "sandbox"},
        }
        logger.debug(f"ListSkillsBySpaceId request body: {request_body}")
        scheme = os.getenv("AGENTKIT_TOP_SCHEME", "https").lower()

        response = ve_request(
            request_body=request_body,
            action="ListSkillsBySpaceId",
            ak=access_key,
            sk=secret_key,
            service=service,
            version="2025-10-30",
            region=region,
            host=host,
            header={"X-Security-Token": session_token},
            scheme=scheme,  # type: ignore[arg-type]
        )

        items = _extract_items(response)
        if not items:
            logger.warning(
                f"No skills returned from skill space={skill_space_id}. "
                f"Response may be empty or the space has no skills."
            )

        for item in items:
            if not isinstance(item, dict):
                continue
            skill = _build_skill_from_space_item(item, skill_space_id)
            if skill is None:
                continue

            skills.append(skill)

            logger.info(
                f"Successfully loaded skill {skill.name} from skill space={skill_space_id}, name={skill.name}, description={skill.description}"
            )
    except Exception as e:
        logger.error(
            f"Failed to load skills from skill space={skill_space_id}: {e}"
        )

    return skills


def _skillhub_request(
    path: str,
    request_body: dict[str, Any],
    response_type: Literal["json", "content"] = "json",
):
    access_key, secret_key, session_token = _get_cloud_credentials()
    service, region, host = _get_skillhub_endpoint()
    scheme = os.getenv("SKILLHUB_TOP_SCHEME", "https").lower()
    header = {"X-Security-Token": session_token}

    return volcengine_signed_request(
        request_body=request_body,
        ak=access_key,
        sk=secret_key,
        service=service,
        region=region,
        host=host,
        path=path,
        header=header,
        scheme=scheme,  # type: ignore[arg-type]
        # SkillHub follows the ve-skills-js-sdk signing flow: the request body is
        # sent normally, but the signed payload hash is the literal
        # "UNSIGNED-PAYLOAD".
        unsigned_payload=True,
        response_type=response_type,
    )


def _get_skillhub_page_size(default: int = 100) -> int:
    raw = os.getenv("SKILLHUB_LIST_SKILLS_PAGE_SIZE")
    if not raw:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            f"Invalid SKILLHUB_LIST_SKILLS_PAGE_SIZE={raw!r}, fallback to {default}."
        )
        return default
    if value <= 0:
        logger.warning(
            f"Non-positive SKILLHUB_LIST_SKILLS_PAGE_SIZE={value}, fallback to {default}."
        )
        return default
    return value


def _load_skills_from_skillhub_space_id(skill_space_id: str) -> list[Skill]:
    logger.info(f"Load skills from SkillHub skill space: {skill_space_id}")

    skills = []

    try:
        page_number = 1
        page_size = _get_skillhub_page_size()
        total_count: Optional[int] = None

        # ListSkills is paginated. Keep fetching until the server-reported
        # TotalCount is satisfied, or until a page returns no Items.
        while total_count is None or len(skills) < total_count:
            request_body = {
                "PageNumber": page_number,
                "PageSize": page_size,
                "Filter": {"SkillSpaceId": skill_space_id},
            }
            logger.debug(f"SkillHub ListSkills request body: {request_body}")
            response = _skillhub_request("/ListSkills", request_body)

            if isinstance(response, str):
                response = json.loads(response)
            if not isinstance(response, dict):
                logger.warning(
                    f"Unexpected SkillHub ListSkills response for skill space={skill_space_id}: {response}"
                )
                break

            if total_count is None:
                raw_total_count = response.get("TotalCount")
                if raw_total_count is None and isinstance(response.get("Result"), dict):
                    raw_total_count = response["Result"].get("TotalCount")
                if raw_total_count is not None:
                    try:
                        total_count = int(raw_total_count)
                    except (TypeError, ValueError):
                        logger.warning(
                            f"Invalid SkillHub TotalCount={raw_total_count!r} for skill space={skill_space_id}."
                        )
                        total_count = None

            items = _extract_items(response)
            if not items:
                if page_number == 1:
                    logger.warning(
                        f"No skills returned from SkillHub skill space={skill_space_id}. "
                        f"Response may be empty or the space has no skills."
                    )
                break

            loaded_count_before_page = len(skills)
            for item in items:
                if not isinstance(item, dict):
                    continue
                skill = _build_skill_from_skillhub_item(item, skill_space_id)
                if skill is None:
                    continue

                skills.append(skill)
                logger.info(
                    f"Successfully loaded SkillHub skill {skill.name} from skill space={skill_space_id}, id={skill.id}, slug={skill.slug}"
                )

            if len(skills) == loaded_count_before_page:
                logger.warning(
                    f"SkillHub page {page_number} for skill space={skill_space_id} contained no valid skills."
                )

            page_number += 1
    except Exception as e:
        logger.error(f"Failed to load skills from SkillHub skill space: {e}")

    return skills


def download_skillhub_skill(skill: Skill, save_path: Path) -> bool:
    if not skill.id:
        logger.error(f"SkillHub skill '{skill.name}' has no skill id.")
        return False

    request_body: dict[str, Any] = {
        "SkillId": skill.id,
        "IsPreview": True,
    }
    if skill.version_id:
        request_body["SkillVersionId"] = skill.version_id

    try:
        content = _skillhub_request(
            "/DownloadSkill",
            request_body,
            response_type="content",
        )
        if not isinstance(content, (bytes, bytearray)) or not content:
            logger.error(f"DownloadSkill returned empty content for '{skill.name}'.")
            return False

        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error(f"Failed to download SkillHub skill '{skill.name}': {e}")
        return False
