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

from veadk.cli.services.veapig.apig import APIGateway
from veadk.utils.logger import get_logger
from veadk.utils.misc import formatted_timestamp
from veadk.utils.volcengine_sign import ve_request

from .vefaas_utils import signed_request, zip_and_encode_folder

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

    def _create_function(self, name: str, path: str):
        function_name = f"{name}-fn-{formatted_timestamp()}"

        # 1. Create a function instance in cloud
        typer.echo(
            typer.style("Runtime: native-python3.10/v1", fg=typer.colors.BRIGHT_BLACK)
        )

        envs = []

        import veadk.config

        for key, value in veadk.config.veadk_environments.items():
            envs.append(EnvForCreateFunctionInput(key=key, value=value))
        typer.echo(
            typer.style(
                f"Fetch {len(envs)} environment variables.",
                fg=typer.colors.BRIGHT_BLACK,
            )
        )

        res = self.client.create_function(
            volcenginesdkvefaas.CreateFunctionRequest(
                command="./run.sh",
                name=function_name,
                description="Created by VeADK (Volcengine Agent Development Kit)",
                tags=[TagForCreateFunctionInput(key="provider", value="veadk")],
                runtime="native-python3.10/v1",
                request_timeout=1800,
                envs=envs,
                # tls_config=TlsConfigForCreateFunctionInput(enable_log=True),
            )
        )
        function_id = res.id

        # 2. Get a temp bucket to store code
        # proj_path = get_project_path()
        code_zip_data, code_zip_size, error = zip_and_encode_folder(path)
        typer.echo(
            typer.style(
                f"Zipped project size: {code_zip_size / 1024 / 1024:.2f} MB",
                fg=typer.colors.BRIGHT_BLACK,
            )
        )

        req = volcenginesdkvefaas.GetCodeUploadAddressRequest(
            function_id=function_id, content_length=code_zip_size
        )
        response = self.client.get_code_upload_address(req)
        upload_url = response.upload_address

        headers = {
            "Content-Type": "application/zip",
        }
        response = requests.put(url=upload_url, data=code_zip_data, headers=headers)
        if 200 <= response.status_code < 300:
            # print(f"Upload successful! Size: {code_zip_size / 1024 / 1024:.2f} MB")
            pass
        else:
            error_message = f"Upload failed to {upload_url} with status code {response.status_code}: {response.text}"
            raise ValueError(error_message)

        # 3. Mount the TOS bucket to function instance
        res = signed_request(
            ak=self.ak,
            sk=self.sk,
            target="CodeUploadCallback",
            body={"FunctionId": function_id},
        )

        typer.echo(
            typer.style(
                f"Function ID on VeFaaS service: {function_id}",
                fg=typer.colors.BRIGHT_BLACK,
            )
        )

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
        assert response["Result"]["Status"] == "create_success"

        return response["Result"]["Id"]

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
            typer.echo(
                typer.style(
                    f"Current status: {status}",
                    fg=typer.colors.BRIGHT_BLACK,
                )
            )
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

    def find_app_id_by_name(self, name: str):
        apps = self._list_application()
        for app in apps:
            if app["Name"] == name:
                return app["Id"]
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
        name: str,  # application name
        path: str,
        gateway_name: str = "",
        gateway_service_name: str = "",
        gateway_upstream_name: str = "",
    ) -> tuple[str, str, str]:
        if "_" in name:
            raise ValueError("Function or Application name cannot contain '_'.")

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

        typer.echo(
            typer.style("[1/3] ", fg=typer.colors.GREEN)
            + "Create VeFaaS service on cloud."
        )
        typer.echo(typer.style(f"Project path: {path}", fg=typer.colors.BRIGHT_BLACK))
        function_name, function_id = self._create_function(name, path)

        typer.echo(typer.style("[2/3] ", fg=typer.colors.GREEN) + "Create application.")
        app_id = self._create_application(
            name,
            function_name,
            gateway_name,
            gateway_upstream_name,
            gateway_service_name,
        )

        typer.echo(
            typer.style("[3/3] ", fg=typer.colors.GREEN) + "Release application."
        )
        url = self._release_application(app_id)

        typer.echo(
            typer.style(f"\nSuccessfully deployed on:\n\n{url}", fg=typer.colors.BLUE)
        )

        return url, app_id, function_id
