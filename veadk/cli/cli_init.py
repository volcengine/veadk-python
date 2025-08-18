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

from typing import Any

import click


def _set_variable_in_file(file_path: str, setting_values: dict):
    import ast

    with open(file_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    tree = ast.parse(source_code)

    class VariableTransformer(ast.NodeTransformer):
        def visit_Assign(self, node: ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in setting_values:
                    node.value = ast.Constant(value=setting_values[target.id])
            return node

    transformer = VariableTransformer()
    new_tree = transformer.visit(tree)
    ast.fix_missing_locations(new_tree)
    new_source_code = ast.unparse(new_tree)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_source_code)

    click.echo("Your project has beed created.")


def _render_prompts() -> dict[str, Any]:
    vefaas_application_name = click.prompt(
        "Volcengine FaaS application name", default="veadk-cloud-agent"
    )

    gateway_name = click.prompt(
        "Volcengine gateway instance name", default="", show_default=True
    )

    gateway_service_name = click.prompt(
        "Volcengine gateway service name", default="", show_default=True
    )

    gateway_upstream_name = click.prompt(
        "Volcengine gateway upstream name", default="", show_default=True
    )

    deploy_mode_options = {
        "1": "A2A/MCP Server",
        # "2": "VeADK Studio",
        "2": "VeADK Web / Google ADK Web",
    }

    click.echo("Choose a deploy mode:")
    for key, value in deploy_mode_options.items():
        click.echo(f"  {key}. {value}")

    deploy_mode = click.prompt(
        "Enter your choice", type=click.Choice(deploy_mode_options.keys())
    )

    return {
        "VEFAAS_APPLICATION_NAME": vefaas_application_name,
        "GATEWAY_NAME": gateway_name,
        "GATEWAY_SERVICE_NAME": gateway_service_name,
        "GATEWAY_UPSTREAM_NAME": gateway_upstream_name,
        "USE_STUDIO": False,
        "USE_ADK_WEB": deploy_mode == deploy_mode_options["2"],
    }


@click.command()
def init() -> None:
    """Init a veadk project that can be deployed to Volcengine VeFaaS."""
    import shutil
    from pathlib import Path

    import veadk.integrations.ve_faas as vefaas

    cwd = Path.cwd()
    local_dir_name = click.prompt("Directory name", default="veadk-cloud-proj")
    target_dir_path = cwd / local_dir_name

    if target_dir_path.exists():
        click.confirm(
            f"Directory '{target_dir_path}' already exists, do you want to overwrite it",
            abort=True,
        )
        shutil.rmtree(target_dir_path)

    setting_values = _render_prompts()

    template_dir_path = Path(vefaas.__file__).parent / "template"
    shutil.copytree(template_dir_path, target_dir_path)
    _set_variable_in_file(target_dir_path / "deploy.py", setting_values)
