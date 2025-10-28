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
    volcengine_access_key: str = getenv("VOLCENGINE_ACCESS_KEY")
    volcengine_secret_key: str = getenv("VOLCENGINE_SECRET_KEY")
    region: str = "cn-beijing"

    def model_post_init(self, context: Any, /) -> None:
        self._vefaas_service = VeFaaS(
            access_key=self.volcengine_access_key,
            secret_key=self.volcengine_secret_key,
            region=self.region,
        )

    def _prepare(self, path: str, name: str):
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
        """Try to launch a fastapi server for tests according to user's configuration.

        Args:
            path (str): Local agent project path.
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
        """Deploy local agent project to Volcengine FaaS platform.

        Args:
            application_name (str): Expected VeFaaS application name.
            path (str): Local agent project path.
            gateway_name (str): Gateway name.
            gateway_service_name (str): Gateway service name.
            gateway_upstream_name (str): Gateway upstream name.
            use_adk_web (bool): Whether to use ADK Web.
            local_test (bool): Whether to run local test for FastAPI Server.

        Returns:
            CloudApp: The deployed cloud application instance.
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
        """Update existing agent project code while keeping the same URL.

        Args:
            application_name (str): Existing application name to update.
            path (str): Local agent project path.

        Returns:
            CloudApp: Updated cloud app with same endpoint.
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
