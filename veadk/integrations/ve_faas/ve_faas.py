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
import shutil
from pathlib import Path
from cookiecutter.main import cookiecutter
import veadk.integrations.ve_faas as vefaas
from veadk.version import VERSION
import requests
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
from veadk.utils.misc import formatted_timestamp, getenv
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
                runtime="native-python3.12/v1",
                request_timeout=1800,
                envs=envs,
                memory_mb=2048,
                role=getenv("IAM_ROLE", None, allow_false_values=True),
            )
        )

        # avoid print secrets
        logger.debug(
            f"Function creation in {res.project_name} project with ID {res.id}"
        )

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
        enable_key_auth: bool = False,
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
                    "EnableKeyAuth": enable_key_auth,
                    "EnableMcpSession": True,
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

        if status == "deploy_success":
            cloud_resource = full_response["Result"]["CloudResource"]
            cloud_resource = json.loads(cloud_resource)
            url = cloud_resource["framework"]["url"]["system_url"]
            return url
        else:
            logger.error(
                f"Release application failed. Application ID: {app_id}, Status: {status}"
            )
            import re

            logs = "\n".join(self._get_application_logs(app_id=app_id))
            log_text = re.sub(
                r'([{"\']?(key|secret|token|pass|auth|credential|access|api|ak|sk|doubao|volces|coze)[^"\'\s]*["\']?\s*[:=]\s*)(["\']?)([^"\'\s]+)(["\']?)|([A-Za-z0-9+/=]{20,})',
                lambda m: (
                    f"{m.group(1)}{m.group(3)}******{m.group(5)}"
                    if m.group(1)
                    else "******"
                ),
                logs,
                flags=re.IGNORECASE,
            )
            raise Exception(f"Release application failed. Logs:\n{log_text}")

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

    def _list_application(self, app_id: str = None, app_name: str = None):
        # firt match app_id. if app_id is None,then match app_name and remove app_id
        request_body = {
            "OrderBy": {"Key": "CreateTime", "Ascend": False},
            "FunctionId": app_id if app_id else None,
            "Filters": (
                [{"Item": {"Key": "Name", "Value": [app_name]}}]
                if app_name and not app_id
                else None
            ),
        }
        # remove None
        request_body = {k: v for k, v in request_body.items() if v is not None}

        page_size = 50
        page_number = 1
        all_items = []
        total_page = None
        while True:
            try:
                request_body.update({"PageNumber": page_number, "PageSize": page_size})
                response = ve_request(
                    request_body=request_body,
                    action="ListApplications",
                    ak=self.ak,
                    sk=self.sk,
                    service="vefaas",
                    version="2021-03-03",
                    region="cn-beijing",
                    host="open.volcengineapi.com",
                )
                result = response.get("Result", {})
                items = result.get("Items", [])
                all_items.extend(items)

                if total_page is None:
                    total = result.get("Total", 0)
                    total_page = (total + page_size - 1) // page_size

                if page_number >= total_page or not items:
                    break
                page_number += 1
            except Exception as e:
                raise ValueError(
                    f"List application failed. Error: {str(e)}. Response: {response}."
                )
        return all_items

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

        user_proj_path = Path(path).resolve()
        template_dir = Path(vefaas.__file__).parent / "template"
        tmp_dir_name = f"{user_proj_path.name}_update_{formatted_timestamp()}"

        settings = {
            "local_dir_name": tmp_dir_name.replace("-", "_"),
            "app_name": user_proj_path.name.replace("-", "_"),
            "veadk_version": VERSION,
        }

        cookiecutter(
            template=str(template_dir),
            output_dir="/tmp",
            no_input=True,
            extra_context=settings,
        )

        tmp_path = Path("/tmp") / tmp_dir_name
        try:
            agent_dir = tmp_path / "src" / user_proj_path.name.replace("-", "_")
            if agent_dir.exists():
                shutil.rmtree(agent_dir)
            agent_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(user_proj_path, agent_dir, dirs_exist_ok=True)
            user_requirements = user_proj_path / "requirements.txt"

            if user_requirements.exists():
                logger.debug("Using user-provided requirements.txt")
                shutil.copy(user_requirements, tmp_path / "src" / "requirements.txt")
            else:
                logger.warning("No requirements.txt found, using template default")

            self._upload_and_mount_code(function_id, str(tmp_path / "src"))
            self.client.update_function(
                volcenginesdkvefaas.UpdateFunctionRequest(
                    id=function_id,
                    request_timeout=1800,  # Keep same timeout as deploy
                )
            )
            logger.info(
                f"VeFaaS function {function_name} with ID {function_id} updated."
            )
            url = self._release_application(app_id)
            logger.info(
                f"VeFaaS application {application_name} with ID {app_id} released."
            )
            logger.info(f"VeFaaS application {application_name} updated on {url}.")
            return url, app_id, function_id

        finally:
            if tmp_path.exists():
                shutil.rmtree(tmp_path)
                logger.debug(f"Cleaned up temporary directory: {tmp_path}")

    def get_application_details(self, app_id: str = None, app_name: str = None):
        if not app_id and not app_name:
            raise ValueError("app_id and app_name cannot be both empty.")
        apps = self._list_application(app_id=app_id, app_name=app_name)
        if app_id:
            for app in apps:
                if app["Id"] == app_id:
                    return app
            return None
        else:
            for app in apps:
                if app["Name"] == app_name:
                    return app

    def get_application_route(
        self, app_id: str = None, app_name: str = None
    ) -> tuple[str, str, str] | None:
        app = self.get_application_details(
            app_id=app_id,
            app_name=app_name,
        )
        if not app:
            return None

        cloud_resource = json.loads(app["CloudResource"])
        gateway_id = cloud_resource["framework"]["triggers"][0]["DetailedConfig"][
            "GatewayId"
        ]
        service_id = cloud_resource["framework"]["triggers"][0]["Routes"][0][
            "ServiceId"
        ]
        route_id = cloud_resource["framework"]["triggers"][0]["Routes"][0]["Id"]
        return gateway_id, service_id, route_id

    def find_app_id_by_name(self, name: str):
        apps = self._list_application(app_name=name)
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
            logger.error(f"Delete application failed. Response: {e}")

    def deploy(
        self,
        name: str,
        path: str,
        gateway_name: str = "",
        gateway_service_name: str = "",
        gateway_upstream_name: str = "",
        enable_key_auth: bool = False,
    ) -> tuple[str, str, str]:
        """Deploy an agent project to VeFaaS service.

        Args:
            name (str): Application name (warning: not function name).
            path (str): Project path.
            gateway_name (str, optional): Gateway name. Defaults to "".
            gateway_service_name (str, optional): Gateway service name. Defaults to "".
            gateway_upstream_name (str, optional): Gateway upstream name. Defaults to "".
            enable_key_auth (bool, optional): Enable key auth. Defaults to False.

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
            enable_key_auth,
        )

        logger.info(f"VeFaaS application {name} with ID {app_id} created.")
        logger.info(f"Start to release VeFaaS application {app_id}.")
        url = self._release_application(app_id)
        logger.info(f"VeFaaS application {name} with ID {app_id} released.")

        logger.info(f"VeFaaS application {name} with ID {app_id} deployed on {url}.")

        return url, app_id, function_id

    def _create_image_function(self, function_name: str, image: str):
        """Create function using container image instead of code upload."""
        # Read environment variables from veadk configuration
        envs = []
        for key, value in veadk.config.veadk_environments.items():
            envs.append(EnvForCreateFunctionInput(key=key, value=value))
        logger.info(
            f"Fetch {len(envs)} environment variables for image function.",
        )

        # Create function with container image source configuration
        res = self.client.create_function(
            volcenginesdkvefaas.CreateFunctionRequest(
                command="bash ./run.sh",  # Custom startup command
                name=function_name,
                description="Created by VeADK (Volcengine Agent Development Kit)",
                tags=[TagForCreateFunctionInput(key="provider", value="veadk")],
                runtime="native/v1",  # Native runtime required for container images
                source_type="image",  # Set source type to container image
                source=image,  # Container image URL
                request_timeout=1800,  # Request timeout in seconds
                envs=envs,  # Environment variables from configuration
            )
        )

        # Log function creation success without exposing sensitive information
        logger.debug(
            f"Function creation in {res.project_name} project with ID {res.id}"
        )

        function_id = res.id
        logger.info(
            f"Function {function_name} created with image {image} and ID {function_id}"
        )

        return function_name, function_id

    def query_user_cr_vpc_tunnel(
        self, registry_name: str, max_attempts: int = 6
    ) -> bool:
        """Query and enable CR VPC tunnel for user registry access."""
        logger.info(f"Setting up CR VPC tunnel for registry: {registry_name}")
        waiting_times = 30

        try:
            for attempt in range(max_attempts):
                # Check current status
                logger.info(
                    f"Checking tunnel status (attempt {attempt + 1}/{max_attempts})"
                )
                query_resp = ve_request(
                    request_body={"Registry": registry_name},
                    action="QueryUserCrVpcTunnel",
                    ak=self.ak,
                    sk=self.sk,
                    service="vefaas",
                    version="2021-03-03",
                    region="cn-beijing",
                    host="open.volcengineapi.com",
                )

                current_status = query_resp.get("Result", {}).get("Ready", False)
                logger.info(f"Current tunnel status: {current_status}")

                # Always try to enable
                logger.info("Enable VPC tunnel")
                enable_resp = ve_request(
                    request_body={"Registry": registry_name},
                    action="EnableUserCrVpcTunnel",
                    ak=self.ak,
                    sk=self.sk,
                    service="vefaas",
                    version="2021-03-03",
                    region="cn-beijing",
                    host="open.volcengineapi.com",
                )

                # Handle EnableUserCrVpcTunnel response correctly
                enable_result = enable_resp.get("Result", {})
                enable_status = enable_result.get("Status", "")
                enable_message = enable_result.get("Message", "")

                if enable_status == "success":
                    logger.info("Enable tunnel succeeded")
                elif enable_status == "failed":
                    logger.warning(f"Enable tunnel failed: {enable_message}")
                else:
                    logger.warning(f"Enable tunnel unknown status: {enable_status}")

                # Verify final status
                logger.info("Verifying tunnel status")
                verify_resp = ve_request(
                    request_body={"Registry": registry_name},
                    action="QueryUserCrVpcTunnel",
                    ak=self.ak,
                    sk=self.sk,
                    service="vefaas",
                    version="2021-03-03",
                    region="cn-beijing",
                    host="open.volcengineapi.com",
                )

                final_status = verify_resp.get("Result", {}).get("Ready", False)
                logger.info(f"Final tunnel status: {final_status}")

                if final_status:
                    logger.info(
                        f"CR VPC tunnel successfully enabled for {registry_name}"
                    )
                    return True

                # If not ready and not last attempt, wait and retry
                if attempt < max_attempts - 1:
                    logger.warning(
                        f"Tunnel not ready, waiting {waiting_times}s before retry"
                    )
                    time.sleep(waiting_times)

        except Exception as e:
            raise ValueError(f"Failed to setup CR VPC tunnel: {str(e)}")

        return False

    def _create_image_function(self, function_name: str, image: str):
        """Create function using container image instead of code upload."""
        # Read environment variables from veadk configuration
        envs = []
        for key, value in veadk.config.veadk_environments.items():
            envs.append(EnvForCreateFunctionInput(key=key, value=value))
        logger.info(
            f"Fetch {len(envs)} environment variables for image function.",
        )

        # Create function with container image source configuration
        res = self.client.create_function(
            volcenginesdkvefaas.CreateFunctionRequest(
                command="bash ./run.sh",  # Custom startup command
                name=function_name,
                description="Created by VeADK (Volcengine Agent Development Kit)",
                tags=[TagForCreateFunctionInput(key="provider", value="veadk")],
                runtime="native/v1",  # Native runtime required for container images
                source_type="image",  # Set source type to container image
                source=image,  # Container image URL
                request_timeout=1800,  # Request timeout in seconds
                envs=envs,  # Environment variables from configuration
            )
        )

        # Log function creation success without exposing sensitive information
        logger.debug(
            f"Function creation in {res.project_name} project with ID {res.id}"
        )

        function_id = res.id
        logger.info(
            f"Function {function_name} created with image {image} and ID {function_id}"
        )

        return function_name, function_id

    def deploy_image(
        self,
        name: str,
        image: str,
        registry_name: str,
        gateway_name: str = "",
        gateway_service_name: str = "",
        gateway_upstream_name: str = "",
    ) -> tuple[str, str, str]:
        """Deploy application using container image.

        Args:
            name (str): Application name.
            image (str): Container image URL.
            gateway_name (str, optional): Gateway name. Defaults to "".
            gateway_service_name (str, optional): Gateway service name. Defaults to "".
            gateway_upstream_name (str, optional): Gateway upstream name. Defaults to "".

        Returns:
            tuple[str, str, str]: (url, app_id, function_id)
        """
        # Validate application name format
        is_ready = self.query_user_cr_vpc_tunnel(registry_name)
        if not is_ready:
            raise ValueError("CR VPC tunnel is not ready")

        if "_" in name:
            raise ValueError("Function or Application name cannot contain '_'.")

        # Generate default gateway names with timestamp if not provided
        if not gateway_name:
            gateway_name = f"{name}-gw-{formatted_timestamp()}"

            # Check for existing serverless gateways to reuse
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

        # Set default gateway service and upstream names
        if not gateway_service_name:
            gateway_service_name = f"{name}-gw-svr-{formatted_timestamp()}"
        if not gateway_upstream_name:
            gateway_upstream_name = f"{name}-gw-us-{formatted_timestamp()}"

        function_name = f"{name}-fn"

        # Log deployment start with image information
        logger.info(
            f"Start to create VeFaaS function {function_name} with image {image}. Gateway: {gateway_name}, Gateway Service: {gateway_service_name}, Gateway Upstream: {gateway_upstream_name}."
        )

        # Create function using container image method
        function_name, function_id = self._create_image_function(function_name, image)
        logger.info(f"VeFaaS function {function_name} with ID {function_id} created.")

        # Create application using existing application creation logic
        logger.info(f"Start to create VeFaaS application {name}.")
        app_id = self._create_application(
            name,
            function_name,
            gateway_name,
            gateway_upstream_name,
            gateway_service_name,
        )

        # Release application and get deployment URL
        logger.info(f"VeFaaS application {name} with ID {app_id} created.")
        logger.info(f"Start to release VeFaaS application {app_id}.")
        # Release application with retry
        max_attempts = 5
        attempt = 0
        while True:
            try:
                url = self._release_application(app_id)
                logger.info(f"VeFaaS application {name} with ID {app_id} released.")
                break
            except Exception:
                attempt += 1
                if attempt < max_attempts:
                    wait_time = 30 * attempt
                    logger.info(
                        f"Image sync still in progress. Waiting {wait_time} seconds before retry {attempt}/{max_attempts}."
                    )
                    time.sleep(wait_time)
                else:
                    raise

        logger.info(f"VeFaaS application {name} with ID {app_id} deployed on {url}.")

        return url, app_id, function_id

    def _get_application_logs(self, app_id: str) -> list[str]:
        response = _ = ve_request(
            request_body={"Id": app_id, "Limit": 99999, "RevisionNumber": 1},
            action="GetApplicationRevisionLog",
            ak=self.ak,
            sk=self.sk,
            service="vefaas",
            version="2021-03-03",
            region="cn-beijing",
            host="open.volcengineapi.com",
        )

        try:
            logs = response["Result"]["LogLines"]
            return logs
        except Exception as _:
            raise ValueError(f"Get application log failed. Response: {response}")
