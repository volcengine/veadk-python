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

from pydantic import BaseModel

from veadk.consts import VEFAAS_IAM_CRIDENTIAL_PATH
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class VeIAMCredential(BaseModel):
    access_key_id: str
    secret_access_key: str
    session_token: str


def get_credential_from_vefaas_iam() -> VeIAMCredential:
    """Get credential from VeFaaS IAM file"""
    logger.info(
        f"Get Volcegnine access key or secret key from environment variables failed, try to get from VeFaaS IAM file (path={VEFAAS_IAM_CRIDENTIAL_PATH})."
    )

    path = Path(VEFAAS_IAM_CRIDENTIAL_PATH)

    if not path.exists():
        logger.error(
            f"Get Volcegnine access key or secret key from environment variables failed, and VeFaaS IAM file (path={VEFAAS_IAM_CRIDENTIAL_PATH}) not exists. Please check your configuration."
        )
        raise FileNotFoundError(
            f"Get Volcegnine access key or secret key from environment variables failed, and VeFaaS IAM file (path={VEFAAS_IAM_CRIDENTIAL_PATH}) not exists. Please check your configuration."
        )

    with open(VEFAAS_IAM_CRIDENTIAL_PATH, "r") as f:
        cred_dict = json.load(f)
        access_key = cred_dict["access_key_id"]
        secret_key = cred_dict["secret_access_key"]
        session_token = cred_dict["session_token"]
        return VeIAMCredential(
            access_key_id=access_key,
            secret_access_key=secret_key,
            session_token=session_token,
        )
