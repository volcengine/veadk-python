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

from veadk.utils.volcengine_sign import ve_request
from veadk.utils.logger import get_logger
from veadk.consts import (
    DEFAULT_CR_INSTANCE_NAME,
    DEFAULT_CR_NAMESPACE_NAME,
    DEFAULT_CR_REPO_NAME,
)
import time

logger = get_logger(__name__)


class VeCR:
    def __init__(self, access_key: str, secret_key: str, region: str = "cn-beijing"):
        self.ak = access_key
        self.sk = secret_key
        self.region = region
        assert region in ["cn-beijing", "cn-guangzhou", "cn-shanghai"]
        self.version = "2022-05-12"

    def _create_instance(self, instance_name: str = DEFAULT_CR_INSTANCE_NAME) -> str:
        """
        create cr instance

        Args:
            instance_name: cr instance name

        Returns:
            cr instance name
        """
        status = self._check_instance(instance_name)
        if status != "NONEXIST":
            logger.debug(f"cr instance {instance_name} already running")
            return instance_name
        response = ve_request(
            request_body={
                "Name": instance_name,
                "ResourceTags": [
                    {"Key": "provider", "Value": "veadk"},
                ],
            },
            action="CreateRegistry",
            ak=self.ak,
            sk=self.sk,
            service="cr",
            version=self.version,
            region=self.region,
            host=f"cr.{self.region}.volcengineapi.com",
        )
        logger.debug(f"create cr instance {instance_name}: {response}")

        while True:
            status = self._check_instance(instance_name)
            if status == "Running":
                break
            elif status == "Failed":
                raise ValueError(f"cr instance {instance_name} create failed")
            else:
                logger.debug(f"cr instance status: {status}")
                time.sleep(5)

        return instance_name

    def _check_instance(self, instance_name: str) -> str:
        """
        check cr instance status

        Args:
            instance_name: cr instance name

        Returns:
            cr instance status
        """
        response = ve_request(
            request_body={
                "Filter": {
                    "Names": [instance_name],
                }
            },
            action="ListRegistries",
            ak=self.ak,
            sk=self.sk,
            service="cr",
            version=self.version,
            region=self.region,
            host=f"cr.{self.region}.volcengineapi.com",
        )
        logger.debug(f"check cr instance {instance_name}: {response}")

        try:
            if response["Result"]["TotalCount"] == 0:
                return "NONEXIST"
            return response["Result"]["Items"][0]["Status"]["Phase"]
        except Exception as _:
            raise ValueError(f"Error check cr instance {instance_name}: {response}")

    def _create_namespace(
        self,
        instance_name: str = DEFAULT_CR_INSTANCE_NAME,
        namespace_name: str = DEFAULT_CR_NAMESPACE_NAME,
    ) -> str:
        """
        create cr namespace

        Args:
            instance_name: cr instance name
            namespace_name: cr namespace name

        Returns:
            cr namespace name
        """
        response = ve_request(
            request_body={
                "Name": namespace_name,
                "Registry": instance_name,
            },
            action="CreateNamespace",
            ak=self.ak,
            sk=self.sk,
            service="cr",
            version=self.version,
            region=self.region,
            host=f"cr.{self.region}.volcengineapi.com",
        )
        logger.debug(f"create cr namespace {namespace_name}: {response}")

        if "Error" in response["ResponseMetadata"]:
            error_code = response["ResponseMetadata"]["Error"]["Code"]
            error_message = response["ResponseMetadata"]["Error"]["Message"]
            if error_code == "AlreadyExists.Namespace":
                logger.debug(f"cr namespace {namespace_name} already exists")
                return namespace_name
            else:
                logger.error(
                    f"Error create cr namespace {namespace_name}: {error_code} {error_message}"
                )
                raise ValueError(
                    f"Error create cr namespace {namespace_name}: {error_code} {error_message}"
                )

        return namespace_name

    def _create_repo(
        self,
        instance_name: str = DEFAULT_CR_INSTANCE_NAME,
        namespace_name: str = DEFAULT_CR_NAMESPACE_NAME,
        repo_name: str = DEFAULT_CR_REPO_NAME,
    ) -> str:
        """
        create cr repo

        Args:
            instance_name: cr instance name
            namespace_name: cr namespace name
            repo_name: cr repo name

        Returns:
            cr repo name
        """
        response = ve_request(
            request_body={
                "Name": repo_name,
                "Registry": instance_name,
                "Namespace": namespace_name,
                "Description": "veadk cr repo",
            },
            action="CreateRepository",
            ak=self.ak,
            sk=self.sk,
            service="cr",
            version=self.version,
            region=self.region,
            host=f"cr.{self.region}.volcengineapi.com",
        )
        logger.debug(f"create cr repo {repo_name}: {response}")

        if "Error" in response["ResponseMetadata"]:
            error_code = response["ResponseMetadata"]["Error"]["Code"]
            error_message = response["ResponseMetadata"]["Error"]["Message"]
            if error_code == "AlreadyExists.Repository":
                logger.debug(f"cr repo {repo_name} already exists")
                return repo_name
            else:
                logger.error(
                    f"Error create cr repo {repo_name}: {error_code} {error_message}"
                )
                raise ValueError(
                    f"Error create cr repo {repo_name}: {error_code} {error_message}"
                )

        return repo_name
