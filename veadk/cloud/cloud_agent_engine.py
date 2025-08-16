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
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from veadk.cli.services.vefaas import VeFaaS
from veadk.cloud.cloud_app import CloudApp
from veadk.config import getenv
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

        # project structure check
        assert os.path.exists(os.path.join(path, "agent.py")), (
            f"Local agent project path `{path}` does not contain `agent.py` file. Please prepare it according to our document https://volcengine.github.io/veadk-python/deploy.html"
        )

        if not os.path.exists(os.path.join(path, "config.yaml")):
            logger.warning(
                f"Local agent project path `{path}` does not contain `config.yaml` file. Some important config items may not be set."
            )

        # prepare template files if not have
        template_files = [
            "app.py",
            "studio_app.py",
            "run.sh",
            "requirements.txt",
            "__init__.py",
        ]
        for template_file in template_files:
            if os.path.exists(os.path.join(path, template_file)):
                logger.warning(
                    f"Local agent project path `{path}` contains a `{template_file}` file. Use your own `{template_file}` file may cause unexpected behavior."
                )
            else:
                logger.info(
                    f"No `{template_file}` detected in local agent project path `{path}`. Prepare it."
                )
                template_file_path = f"{Path(__file__).resolve().parent.resolve().parent.resolve()}/cli/services/vefaas/template/src/{template_file}"
                import shutil

                shutil.copy(template_file_path, os.path.join(path, template_file))

    def deploy(
        self,
        application_name: str,
        path: str,
        gateway_name: str = "",
        gateway_service_name: str = "",
        gateway_upstream_name: str = "",
        use_studio: bool = False,
        use_adk_web: bool = False,
    ) -> CloudApp:
        """Deploy local agent project to Volcengine FaaS platform.

        Args:
            path (str): Local agent project path.
            name (str): Volcengine FaaS function name.

        Returns:
            str: Volcengine FaaS function endpoint.
        """
        assert not (use_studio and use_adk_web), (
            "use_studio and use_adk_web can not be True at the same time."
        )

        # prevent deepeval writing operations
        import veadk.config

        veadk.config.veadk_environments["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"

        if use_studio:
            veadk.config.veadk_environments["USE_STUDIO"] = "True"
        else:
            import veadk.config

            veadk.config.veadk_environments["USE_STUDIO"] = "False"

        if use_adk_web:
            import veadk.config

            veadk.config.veadk_environments["USE_ADK_WEB"] = "True"
        else:
            import veadk.config

            veadk.config.veadk_environments["USE_ADK_WEB"] = "False"

        # convert `path` to absolute path
        path = str(Path(path).resolve())
        self._prepare(path, application_name)

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
