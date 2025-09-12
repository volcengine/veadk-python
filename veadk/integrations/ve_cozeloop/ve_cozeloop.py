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

import requests

from veadk.consts import DEFAULT_COZELOOP_SPACE_NAME
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class VeCozeloop:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def create_workspace(
        self, workspace_name: str = DEFAULT_COZELOOP_SPACE_NAME
    ) -> str:
        logger.info(
            f"Automatically create Cozeloop workspace with name {workspace_name}"
        )

        try:
            workspace_id = self.search_workspace_id(workspace_name=workspace_name)
            logger.info(f"Get existing Cozeloop workspace ID: {workspace_id}")

            return workspace_id
        except Exception as _:
            URL = "https://api.coze.cn/v1/workspaces"

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            data = {
                "name": workspace_name,
                "description": "Created by Volcengine Agent Development Kit (VeADK)",
            }

            response = requests.post(URL, headers=headers, json=data)

            if response.json().get("code") == 0:
                workspace_id = response.json().get("data").get("id")
                logger.info(f"New created Cozeloop workspace ID: {workspace_id}")
                return workspace_id
            else:
                raise Exception(
                    f"Failed to automatically create workspace: {response.json()}"
                )

    def search_workspace_id(
        self, workspace_name: str = DEFAULT_COZELOOP_SPACE_NAME
    ) -> str:
        logger.info(
            f"Automatically fetching Cozeloop workspace ID with name {workspace_name}"
        )

        URL = "https://api.coze.cn/v1/workspaces"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "page_num": 1,
            "page_size": 50,
        }

        response = requests.get(URL, headers=headers, json=data)

        if response.json().get("code") == 0:
            workspaces = response.json().get("data").get("workspaces", [])

            workspace_id = ""
            for workspace in workspaces:
                if workspace.get("name") == workspace_name:
                    workspace_id = workspace.get("id")
                    logger.info(f"Get Cozeloop workspace ID: {workspace_id}")
                    return workspace_id

            raise Exception(f"Workspace with name {workspace_name} not found.")
        else:
            raise Exception(f"Failed to get workspace ID: {response.json()}")
