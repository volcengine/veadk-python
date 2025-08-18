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
    "--access-key",
    default=None,
    help="Volcengine access key",
)
@click.option(
    "--secret-key",
    default=None,
    help="Volcengine secret key",
)
@click.option("--vefaas-app-name", help="Expected Volcengine FaaS application name")
@click.option("--veapig-instance-name", help="Expected Volcengine APIG instance name")
@click.option("--veapig-service-name", help="Expected Volcengine APIG service name")
@click.option("--veapig-upstream-name", help="Expected Volcengine APIG upstream name")
@click.option(
    "--short-term-memory-backend",
    default="local",
    type=click.Choice(["local", "mysql"]),
    help="Backend for short-term memory",
)
@click.option("--use-adk-web", is_flag=True, help="Whether to use ADK Web")
@click.option("--path", default=".", help="Local project path")
def deploy(
    access_key: str,
    secret_key: str,
    vefaas_app_name: str,
    veapig_instance_name: str,
    veapig_service_name: str,
    veapig_upstream_name: str,
    short_term_memory_backend: str,
    use_adk_web: bool,
    path: str,
) -> None:
    """Deploy a user project to Volcengine FaaS application."""
    import shutil
    from pathlib import Path

    from cookiecutter.main import cookiecutter

    import veadk.integrations.ve_faas as vefaas
    from veadk.config import getenv
    from veadk.utils.misc import formatted_timestamp

    if not access_key:
        access_key = getenv("VOLCENGINE_ACCESS_KEY")
    if not secret_key:
        secret_key = getenv("VOLCENGINE_SECRET_KEY")

    user_proj_abs_path = Path(path).resolve()
    template_dir_path = Path(vefaas.__file__).parent / "template"

    tmp_dir_name = f"{user_proj_abs_path.name}_{formatted_timestamp()}"

    settings = {
        "local_dir_name": tmp_dir_name,
        "app_name": user_proj_abs_path.name,
        "agent_module_name": user_proj_abs_path.name,
        "requirement_file_path": str(user_proj_abs_path / "requirements.txt"),
        "short_term_memory_backend": short_term_memory_backend,
        "vefaas_application_name": vefaas_app_name,
        "veapig_instance_name": veapig_instance_name,
        "veapig_service_name": veapig_service_name,
        "veapig_upstream_name": veapig_upstream_name,
        "use_adk_web": use_adk_web,
    }

    print(settings)

    cookiecutter(
        template=str(template_dir_path),
        output_dir=TEMP_PATH,
        no_input=True,
        extra_context=settings,
    )

    agent_dir = (
        Path(TEMP_PATH)
        / tmp_dir_name
        / "src"
        / user_proj_abs_path.name.replace("-", "_")
    )

    # remove /tmp/tmp_dir_name/src/user_proj_abs_path.name
    shutil.rmtree(agent_dir)
    agent_dir.mkdir(parents=True, exist_ok=True)

    # mv
    shutil.copytree(user_proj_abs_path, agent_dir, dirs_exist_ok=True)

    # mv requirements.txt and config.yaml if have
    if (user_proj_abs_path / "requirements.txt").exists():
        shutil.copy(
            user_proj_abs_path / "requirements.txt",
            f"{TEMP_PATH}/{tmp_dir_name}/requirements.txt",
        )
        # remove file

    if (user_proj_abs_path / "config.yaml").exists():
        shutil.copy(
            user_proj_abs_path / "config.yaml",
            f"{TEMP_PATH}/{tmp_dir_name}/config.yaml",
        )
        # remove file
