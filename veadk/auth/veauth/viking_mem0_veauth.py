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

import os

from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)


def _get_api_key_id_by_project_id(
    project_id: str, access_key: str, secret_key: str, session_token: str, region: str
):
    res = ve_request(
        request_body={"MemoryProjectId": project_id},
        header={"X-Security-Token": session_token},
        action="DescribeMemoryProjectDetail",
        ak=access_key,
        sk=secret_key,
        service="mem0",
        version="2025-10-10",
        region=region,
        host="open.volcengineapi.com",
    )
    try:
        api_key_id = res["Result"]["APIKeyInfos"]["APIKeyId"]
    except KeyError:
        raise ValueError(f"Failed to get mem0 api key id: {res}")

    return api_key_id


def _get_api_key_by_api_key_id(
    api_key_id: str, access_key: str, secret_key: str, session_token: str, region: str
) -> str:
    res = ve_request(
        request_body={"APIKeyId": api_key_id},
        header={"X-Security-Token": session_token},
        action="DescribeAPIKeyDetail",
        ak=access_key,
        sk=secret_key,
        service="mem0",
        version="2025-10-10",
        region=region,
        host="open.volcengineapi.com",
    )
    try:
        api_key = res["Result"]["APIKeyValue"]
    except KeyError:
        raise ValueError(f"Failed to get mem0 api key: {res}")

    return api_key


def get_viking_mem0_token(
    api_key_id: str, memory_project_id: str, region: str = "cn-beijing"
) -> str:
    logger.info("Fetching Viking mem0 token...")

    access_key = os.getenv("VOLCENGINE_ACCESS_KEY")
    secret_key = os.getenv("VOLCENGINE_SECRET_KEY")
    session_token = ""

    if not (access_key and secret_key):
        # try to get from vefaas iam
        cred = get_credential_from_vefaas_iam()
        access_key = cred.access_key_id
        secret_key = cred.secret_access_key
        session_token = cred.session_token

    if not api_key_id:
        api_key_id = _get_api_key_id_by_project_id(
            memory_project_id, access_key, secret_key, session_token, region
        )

    return _get_api_key_by_api_key_id(
        api_key_id, access_key, secret_key, session_token, region
    )
