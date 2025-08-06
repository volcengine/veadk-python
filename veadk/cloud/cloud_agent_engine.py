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
        # VeFaaS path check
        if "_" in name:
            raise ValueError(
                f"Invalid Volcengine FaaS function name `{name}`, please use lowercase letters and numbers, or replace it with a `-` char."
            )

        # project path check
        assert os.path.exists(path), f"Local agent project path `{path}` not exists."
        assert os.path.isdir(path), (
            f"Local agent project path `{path}` is not a directory."
        )

        assert os.path.exists(os.path.join(path, "agent.py")), (
            f"Local agent project path `{path}` does not contain `agent.py` file. Please prepare it according to veadk-python/cloud/template/agent.py.example"
        )

        if os.path.exists(os.path.join(path, "app.py")):
            logger.warning(
                f"Local agent project path `{path}` contains an `app.py` file. Use your own `app.py` file may cause unexpected behavior."
            )
        else:
            logger.info(
                f"No `app.py` detected in local agent project path `{path}`. Prepare it."
            )
            template_app_py = (
                f"{Path(__file__).resolve().parent.resolve()}/template/app.py"
            )
            import shutil

            shutil.copy(template_app_py, os.path.join(path, "app.py"))

        if os.path.exists(os.path.join(path, "studio_app.py")):
            logger.warning(
                f"Local agent project path `{path}` contains an `studio_app.py` file. Use your own `studio_app.py` file may cause unexpected behavior."
            )
        else:
            logger.info(
                f"No `studio_app.py` detected in local agent project path `{path}`. Prepare it."
            )
            template_studio_app_py = (
                f"{Path(__file__).resolve().parent.resolve()}/template/studio_app.py"
            )
            import shutil

            shutil.copy(template_studio_app_py, os.path.join(path, "studio_app.py"))

        if os.path.exists(os.path.join(path, "run.sh")):
            logger.warning(
                f"Local agent project path `{path}` contains a `run.sh` file. Use your own `run.sh` file may cause unexpected behavior."
            )
        else:
            logger.info(
                f"No `run.sh` detected in local agent project path `{path}`. Prepare it."
            )
            template_run_sh = (
                f"{Path(__file__).resolve().parent.resolve()}/template/run.sh"
            )
            import shutil

            shutil.copy(template_run_sh, os.path.join(path, "run.sh"))

    def deploy(
        self,
        path: str,
        name: str,
        gateway_name: str = "",
        gateway_service_name: str = "",
        gateway_upstream_name: str = "",
        use_studio: bool = False,
    ) -> CloudApp:
        """Deploy local agent project to Volcengine FaaS platform.

        Args:
            path (str): Local agent project path.
            name (str): Volcengine FaaS function name.

        Returns:
            str: Volcengine FaaS function endpoint.
        """
        # prevent deepeval writing operations
        import veadk.config

        veadk.config.veadk_environments["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"

        if use_studio:
            import veadk.config

            veadk.config.veadk_environments["USE_STUDIO"] = "True"
        else:
            import veadk.config

            veadk.config.veadk_environments["USE_STUDIO"] = "False"

        # convert `path` to absolute path
        path = str(Path(path).resolve())
        self._prepare(path, name)

        if not gateway_name:
            gateway_name = f"{name}-gw-{formatted_timestamp()}"
        if not gateway_service_name:
            gateway_service_name = f"{name}-gw-svr-{formatted_timestamp()}"
        if not gateway_upstream_name:
            gateway_upstream_name = f"{name}-gw-us-{formatted_timestamp()}"

        try:
            vefaas_application_url, app_id, function_id = self._vefaas_service.deploy(
                path=path,
                name=name,
                gateway_name=gateway_name,
                gateway_service_name=gateway_service_name,
                gateway_upstream_name=gateway_upstream_name,
            )
            _ = function_id  # for future use

            return CloudApp(
                name=name,
                endpoint=vefaas_application_url,
                app_id=app_id,
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
            self._vefaas_service.delete(app_id)
