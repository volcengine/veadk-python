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
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from veadk.cloud.cloud_app import CloudApp
from veadk.config import getenv, veadk_environments
from veadk.integrations.ve_faas.ve_faas import VeFaaS
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

    Note:
        Credentials must be set via environment variables for default behavior.
        This class performs interactive confirmations for destructive operations like removal.

    Example:
        >>> from veadk.cloud.cloud_agent_engine import CloudAgentEngine
        >>> engine = CloudAgentEngine()
        >>> app = engine.deploy("test-app", "/path/to/local/project")
        >>> print(app.vefaas_endpoint)
    """

    volcengine_access_key: str = getenv("VOLCENGINE_ACCESS_KEY")
    volcengine_secret_key: str = getenv("VOLCENGINE_SECRET_KEY")
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
        local_test: bool = False,
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
            local_test (bool): Perform FastAPI server test before deploy. Defaults to False.

        Returns:
            CloudApp: Deployed application with endpoint, name, and ID.

        Raises:
            ValueError: On deployment failure, such as invalid config or VeFaaS errors.

        Note:
            Converts path to absolute; sets telemetry opt-out and ADK Web env vars.
            Generates default gateway names if not specified.

        Example:
            >>> app = engine.deploy("my-agent", "./agent-project", local_test=True)
            >>> print(f"Deployed at: {app.vefaas_endpoint}")
        """
        # prevent deepeval writing operations
        veadk_environments["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"

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

        try:
            vefaas_application_url, app_id, function_id = self._vefaas_service.deploy(
                path=path,
                name=application_name,
                gateway_name=gateway_name,
                gateway_service_name=gateway_service_name,
                gateway_upstream_name=gateway_upstream_name,
            )
            _ = function_id  # for future use

            return CloudApp(
                vefaas_application_name=application_name,
                vefaas_endpoint=vefaas_application_url,
                vefaas_application_id=app_id,
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

        Example:
            >>> engine.remove("my-agent")
            Confirm delete cloud app my-agent? (y/N): y
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

        Example:
            >>> updated_app = engine.update_function_code("my-agent", "./updated-project")
            >>> assert updated_app.vefaas_endpoint == old_endpoint
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
