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
from veadk.configs.database_configs import MSENacosConfig
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)


def get_instance_id_by_name(instance_name: str, region: str, project_name: str) -> str:
    logger.info(f"Fetching MSE Nacos instance id by instance name {instance_name} ...")

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
        request_body={
            "Filter": {"Status": [], "ProjectName": project_name},
            "PageNumber": 1,
            "PageSize": 10,
            "ProjectName": project_name,
        },
        header={"X-Security-Token": session_token},
        action="ListNacosRegistries",
        ak=access_key,
        sk=secret_key,
        service="mse",
        version="2022-01-01",
        region=region,
        host="open.volcengineapi.com",
    )

    try:
        for item in res["Result"]["Items"]:
            if item["Name"] == instance_name:
                logger.info(
                    f"Found MSE Nacos instance id {item['Id']} by instance name {instance_name}"
                )
                return item["Id"]
        raise ValueError(f"Id by instance name {instance_name} not found: {res}")
    except Exception as e:
        logger.error(
            f"Failed to get MSE Nacos instance id by name {instance_name}: {e}, response: {res}"
        )
        raise e


def get_mse_cridential(
    instance_name: str,
    region: str = "cn-beijing",
    project_name: str = "default",
) -> MSENacosConfig:
    logger.info("Fetching MSE Nacos token...")

    access_key = os.getenv("VOLCENGINE_ACCESS_KEY")
    secret_key = os.getenv("VOLCENGINE_SECRET_KEY")
    session_token = ""

    if not (access_key and secret_key):
        # try to get from vefaas iam
        cred = get_credential_from_vefaas_iam()
        access_key = cred.access_key_id
        secret_key = cred.secret_access_key
        session_token = cred.session_token

    instance_id = get_instance_id_by_name(
        instance_name=instance_name, region=region, project_name=project_name
    )

    res = ve_request(
        request_body={
            "Id": instance_id,
            "ProjectName": project_name,
        },
        header={"X-Security-Token": session_token},
        action="GetNacosRegistry",
        ak=access_key,
        sk=secret_key,
        service="mse",
        version="2022-01-01",
        region=region,
        host="open.volcengineapi.com",
    )

    try:
        logger.info(
            f"Successfully fetched MSE Nacos endpoint {res['Result']['NacosRegistry']['PublicAddress']} and corresponding password."
        )
        return MSENacosConfig(
            endpoint=res["Result"]["NacosRegistry"]["PublicAddress"],
            password=res["Result"]["NacosRegistry"]["InitialPassword"],
        )
    except Exception as e:
        logger.error(f"Failed to get MSE Nacos token: {e}, response: {res}")
        raise e
