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
import time

import requests
import typer
import volcenginesdkcore
import volcenginesdkvefaas
from volcenginesdkvefaas.models.env_for_create_function_input import (
    EnvForCreateFunctionInput,
)
from volcenginesdkvefaas.models.tag_for_create_function_input import (
    TagForCreateFunctionInput,
)

import veadk.config
from veadk.integrations.ve_apig.ve_apig import APIGateway
from veadk.integrations.ve_faas.ve_faas_utils import (
    signed_request,
    zip_and_encode_folder,
)
from veadk.utils.logger import get_logger
from veadk.utils.misc import formatted_timestamp
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)


class VeFaaS:
    def __init__(self, access_key: str, secret_key: str, region: str = "cn-beijing"):
        self.ak = access_key
        self.sk = secret_key
        self.region = region

        configuration = volcenginesdkcore.Configuration()
        configuration.ak = self.ak
        configuration.sk = self.sk
        configuration.region = region

        configuration.client_side_validation = True
        volcenginesdkcore.Configuration.set_default(configuration)

        self.client = volcenginesdkvefaas.VEFAASApi(
            volcenginesdkcore.ApiClient(configuration)
        )

        self.apig_client = APIGateway(self.ak, self.sk, self.region)

        self.template_id = "6874f3360bdbc40008ecf8c7"

    def _upload_and_mount_code(self, function_id: str, path: str):
        """Upload code to VeFaaS temp bucket and mount to function instance.

        Args:
            function_id (str): Target function ID.
            path (str): Local project path.
        """
        # Get zipped code data
        code_zip_data, code_zip_size, error = zip_and_encode_folder(path)
        logger.info(
            f"Zipped project size: {code_zip_size / 1024 / 1024:.2f} MB",
        )

        # Upload code to VeFaaS temp bucket
        req = volcenginesdkvefaas.GetCodeUploadAddressRequest(
            function_id=function_id, content_length=code_zip_size
        )
        response = self.client.get_code_upload_address(req)
        upload_url = response.upload_address

        headers = {
            "Content-Type": "application/zip",
        }
        response = requests.put(url=upload_url, data=code_zip_data, headers=headers)
        if not (200 <= response.status_code < 300):
            error_message = f"Upload failed to {upload_url} with status code {response.status_code}: {response.text}"
            raise ValueError(error_message)

        # Mount the TOS bucket to function instance
        res = signed_request(
            ak=self.ak,
            sk=self.sk,
            target="CodeUploadCallback",
            body={"FunctionId": function_id},
        )

        return res

    def _create_function(self, function_name: str, path: str):
        # Read envs
        envs = []
        for key, value in veadk.config.veadk_environments.items():
            envs.append(EnvForCreateFunctionInput(key=key, value=value))
        logger.info(
            f"Fetch {len(envs)} environment variables.",
        )

        # Create function
        res = self.client.create_function(
            volcenginesdkvefaas.CreateFunctionRequest(
                command="./run.sh",
                name=function_name,
                description="Created by VeADK (Volcengine Agent Development Kit)",
                tags=[TagForCreateFunctionInput(key="provider", value="veadk")],
                runtime="native-python3.10/v1",
                request_timeout=1800,
                envs=envs,
            )
        )
        logger.debug(f"Function creation response: {res}")

        function_id = res.id

        # Upload and mount code using extracted method
        self._upload_and_mount_code(function_id, path)

        return function_name, function_id

    def _create_application(
        self,
        application_name: str,
        function_name: str,
        gateway_name: str,
        upstream_name: str,
        service_name: str,
    ):
        response = ve_request(
            request_body={
                "Name": application_name,
                "Services": [],
                "IAM": [],
                "Config": {
                    "Region": self.region,
                    "FunctionName": function_name,
                    "GatewayName": gateway_name,
                    "ServiceName": service_name,
                    "UpstreamName": upstream_name,
                },
                "TemplateId": self.template_id,
            },
            action="CreateApplication",
            ak=self.ak,
            sk=self.sk,
            service="vefaas",
            version="2021-03-03",
            region="cn-beijing",
            host="open.volcengineapi.com",
        )

        try:
            if response["Result"]["Status"] == "create_success":
                return response["Result"]["Id"]
            else:
                raise ValueError(f"Create application failed: {response}")
        except Exception as _:
            raise ValueError(f"Create application failed: {response}")

    def _release_application(self, app_id: str):
        _ = ve_request(
            request_body={"Id": app_id},
            action="ReleaseApplication",
            ak=self.ak,
            sk=self.sk,
            service="vefaas",
            version="2021-03-03",
            region="cn-beijing",
            host="open.volcengineapi.com",
        )

        status, full_response = self._get_application_status(app_id)
        while status not in ["deploy_success", "deploy_fail"]:
            time.sleep(10)
            status, full_response = self._get_application_status(app_id)

        assert status == "deploy_success", (
            f"Release application failed. Response: {full_response}"
        )

        cloud_resource = full_response["Result"]["CloudResource"]
        cloud_resource = json.loads(cloud_resource)

        url = cloud_resource["framework"]["url"]["system_url"]

        return url

    def _get_application_status(self, app_id: str):
        response = ve_request(
            request_body={"Id": app_id},
            action="GetApplication",
            ak=self.ak,
            sk=self.sk,
            service="vefaas",
            version="2021-03-03",
            region="cn-beijing",
            host="open.volcengineapi.com",
        )
        return response["Result"]["Status"], response

    def _list_application(self):
        response = ve_request(
            request_body={},
            action="ListApplications",
            ak=self.ak,
            sk=self.sk,
            service="vefaas",
            version="2021-03-03",
            region="cn-beijing",
            host="open.volcengineapi.com",
        )
        return response["Result"]["Items"]

    def _update_function_code(
        self,
        application_name: str,  # application name
        path: str,
    ) -> tuple[str, str, str]:
        """Update existing application function code while preserving URL.

        Args:
            application_name (str): Application name to update.
            path (str): Local project path.

        Returns:
            tuple[str, str, str]: URL, app_id, function_id
        """
        # Naming check
        if "_" in application_name:
            raise ValueError("Function or Application name cannot contain '_'.")

        # Find existing application
        app_id = self.find_app_id_by_name(application_name)
        if not app_id:
            raise ValueError(
                f"Application '{application_name}' not found. Use deploy() for new applications."
            )

        # Get application status and extract function info
        status, full_response = self._get_application_status(app_id)
        if status == "deploy_fail":
            raise ValueError(
                f"Cannot update failed application. Current status: {status}"
            )

        # Extract function name from application config
        cloud_resource = full_response["Result"]["CloudResource"]
        cloud_resource = json.loads(cloud_resource)
        function_name = cloud_resource["framework"]["function"]["Name"]
        # existing_url = cloud_resource["framework"]["url"]["system_url"]
        function_id = cloud_resource["framework"]["function"]["Id"]
        if not function_id:
            raise ValueError(f"Function '{function_name}' not found for update")

        logger.info(
            f"Start to update VeFaaS function {function_name} with path {path}."
        )

        # Upload and mount code using extracted method
        self._upload_and_mount_code(function_id, path)

        # Use update_function client method to apply changes
        self.client.update_function(
            volcenginesdkvefaas.UpdateFunctionRequest(
                id=function_id,
                request_timeout=1800,  # Keep same timeout as deploy
            )
        )

        logger.info(f"Function updated successfully: {function_id}")

        logger.info(f"VeFaaS function {function_name} with ID {function_id} updated.")

        # Release the application to apply changes
        url = self._release_application(app_id)

        logger.info(f"VeFaaS application {application_name} with ID {app_id} released.")

        logger.info(
            f"VeFaaS application {application_name} with ID {app_id} updated on {url}."
        )

        return url, app_id, function_id

    def get_application_details(self, app_id: str = None, app_name: str = None):
        if not app_id and not app_name:
            raise ValueError("app_id and app_name cannot be both empty.")
        apps = self._list_application()
        if app_id:
            for app in apps:
                if app["Id"] == app_id:
                    return app
            return None
        else:
            for app in apps:
                if app["Name"] == app_name:
                    return app

    def find_app_id_by_name(self, name: str):
        apps = self._list_application()
        for app in apps:
            if app["Name"] == name:
                return app["Id"]
        logger.warning(f"Application with name {name} not found.")
        return None

    def delete(self, app_id: str):
        try:
            ve_request(
                request_body={"Id": app_id},
                action="DeleteApplication",
                ak=self.ak,
                sk=self.sk,
                service="vefaas",
                version="2021-03-03",
                region="cn-beijing",
                host="open.volcengineapi.com",
            )
        except Exception as e:
            typer.echo(
                typer.style(
                    f"Delete application failed. Response: {e}",
                    fg=typer.colors.BRIGHT_RED,
                )
            )

    def deploy(
        self,
        name: str,
        path: str,
        gateway_name: str = "",
        gateway_service_name: str = "",
        gateway_upstream_name: str = "",
    ) -> tuple[str, str, str]:
        """Deploy an agent project to VeFaaS service.

        Args:
            name (str): Application name (warning: not function name).
            path (str): Project path.
            gateway_name (str, optional): Gateway name. Defaults to "".
            gateway_service_name (str, optional): Gateway service name. Defaults to "".
            gateway_upstream_name (str, optional): Gateway upstream name. Defaults to "".

        Returns:
            tuple[str, str, str]: (url, app_id, function_id)
        """
        # Naming check
        if "_" in name:
            raise ValueError("Function or Application name cannot contain '_'.")

        # Give default names
        if not gateway_name:
            gateway_name = f"{name}-gw-{formatted_timestamp()}"

            existing_gateways = self.apig_client.list_gateways()
            for gateway_instance in existing_gateways.items:
                if (
                    gateway_instance.type == "serverless"
                    and gateway_instance.name != gateway_name
                ):
                    logger.warning(
                        f"You have at least one serverless gateway {gateway_instance.name}, but not {gateway_name}. Using {gateway_instance.name} instead."
                    )
                    gateway_name = gateway_instance.name
                    break

        if not gateway_service_name:
            gateway_service_name = f"{name}-gw-svr-{formatted_timestamp()}"
        if not gateway_upstream_name:
            gateway_upstream_name = f"{name}-gw-us-{formatted_timestamp()}"

        function_name = f"{name}-fn"

        logger.info(
            f"Start to create VeFaaS function {function_name} with path {path}. Gateway: {gateway_name}, Gateway Service: {gateway_service_name}, Gateway Upstream: {gateway_upstream_name}."
        )
        function_name, function_id = self._create_function(function_name, path)
        logger.info(f"VeFaaS function {function_name} with ID {function_id} created.")

        logger.info(f"Start to create VeFaaS application {name}.")
        app_id = self._create_application(
            name,
            function_name,
            gateway_name,
            gateway_upstream_name,
            gateway_service_name,
        )

        logger.info(f"VeFaaS application {name} with ID {app_id} created.")
        logger.info(f"Start to release VeFaaS application {app_id}.")
        url = self._release_application(app_id)
        logger.info(f"VeFaaS application {name} with ID {app_id} released.")

        logger.info(f"VeFaaS application {name} with ID {app_id} deployed on {url}.")

        return url, app_id, function_id
