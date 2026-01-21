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

from veadk.skills.skill import Skill
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)


def load_skill_from_directory(skill_directory: Path) -> Skill:
    logger.info(f"Load skill from {skill_directory}")
    skill_readme = skill_directory / "SKILL.md"
    if not skill_readme.exists():
        logger.error(f"Skill '{skill_directory}' has no SKILL.md file.")
        raise ValueError(f"Skill '{skill_directory}' has no SKILL.md file")

    skill = frontmatter.load(str(skill_readme))

    skill_name = skill.get("name", "")
    skill_description = skill.get("description", "")

    if not skill_name or not skill_description:
        logger.error(
            f"Skill {skill_readme} is missing name or description. Please check the SKILL.md file."
        )
        raise ValueError(
            f"Skill {skill_readme} is missing name or description. Please check the SKILL.md file."
        )

    logger.info(
        f"Successfully loaded skill {skill_name} locally from {skill_readme}, name={skill_name}, description={skill_description}"
    )
    return Skill(
        name=skill_name,  # type: ignore
        description=skill_description,  # type: ignore
        path=str(skill_directory),
    )


def load_skills_from_directory(skills_directory: Path) -> list[Skill]:
    skills = []
    logger.info(f"Load skills from {skills_directory}")
    for skill_directory in skills_directory.iterdir():
        if skill_directory.is_dir():
            skill = load_skill_from_directory(skill_directory)
            skills.append(skill)
    return skills


def load_skills_from_cloud(skill_space_ids: str) -> list[Skill]:
    skill_space_ids_list = [x.strip() for x in skill_space_ids.split(",")]
    logger.info(f"Load skills from skill spaces: {skill_space_ids_list}")

    from veadk.auth.veauth.utils import get_credential_from_vefaas_iam

    skills = []

    for skill_space_id in skill_space_ids_list:
        try:
            service = os.getenv("AGENTKIT_TOOL_SERVICE_CODE", "agentkit")
            region = os.getenv("AGENTKIT_TOOL_REGION", "cn-beijing")
            host = os.getenv("AGENTKIT_SKILL_HOST", "open.volcengineapi.com")

            access_key = os.getenv("VOLCENGINE_ACCESS_KEY")
            secret_key = os.getenv("VOLCENGINE_SECRET_KEY")
            session_token = ""

            if not (access_key and secret_key):
                # Try to get from vefaas iam
                cred = get_credential_from_vefaas_iam()
                access_key = cred.access_key_id
                secret_key = cred.secret_access_key
                session_token = cred.session_token

            request_body = {
                "SkillSpaceId": skill_space_id,
                "InnerTags": {"source": "sandbox"},
            }
            logger.debug(f"ListSkillsBySpaceId request body: {request_body}")

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
            )

            if isinstance(response, str):
                response = json.loads(response)

            list_skills_result = response.get("Result")
            items = list_skills_result.get("Items")

            for item in items:
                if not isinstance(item, dict):
                    continue
                skill_name = item.get("Name")
                skill_description = item.get("Description")
                tos_bucket = item.get("BucketName")
                tos_path = item.get("TosPath")
                if not skill_name:
                    continue

                skill = Skill(
                    name=skill_name,  # type: ignore
                    description=skill_description,  # type: ignore
                    path=tos_path,
                    skill_space_id=skill_space_id,
                    bucket_name=tos_bucket,
                )

                skills.append(skill)

                logger.info(
                    f"Successfully loaded skill {skill_name} from skill space={skill_space_id}, name={skill_name}, description={skill_description}"
                )
        except Exception as e:
            logger.error(f"Failed to load skill from skill space: {e}")

    return skills
