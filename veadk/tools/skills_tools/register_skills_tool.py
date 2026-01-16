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
import os
import zipfile
from pathlib import Path
from datetime import datetime

from google.adk.tools import ToolContext

from veadk.tools.skills_tools.session_path import get_session_path
from veadk.integrations.ve_tos.ve_tos import VeTOS
from veadk.utils.volcengine_sign import ve_request
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def register_skills_tool(
    skill_name: str,
    skill_description: str,
    skill_local_path: str,
    tool_context: ToolContext,
) -> str:
    """Register a skill to the remote skill space by uploading its zip package to TOS and calling the CreateSkill API.

    Args:
        skill_name (str): The name of the skill.
        skill_description (str): The description of the skill.
        skill_local_path (str): The local path of the skill directory.
            - The format of the skill directory is as follows:
                skill_local_path/
                    SKILL.md
                    other files...
        tool_context (ToolContext): The context of the tool execution.

    Returns:
        str: Result message indicating success or failure.
    """
    working_dir = get_session_path(session_id=tool_context.session.id)

    # skill_path = Path(skill_local_path)
    raw = Path(skill_local_path).expanduser()
    if not raw.is_absolute():
        skill_path = (working_dir / raw).resolve()
    else:
        skill_path = raw.resolve()
    if not skill_path.exists() or not skill_path.is_dir():
        logger.error(f"Skill path '{skill_path}' does not exist or is not a directory.")
        return f"Skill path '{skill_path}' does not exist or is not a directory."

    skill_readme = skill_path / "SKILL.md"
    if not skill_readme.exists():
        logger.error(f"Skill path '{skill_path}' has no SKILL.md file.")
        return f"Skill path '{skill_path}' has no SKILL.md file."

    zip_file_path = working_dir / "outputs" / f"{skill_name}.zip"

    with zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(skill_path):
            for file in files:
                file_path = Path(root) / file
                arcname = Path(skill_name) / file_path.relative_to(skill_path)
                zipf.write(file_path, arcname)

    try:
        from veadk.auth.veauth.utils import get_credential_from_vefaas_iam

        agentkit_tool_service = os.getenv("AGENTKIT_TOOL_SERVICE_CODE", "agentkit")
        agentkit_skill_host = os.getenv("AGENTKIT_SKILL_HOST", "open.volcengineapi.com")
        region = os.getenv("AGENTKIT_TOOL_REGION", "cn-beijing")

        access_key = os.getenv("VOLCENGINE_ACCESS_KEY")
        secret_key = os.getenv("VOLCENGINE_SECRET_KEY")
        session_token = ""

        if not (access_key and secret_key):
            cred = get_credential_from_vefaas_iam()
            access_key = cred.access_key_id
            secret_key = cred.secret_access_key
            session_token = cred.session_token

        res = ve_request(
            request_body={},
            action="GetCallerIdentity",
            ak=access_key,
            sk=secret_key,
            service="sts",
            version="2018-01-01",
            region=region,
            host="sts.volcengineapi.com",
            header={"X-Security-Token": session_token},
        )
        try:
            account_id = res["Result"]["AccountId"]
        except KeyError as e:
            logger.error(
                f"Error occurred while getting account id: {e}, response is {res}"
            )
            return f"Error: Failed to get account id when registering skill '{skill_name}'."

        tos_bucket = f"agentkit-platform-{region}-{account_id}-skill"

        tos_client = VeTOS(
            ak=access_key,
            sk=secret_key,
            session_token=session_token,
            bucket_name=tos_bucket,
            region=region,
        )

        object_key = (
            f"uploads/{datetime.now().strftime('%Y%m%d_%H%M%S')}/{skill_name}.zip"
        )
        tos_client.upload_file(
            file_path=zip_file_path, bucket_name=tos_bucket, object_key=object_key
        )
        tos_url = tos_client.build_tos_url(
            bucket_name=tos_bucket, object_key=object_key
        )

        skill_space_ids = os.getenv("SKILL_SPACE_ID", "")
        skill_space_ids_list = [
            x.strip() for x in skill_space_ids.split(",") if x.strip()
        ]

        response = ve_request(
            request_body={
                "Name": skill_name,
                "Description": skill_description,
                "TosUrl": tos_url,
                "SkillSpaces": skill_space_ids_list,
            },
            action="CreateSkill",
            ak=access_key,
            sk=secret_key,
            service=agentkit_tool_service,
            version="2025-10-30",
            region=region,
            host=agentkit_skill_host,
            header={"X-Security-Token": session_token},
        )

        if isinstance(response, str):
            response = json.loads(response)

        logger.debug(f"CreateSkill response: {response}")

        if "Error" in response:
            logger.error(
                f"Failed to register skill '{skill_name}': {response['Error']}"
            )
            return f"Failed to register skill '{skill_name}': {response['Error']}"

        logger.info(
            f"Successfully registered skill '{skill_name}' to skill space {skill_space_ids_list}."
        )
        return f"Successfully registered skill '{skill_name}' to skill space {skill_space_ids_list}."

    except Exception as e:
        logger.error(f"Failed to register skill '{skill_name}': {e}")
        return f"Failed to register skill '{skill_name}'"
