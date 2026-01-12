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
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from veadk.cloud.cloud_app import CloudApp
from veadk.config import getenv, veadk_environments
from veadk.integrations.ve_apig.ve_apig import APIGateway
from veadk.integrations.ve_faas.ve_faas import VeFaaS
from veadk.integrations.ve_identity.identity_client import IdentityClient
from veadk.utils.logger import get_logger
from veadk.utils.misc import formatted_timestamp

logger = get_logger(__name__)


class CloudAgentEngine(BaseModel):
    """Manages cloud agent deployment and operations on Volcengine FaaS platform.

    This class handles authentication with Volcengine, deploys local projects to FaaS,
    updates function code, removes applications, and supports local testing.

    Attributes:
        volcengine_access_key (str): Access key for Volcengine authentication.
            Defaults to VOLCENGINE_ACCESS_KEY environment variable.
        volcengine_secret_key (str): Secret key for Volcengine authentication.
            Defaults to VOLCENGINE_SECRET_KEY environment variable.
        region (str): Region for Volcengine services. Defaults to "cn-beijing".
        _vefaas_service (VeFaaS): Internal VeFaaS client instance, initialized post-creation.
        _veapig_service (APIGateway): Internal VeAPIG client instance, initialized post-creation.
        _veidentity_service (IdentityClient): Internal Identity client instance, initialized post-creation.

    Note:
        Credentials must be set via environment variables for default behavior.
        This class performs interactive confirmations for destructive operations like removal.

    Examples:
        ```python
        from veadk.cloud.cloud_agent_engine import CloudAgentEngine
        engine = CloudAgentEngine()
        app = engine.deploy("test-app", "/path/to/local/project")
        print(app.vefaas_endpoint)
        ```
    """

    volcengine_access_key: str = getenv(
        "VOLCENGINE_ACCESS_KEY", "", allow_false_values=True
    )
    volcengine_secret_key: str = getenv(
        "VOLCENGINE_SECRET_KEY", "", allow_false_values=True
    )
    region: str = "cn-beijing"

    def model_post_init(self, context: Any, /) -> None:
        """Initializes the internal VeFaaS service after Pydantic model validation.

        Creates a VeFaaS instance using the configured access key, secret key, and region.

        Args:
            self: The CloudAgentEngine instance.
            context: Pydantic post-init context parameter (not used).

        Returns:
            None

        Note:
            This is a Pydantic lifecycle method, ensuring service readiness after init.
        """
        self._vefaas_service = VeFaaS(
            access_key=self.volcengine_access_key,
            secret_key=self.volcengine_secret_key,
            region=self.region,
        )
        self._veapig_service = APIGateway(
            access_key=self.volcengine_access_key,
            secret_key=self.volcengine_secret_key,
            region=self.region,
        )
        self._veidentity_service = IdentityClient(
            access_key=self.volcengine_access_key,
            secret_key=self.volcengine_secret_key,
            region=self.region,
        )

    def _prepare(self, path: str, name: str):
        """Prepares the local project for deployment by validating path and name.

        Checks if the path exists and is a directory, validates application name format.

        Args:
            path (str): Full or relative path to the local agent project directory.
            name (str): Intended VeFaaS application name.

        Returns:
            None

        Raises:
            AssertionError: If path does not exist or is not a directory.
            ValueError: If name contains invalid characters like underscores.

        Note:
            Includes commented code for handling requirements.txt; not executed currently.
            Called internally by deploy and update methods.
        """
        # basic check
        assert os.path.exists(path), f"Local agent project path `{path}` not exists."
        assert os.path.isdir(path), (
            f"Local agent project path `{path}` is not a directory."
        )

        # VeFaaS application/function name check
        if "_" in name:
            raise ValueError(
                f"Invalid Volcengine FaaS function name `{name}`, please use lowercase letters and numbers, or replace it with a `-` char."
            )

        # # copy user's requirements.txt
        # module = load_module_from_file(
        #     module_name="agent_source", file_path=f"{path}/agent.py"
        # )

        # requirement_file_path = module.agent_run_config.requirement_file_path
        # if Path(requirement_file_path).exists():
        #     shutil.copy(requirement_file_path, os.path.join(path, "requirements.txt"))

        #     logger.info(
        #         f"Copy requirement file: from {requirement_file_path} to {path}/requirements.txt"
        #     )
        # else:
        #     logger.warning(
        #         f"Requirement file: {requirement_file_path} not found or you have no requirement file in your project. Use a default one."
        #     )

    def _try_launch_fastapi_server(self, path: str):
        """Tries to start a FastAPI server locally for testing deployment readiness.

        Runs the project's run.sh script and checks connectivity on port 8000.

        Args:
            path (str): Path to the local project containing run.sh.

        Returns:
            None

        Raises:
            RuntimeError: If server startup times out after 30 seconds.

        Note:
            Sets _FAAS_FUNC_TIMEOUT environment to 900 seconds.
            Streams output to console and terminates process after successful check.
            Assumes run.sh launches server on 0.0.0.0:8000.
        """
        RUN_SH = f"{path}/run.sh"

        HOST = "0.0.0.0"
        PORT = 8000

        # Prepare environment variables
        os.environ["_FAAS_FUNC_TIMEOUT"] = "900"
        env = os.environ.copy()

        process = subprocess.Popen(
            ["bash", RUN_SH],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            bufsize=1,
        )

        timeout = 30
        start_time = time.time()

        for line in process.stdout:  # type: ignore
            print(line, end="")

            if time.time() - start_time > timeout:
                process.terminate()
                raise RuntimeError(f"FastAPI server failed to start on {HOST}:{PORT}")
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.1)
                    s.connect(("127.0.0.1", PORT))
                    logger.info(f"FastAPI server is listening on {HOST}:{PORT}")
                    logger.info("Local deplyment test successfully.")
                    break
            except (ConnectionRefusedError, socket.timeout):
                continue

        process.terminate()
        process.wait()

    def deploy(
        self,
        application_name: str,
        path: str,
        gateway_name: str = "",
        gateway_service_name: str = "",
        gateway_upstream_name: str = "",
        use_adk_web: bool = False,
        auth_method: str = "none",
        identity_user_pool_name: str = "",
        identity_client_name: str = "",
        local_test: bool = False,
        enable_session_affinity: bool = False,
    ) -> CloudApp:
        """Deploys a local agent project to Volcengine FaaS, creating necessary resources.

        Prepares project, optionally tests locally, deploys via VeFaaS, and returns app instance.

        Args:
            application_name (str): Unique name for the VeFaaS application.
            path (str): Local directory path of the agent project.
            gateway_name (str, optional): Custom gateway resource name. Defaults to timestamped.
            gateway_service_name (str, optional): Custom service name. Defaults to timestamped.
            gateway_upstream_name (str, optional): Custom upstream name. Defaults to timestamped.
            use_adk_web (bool): Enable ADK Web configuration. Defaults to False.
            auth_method (str, optional): Authentication for the agent. Defaults to none.
            identity_user_pool_name (str, optional): Custom user pool name. Defaults to timestamped.
            identity_client_name (str, optional): Custom client name. Defaults to timestamped.
            local_test (bool): Perform FastAPI server test before deploy. Defaults to False.

        Returns:
            CloudApp: Deployed application with endpoint, name, and ID.

        Raises:
            ValueError: On deployment failure, such as invalid config or VeFaaS errors.

        Note:
            Converts path to absolute; sets telemetry opt-out and ADK Web env vars.
            Generates default gateway names if not specified.

        Examples:
            ```python
            app = engine.deploy("my-agent", "./agent-project", local_test=True)
            print(f"Deployed at: {app.vefaas_endpoint}")
            ```
        """
        # prevent deepeval writing operations
        veadk_environments["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"

        enable_key_auth = False
        if auth_method == "api-key":
            enable_key_auth = True

        if use_adk_web:
            veadk_environments["USE_ADK_WEB"] = "True"
        else:
            veadk_environments["USE_ADK_WEB"] = "False"

        # convert `path` to absolute path
        path = str(Path(path).resolve())
        self._prepare(path, application_name)

        if local_test:
            self._try_launch_fastapi_server(path)

        if not gateway_name:
            gateway_name = f"{application_name}-gw-{formatted_timestamp()}"
        if not gateway_service_name:
            gateway_service_name = f"{application_name}-gw-svr-{formatted_timestamp()}"
        if not gateway_upstream_name:
            gateway_upstream_name = f"{application_name}-gw-us-{formatted_timestamp()}"
        if not identity_user_pool_name:
            identity_user_pool_name = (
                f"{application_name}-id-up-{formatted_timestamp()}"
            )
        if not identity_client_name:
            identity_client_name = f"{application_name}-id-cli-{formatted_timestamp()}"

        try:
            vefaas_application_url, app_id, function_id, affinity_binding_id = (
                self._vefaas_service.deploy(
                    path=path,
                    name=application_name,
                    gateway_name=gateway_name,
                    gateway_service_name=gateway_service_name,
                    gateway_upstream_name=gateway_upstream_name,
                    enable_key_auth=enable_key_auth,
                    enable_session_affinity=enable_session_affinity,
                )
            )
            _ = function_id
            if affinity_binding_id:
                logger.info(f"Session affinity plugin bindng_id: {affinity_binding_id}")

            veapig_gateway_id, _, veapig_route_id = (
                self._vefaas_service.get_application_route(app_id=app_id)
            )

            if auth_method == "oauth2":
                # Get or create the Identity user pool.
                identity_user_pool = self._veidentity_service.get_user_pool(
                    name=identity_user_pool_name,
                )
                if not identity_user_pool:
                    identity_user_pool = self._veidentity_service.create_user_pool(
                        name=identity_user_pool_name,
                    )
                identity_user_pool_id = identity_user_pool[0]
                identity_user_pool_domain = identity_user_pool[1]

                # Create APIG upstream for Identity.
                veapig_identity_upstream_id = (
                    self._veapig_service.check_domain_upstream_exist(
                        domain=identity_user_pool_domain,
                        port=443,
                        gateway_id=veapig_gateway_id,
                    )
                )
                if not veapig_identity_upstream_id:
                    veapig_identity_upstream_id = (
                        self._veapig_service.create_domain_upstream(
                            domain=identity_user_pool_domain,
                            port=443,
                            is_https=True,
                            gateway_id=veapig_gateway_id,
                            upstream_name=f"id-{formatted_timestamp()}",
                        )
                    )

                # Create plugin binding.
                plugin_name = ""
                plugin_config = {}
                if use_adk_web:
                    # Get or create the Identity client.
                    identity_client_id = ""
                    identity_client_secret = ""
                    identity_client = self._veidentity_service.get_user_pool_client(
                        user_pool_uid=identity_user_pool_id,
                        name=identity_client_name,
                    )
                    if identity_client:
                        identity_client_id = identity_client[0]
                        identity_client_secret = identity_client[1]
                    else:
                        identity_client_id, identity_client_secret = (
                            self._veidentity_service.create_user_pool_client(
                                user_pool_uid=identity_user_pool_id,
                                name=identity_client_name,
                                client_type="WEB_APPLICATION",
                            )
                        )

                    self._veidentity_service.register_callback_for_user_pool_client(
                        user_pool_uid=identity_user_pool_id,
                        client_uid=identity_client_id,
                        callback_url=f"{vefaas_application_url}/callback",
                        web_origin=vefaas_application_url,
                    )

                    plugin_name = "wasm-oauth2-sso"
                    plugin_config = {
                        "AuthorizationUrl": f"https://{identity_user_pool_domain}/authorize",
                        "UpstreamId": veapig_identity_upstream_id,
                        "TokenUrl": f"https://{identity_user_pool_domain}/oauth/token",
                        "RedirectPath": "/callback",
                        "SignoutPath": "/signout",
                        "ClientId": identity_client_id,
                        "ClientSecret": identity_client_secret,
                    }
                else:
                    plugin_name = "wasm-jwt-auth"
                    plugin_config = {
                        "RemoteJwks": {
                            "UpstreamId": veapig_identity_upstream_id,
                            "Url": f"https://{identity_user_pool_domain}/keys",
                        },
                        "Issuer": f"https://{identity_user_pool_domain}",
                        "ValidateConsumer": False,
                    }
                self._vefaas_service.apig_client.create_plugin_binding(
                    scope="ROUTE",
                    target=veapig_route_id,
                    plugin_name=plugin_name,
                    plugin_config=json.dumps(plugin_config),
                )

            return CloudApp(
                vefaas_application_name=application_name,
                vefaas_endpoint=vefaas_application_url,
                vefaas_application_id=app_id,
                affinity_binding_id=affinity_binding_id,
            )
        except Exception as e:
            raise ValueError(
                f"Failed to deploy local agent project to Volcengine FaaS platform. Error: {e}"
            )

    def remove(self, app_name: str):
        """Deletes a deployed cloud application after user confirmation.

        Locates app by name, confirms, and issues delete via VeFaaS.

        Args:
            app_name (str): Name of the application to remove.

        Returns:
            None

        Raises:
            ValueError: If application not found by name.

        Note:
            Interactive prompt required; cancels on non-'y' input.
            Deletion is processed asynchronously by VeFaaS.

        Examples:
            ```python
            engine.remove("my-agent")
            ```
        """
        confirm = input(f"Confirm delete cloud app {app_name}? (y/N): ")
        if confirm.lower() != "y":
            print("Delete cancelled.")
            return
        else:
            app_id = self._vefaas_service.find_app_id_by_name(app_name)
            if not app_id:
                raise ValueError(
                    f"Cloud app {app_name} not found, cannot delete it. Please check the app name."
                )
            self._vefaas_service.delete(app_id)

    def update_function_code(
        self,
        application_name: str,
        path: str,
    ) -> CloudApp:
        """Updates the code in an existing VeFaaS application without changing endpoint.

        Prepares new code from local path and updates function via VeFaaS.

        Args:
            application_name (str): Name of the existing application to update.
            path (str): Local path containing updated project files.

        Returns:
            CloudApp: Updated application instance with same endpoint.

        Raises:
            ValueError: If update fails due to preparation or VeFaaS issues.

        Note:
            Preserves gateway and other resources; only function code is updated.
            Path is resolved to absolute before processing.

        Examples:
            ```python
            updated_app = engine.update_function_code("my-agent", "./updated-project")
            ```
        """
        # convert `path` to absolute path
        path = str(Path(path).resolve())
        self._prepare(path, application_name)

        try:
            vefaas_application_url, app_id, function_id = (
                self._vefaas_service._update_function_code(
                    application_name=application_name,
                    path=path,
                )
            )

            return CloudApp(
                vefaas_application_name=application_name,
                vefaas_endpoint=vefaas_application_url,
                vefaas_application_id=app_id,
            )
        except Exception as e:
            raise ValueError(
                f"Failed to update agent project on Volcengine FaaS platform. Error: {e}"
            )

    def disable_session_affinity(self, binding_id: str) -> None:
        """Disable session affinity by deleting plugin binding."""
        self._vefaas_service.disable_session_affinity(binding_id)
        logger.info(f"Session affinity plugin binding {binding_id} deleted.")
