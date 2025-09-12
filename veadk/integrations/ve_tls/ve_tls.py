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

from veadk.consts import DEFAULT_TLS_LOG_PROJECT_NAME, DEFAULT_TLS_TRACING_INSTANCE_NAME
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class VeTLS:
    def __init__(
        self,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "cn-beijing",
    ):
        try:
            from volcengine.tls.TLSService import TLSService

            from veadk.integrations.ve_tls.utils import ve_tls_request
        except ImportError:
            raise ImportError(
                "Please install volcengine SDK before init VeTLS: pip install volcengine"
            )

        self._ve_tls_request = ve_tls_request

        self.access_key = (
            access_key if access_key else os.getenv("VOLCENGINE_ACCESS_KEY", "")
        )
        self.secret_key = (
            secret_key if secret_key else os.getenv("VOLCENGINE_SECRET_KEY", "")
        )
        self.region = region

        self._client = TLSService(
            endpoint=f"https://tls-{self.region}.volces.com",
            access_key_id=self.access_key,
            access_key_secret=self.secret_key,
            region=self.region,
        )

    def get_project_id_by_name(self, project_name: str) -> str:
        """Get the ID of a log project by its name.

        Args:
            project_name (str): The name of the log project.

        Returns:
            str: The ID of the log project, or None if not found.
        """
        logger.info(f"Getting ID for log project '{project_name}' in TLS...")

        request_body = {
            "ProjectName": project_name,
            "IsFullName": True,
        }

        try:
            res = None
            res = self._ve_tls_request(
                client=self._client,
                api="DescribeProjects",
                body=request_body,
                method="GET",
            )
            projects = res["Projects"]
            for project in projects:
                if project["ProjectName"] == project_name:
                    return project["ProjectId"]
            return "<no_project_id_found>"
        except KeyError:
            raise ValueError(f"Failed to get log project ID: {res}")

    def create_log_project(self, project_name: str) -> str:
        """Create a log project in TLS.

        Args:
            project_name (str): The name of the log project to create.

        Returns:
            str: The ID of the created log project.
        """
        logger.info(f"Creating log project '{project_name}' in TLS...")

        request_body = {
            "ProjectName": project_name,
            "Region": self.region,
            "Description": "Created by Volcengine Agent Development Kit (VeADK)",
            "Tags": [{"Key": "provider", "Value": "VeADK"}],
        }
        try:
            res = self._ve_tls_request(
                client=self._client, api="CreateProject", body=request_body
            )

            if res["ErrorCode"] == "ProjectAlreadyExist":
                logger.debug(
                    f"Log project '{project_name}' already exists. Check its ID."
                )
                return self.get_project_id_by_name(project_name)

            return res["ProjectId"]
        except KeyError:
            raise ValueError(f"Failed to create log project: {res}")

    def get_trace_instance_by_name(self, log_project_id: str, trace_instance_name: str):
        logger.info(f"Getting trace instance '{trace_instance_name}' in TLS...")

        request_body = {
            "PageSize": 100,
            "ProjectId": log_project_id,
            "TraceInstanceName": trace_instance_name,
        }
        try:
            res = self._ve_tls_request(
                client=self._client,
                api="DescribeTraceInstances",
                body=request_body,
                method="GET",
            )

            for instance in res["TraceInstances"]:
                if instance["TraceInstanceName"] == trace_instance_name:
                    return instance
        except KeyError:
            raise ValueError(f"Failed to create log project: {res}")

    def create_tracing_instance(self, log_project_id: str, trace_instance_name: str):
        """Create a tracing instance in TLS.

        Args:
            instance_name (str): The name of the tracing instance to create.

        Returns:
            dict: The tracing instance.
        """
        logger.info(f"Creating tracing instance '{trace_instance_name}' in TLS...")

        request_body = {
            "ProjectId": log_project_id,
            "TraceInstanceName": trace_instance_name,
            "Description": "Created by Volcengine Agent Development Kit (VeADK)",
        }

        try:
            res = None
            res = self._ve_tls_request(
                client=self._client,
                api="CreateTraceInstance",
                body=request_body,
            )

            if res["ErrorCode"] == "TopicAlreadyExist":
                logger.debug(
                    f"Log project '{trace_instance_name}' already exists. Check its ID."
                )
                return self.get_trace_instance_by_name(
                    log_project_id, trace_instance_name
                )

            # after creation, get the trace instance details
            res = self._ve_tls_request(
                client=self._client,
                api="DescribeTraceInstance",
                body={"TraceInstanceID": res["TraceInstanceID"]},
                method="GET",
            )

            return res
        except KeyError:
            raise ValueError(f"Failed to create tracing instance: {res}")

    def get_trace_topic_id(self):
        """Get the trace topic ID under VeADK default names.

        This method is a tool function just designed for `veadk/config.py`.

        Returns:
            str: The trace topic ID.
        """
        logger.info("Getting trace topic ID for tracing instance in TLS...")

        log_project_id = self.create_log_project(DEFAULT_TLS_LOG_PROJECT_NAME)

        instance = self.create_tracing_instance(
            log_project_id, DEFAULT_TLS_TRACING_INSTANCE_NAME
        )

        if not instance:
            raise ValueError("None instance")

        logger.info(f"Fetched trace topic id: {instance['TraceTopicId']}")

        return instance["TraceTopicId"]
