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
def deploy(
    volcengine_access_key: str,
    volcengine_secret_key: str,
    project_path: str,
    deploy_config_file: str,
) -> None:
    #     """Deploy a user project to Volcengine FaaS application."""
    #     import asyncio
    #     import shutil
    #     from pathlib import Path

    #     from cookiecutter.main import cookiecutter

    #     import veadk.integrations.ve_faas as vefaas
    #     from veadk.config import getenv
    #     from veadk.utils.logger import get_logger
    #     from veadk.utils.misc import formatted_timestamp, load_module_from_file

    #     logger = get_logger(__name__)

    #     if not volcengine_access_key:
    #         access_key = getenv("VOLCENGINE_ACCESS_KEY")
    #     if not volcengine_secret_key:
    #         secret_key = getenv("VOLCENGINE_SECRET_KEY")

    #     user_proj_abs_path = Path(path).resolve()
    #     template_dir_path = Path(vefaas.__file__).parent / "template"

    #     tmp_dir_name = f"{user_proj_abs_path.name}_{formatted_timestamp()}"

    #     settings = {
    #         "local_dir_name": tmp_dir_name.replace("-", "_"),
    #         "app_name": user_proj_abs_path.name.replace("-", "_"),
    #         "agent_module_name": user_proj_abs_path.name,
    #         "short_term_memory_backend": short_term_memory_backend,
    #         "vefaas_application_name": vefaas_app_name,
    #         "veapig_instance_name": veapig_instance_name,
    #         "veapig_service_name": veapig_service_name,
    #         "veapig_upstream_name": veapig_upstream_name,
    #         "use_adk_web": use_adk_web,
    #         "veadk_version": VERSION,
    #     }

    #     cookiecutter(
    #         template=str(template_dir_path),
    #         output_dir=TEMP_PATH,
    #         no_input=True,
    #         extra_context=settings,
    #     )
    #     logger.debug(f"Create a template project at {TEMP_PATH}/{tmp_dir_name}")

    #     agent_dir = (
    #         Path(TEMP_PATH)
    #         / tmp_dir_name
    #         / "src"
    #         / user_proj_abs_path.name.replace("-", "_")
    #     )

    #     # remove /tmp/tmp_dir_name/src/user_proj_abs_path.name
    #     shutil.rmtree(agent_dir)
    #     agent_dir.mkdir(parents=True, exist_ok=True)

    #     # copy
    #     shutil.copytree(user_proj_abs_path, agent_dir, dirs_exist_ok=True)
    #     logger.debug(f"Remove agent module from {user_proj_abs_path} to {agent_dir}")

    #     # copy requirements.txt
    #     if (user_proj_abs_path / "requirements.txt").exists():
    #         logger.debug(
    #             f"Find a requirements.txt in {user_proj_abs_path}/requirements.txt, copy it to temp project."
    #         )
    #         shutil.copy(
    #             user_proj_abs_path / "requirements.txt",
    #             Path(TEMP_PATH) / tmp_dir_name / "src" / "requirements.txt",
    #         )
    #     else:
    #         logger.warning(
    #             "No requirements.txt found in the user project, we will use a default one."
    #         )

    #     # avoid upload user's config.yaml
    #     if (user_proj_abs_path / "config.yaml").exists():
    #         logger.warning(
    #             f"Find a config.yaml in {user_proj_abs_path}/config.yaml, we will not upload it by default."
    #         )
    #         shutil.move(agent_dir / "config.yaml", Path(TEMP_PATH) / tmp_dir_name)
    #     else:
    #         logger.info(
    #             "No config.yaml found in the user project. Some environment variables may not be set."
    #         )

    #     # load
    #     logger.debug(
    #         f"Load deploy module from {Path(TEMP_PATH) / tmp_dir_name / 'deploy.py'}"
    #     )
    #     deploy_module = load_module_from_file(
    #         module_name="deploy_module",
    #         file_path=str(Path(TEMP_PATH) / tmp_dir_name / "deploy.py"),
    #     )
    #     logger.info(f"Begin deploy from {Path(TEMP_PATH) / tmp_dir_name / 'src'}")
    #     asyncio.run(deploy_module.main())

    #     # remove tmp file
    #     logger.info("Deploy done. Delete temp dir.")
    #     shutil.rmtree(Path(TEMP_PATH) / tmp_dir_name)
    pass
