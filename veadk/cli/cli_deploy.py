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


import click


TEMP_PATH = "/tmp"


@click.command()
@click.option(
    "--volcengine-access-key",
    default=None,
    help="Volcengine access key",
)
@click.option(
    "--volcengine-secret-key",
    default=None,
    help="Volcengine secret key",
)
@click.option("--project-path", default=".", help="Local project path")
@click.option(
    "--deploy-config-file", default="./deploy.yaml", help="Deploy config file path"
)
@click.option(
    "--local_test", is_flag=True, default=False, help="Run local test before deploy"
)
def deploy(
    volcengine_access_key: str,
    volcengine_secret_key: str,
    project_path: str,
    deploy_config_file: str,
    local_test: bool,
) -> None:
    """Deploy a user project to Volcengine FaaS application."""
    import asyncio
    import shutil
    import yaml
    import os
    import sys
    import subprocess
    from pathlib import Path
    from cookiecutter.main import cookiecutter
    import veadk.integrations.ve_faas as vefaas
    from veadk.config import veadk_environments
    from veadk.utils.logger import get_logger
    from veadk.utils.misc import formatted_timestamp
    from veadk.version import VERSION
    from veadk.cloud.cloud_agent_engine import CloudAgentEngine

    logger = get_logger(__name__)

    # if not volcengine_access_key:
    #     access_key = getenv("VOLCENGINE_ACCESS_KEY")
    # if not volcengine_secret_key:
    #     secret_key = getenv("VOLCENGINE_SECRET_KEY")

    # Get deploy.yaml
    if deploy_config_file:
        deploy_config_path = Path(deploy_config_file).resolve()
    else:
        deploy_config_path = Path.cwd() / "deploy.yaml"

    if not deploy_config_path.exists():
        raise click.ClickException(
            f"Deploy config file not found: {deploy_config_path}"
        )

    with open(deploy_config_path, "r") as f:
        deploy_config = yaml.safe_load(f)

    vefaas_config = deploy_config.get("vefaas", {})
    veapig_config = deploy_config.get("veapig", {})
    veadk_config = deploy_config.get("veadk", {})

    # Set environment variables
    os.environ["VEADK_ENTRYPOINT_AGENT"] = veadk_config.get("entrypoint_agent", "")
    os.environ["APP_NAME"] = vefaas_config.get("application_name", "veadk-app")
    os.environ["VOLCENGINE_ACCESS_KEY"] = volcengine_access_key or ""
    os.environ["VOLCENGINE_SECRET_KEY"] = volcengine_secret_key or ""
    os.environ["USE_ADK_WEB"] = (
        "True" if veadk_config.get("deploy_mode", "A2A/MCP") == "WEB" else "False"
    )

    yaml_envs = {
        "VEADK_ENTRYPOINT_AGENT": veadk_config.get("entrypoint_agent", ""),
        "APP_NAME": vefaas_config.get("application_name", "veadk-app"),
        "VOLCENGINE_ACCESS_KEY": volcengine_access_key or "",
        "VOLCENGINE_SECRET_KEY": volcengine_secret_key or "",
        "USE_ADK_WEB": "True"
        if veadk_config.get("deploy_mode", "A2A/MCP") == "WEB"
        else "False",
    }

    for key, value in yaml_envs.items():
        os.environ[key] = value
        veadk_environments[key] = value

    # Get user project path
    user_proj_abs_path = Path(project_path).resolve()

    if not user_proj_abs_path.exists():
        raise click.ClickException(f"Project path not found: {project_path}")

    """ Local test mode """
    if local_test:
        logger.info("Running in local test mode")
        # Add project path to PYTHONPATH for local test
        current_pythonpath = os.environ.get("PYTHONPATH", "")
        os.environ["PYTHONPATH"] = (
            f"{user_proj_abs_path}:{current_pythonpath}"
            if current_pythonpath
            else str(user_proj_abs_path)
        )

        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "veadk.cloud.app:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--reload",
        ]

        try:
            subprocess.run(cmd, check=True)
        except KeyboardInterrupt:
            logger.info("Server stopped")
        return

    """ Deploy mode """
    template_dir_path = Path(vefaas.__file__).parent / "template"
    tmp_dir_name = f"{user_proj_abs_path.name}_{formatted_timestamp()}"

    agent_temp_module_name = user_proj_abs_path.name.replace("-", "_")

    settings = {
        "local_dir_name": tmp_dir_name.replace("-", "_"),
        "app_name": agent_temp_module_name,
        "agent_module_name": user_proj_abs_path.name,
        "short_term_memory_backend": veadk_config.get(
            "short_term_memory_backend", "InMemorySTM"
        ),
        "vefaas_application_name": vefaas_config.get(
            "application_name", "veadk-cloud-agent"
        ),
        "veapig_instance_name": veapig_config.get("instance_name", ""),
        "veapig_service_name": veapig_config.get("service_name", ""),
        "veapig_upstream_name": veapig_config.get("upstream_name", ""),
        "use_adk_web": veadk_config.get("deploy_mode", "A2A/MCP") == "WEB",
        "veadk_version": VERSION,
    }

    cookiecutter(
        template=str(template_dir_path),
        output_dir=TEMP_PATH,
        no_input=True,
        extra_context=settings,
    )
    logger.debug(f"Create a template project at {TEMP_PATH}/{tmp_dir_name}")

    # remove template agent dir. /tmp/tmp_dir_name/user_proj_abs_path.name
    temp_proj_dir = Path(TEMP_PATH) / tmp_dir_name / agent_temp_module_name

    if temp_proj_dir.exists():
        shutil.rmtree(temp_proj_dir)
    temp_proj_dir.mkdir(parents=True, exist_ok=True)

    # Copy user project files to template agent dir
    shutil.copytree(user_proj_abs_path, temp_proj_dir, dirs_exist_ok=True)
    logger.debug(f"Copy agent module from {user_proj_abs_path} to {temp_proj_dir}")

    # copy requirements.txt
    if (user_proj_abs_path / agent_temp_module_name / "requirements.txt").exists():
        logger.debug(
            f"Find a requirements.txt in {user_proj_abs_path}/requirements.txt, copy it to temp project."
        )
        shutil.copy(
            user_proj_abs_path / agent_temp_module_name / "requirements.txt",
            Path(TEMP_PATH) / tmp_dir_name / "requirements.txt",
        )
    else:
        logger.warning(
            "No requirements.txt found in the user project, we will use a default one."
        )

    # avoid upload user's config.yaml
    if (user_proj_abs_path / "config.yaml").exists():
        logger.warning(
            f"Find a config.yaml in {user_proj_abs_path}/config.yaml, we will not upload it by default."
        )
        shutil.move(temp_proj_dir / "config.yaml", Path(TEMP_PATH) / tmp_dir_name)
    else:
        logger.info(
            "No config.yaml found in the user project. Some environment variables may not be set."
        )

    # Create run.sh
    run_sh_content = f"""#!/bin/bash
set -ex

cd `dirname $0`

# A special check for CLI users (run.sh should be located at the 'root' dir)
if [ -d "output" ]; then
    cd ./output/
fi

# Default values for host and port
HOST="0.0.0.0"
PORT=${{_FAAS_RUNTIME_PORT:-8000}}
TIMEOUT=${{_FAAS_FUNC_TIMEOUT:-900}}

export SERVER_HOST=$HOST
export SERVER_PORT=$PORT

# Install requirements
pip install -r requirements.txt

# Set PYTHONPATH
export PYTHONPATH=$PYTHONPATH:./site-packages
export PYTHONPATH=$PYTHONPATH:$(pwd)/{agent_temp_module_name}

# Run server based on mode
if [ "$USE_ADK_WEB" = "True" ]; then
    echo "Running VeADK Web mode"
    exec python3 -m veadk.cli.cli web --host $HOST
else
    echo "Running A2A/MCP mode"
    exec python3 -m uvicorn veadk.cloud.app:app --host $HOST --port $PORT --timeout-graceful-shutdown $TIMEOUT --loop asyncio
fi
"""
    # Write run.sh to the tmp project root
    run_sh_path = Path(TEMP_PATH) / tmp_dir_name / agent_temp_module_name / "run.sh"
    with open(run_sh_path, "w") as f:
        f.write(run_sh_content)
    logger.debug(f"Created run.sh at {run_sh_path}")

    # Deploy using CloudAgentEngine
    async def _deploy():
        engine = CloudAgentEngine()
        cloud_app = engine.deploy(
            path=str(Path(TEMP_PATH) / tmp_dir_name / agent_temp_module_name),
            application_name=vefaas_config.get("application_name"),
            gateway_name=veapig_config.get("instance_name", ""),
            gateway_service_name=veapig_config.get("service_name", ""),
            gateway_upstream_name=veapig_config.get("upstream_name", ""),
            use_adk_web=settings["use_adk_web"],
        )
        return cloud_app

    # Run deployment
    cloud_app = asyncio.run(_deploy())
    logger.info(f"VeFaaS application ID: {cloud_app.vefaas_application_id}")
    if settings["use_adk_web"]:
        logger.info(f"Web is running at: {cloud_app.vefaas_endpoint}")
    else:
        logger.info(f"A2A endpoint: {cloud_app.vefaas_endpoint}")
        logger.info(f"MCP endpoint: {cloud_app.vefaas_endpoint}/mcp")

    # remove tmp file
    logger.info(f"Deploy done. Delete temp dir {Path(TEMP_PATH) / tmp_dir_name}.")
    shutil.rmtree(Path(TEMP_PATH) / tmp_dir_name)
