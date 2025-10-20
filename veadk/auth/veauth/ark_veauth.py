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


def get_ark_token(region: str = "cn-beijing") -> str:
    logger.info("Fetching ARK token...")

    access_key = os.getenv("VOLCENGINE_ACCESS_KEY")
    secret_key = os.getenv("VOLCENGINE_SECRET_KEY")
    session_token = ""

    if not (access_key and secret_key):
        # try to get from vefaas iam
        cred = get_credential_from_vefaas_iam()
        access_key = cred.access_key_id
        secret_key = cred.secret_access_key
        session_token = cred.session_token

    res = ve_request(
        request_body={"ProjectName": "default", "Filter": {}},
        header={"X-Security-Token": session_token},
        action="ListApiKeys",
        ak=access_key,
        sk=secret_key,
        service="ark",
        version="2024-01-01",
        region=region,
        host="open.volcengineapi.com",
    )
    try:
        first_api_key_id = res["Result"]["Items"][0]["Id"]
    except KeyError:
        raise ValueError(f"Failed to get ARK api key list: {res}")

    # get raw api key
    res = ve_request(
        request_body={"Id": first_api_key_id},
        header={"X-Security-Token": session_token},
        action="GetRawApiKey",
        ak=access_key,
        sk=secret_key,
        service="ark",
        version="2024-01-01",
        region=region,
        host="open.volcengineapi.com",
    )
    try:
        return res["Result"]["ApiKey"]
    except KeyError:
        raise ValueError(f"Failed to get ARK api key: {res}")
