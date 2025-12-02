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
import shutil
import sys
from pathlib import Path


def get_rl_template_root() -> Path:
    """Get absolute path of RL scaffold template root (cli/templates/rl/)"""
    current_file = Path(__file__).resolve()
    cli_dir = current_file.parent
    rl_template_root = cli_dir / "templates" / "rl"
    return rl_template_root


@click.group(name="rl", help="RL related commands")
def rl_group():
    pass


@rl_group.command(
    name="init", help="Initialize RL scaffold project (specify platform/workspace)"
)
@click.option(
    "--platform",
    "-p",
    required=True,
    type=click.Choice(["ark"], case_sensitive=False),
    help="Scaffold platform type (only support for now: ark)",
)
@click.option(
    "--workspace", "-w", required=True, type=str, help="Target workspace directory name"
)
@click.option(
    "--overwrite",
    "-f",
    is_flag=True,
    help="Force overwrite existing workspace (default: false)",
)
def rl_init(platform: str, workspace: str, overwrite: bool):
    """
    Initialize RL scaffold project for ark platform
    Example: veadk rl init --platform ark --workspace veadk_rl_ark_project
    """
    # Locate template directory
    rl_template_root = get_rl_template_root()
    platform_template_dir = rl_template_root / platform.lower()

    # Validate template directory
    if not platform_template_dir.exists():
        click.secho(f"Error: Scaffold template for {platform} not found!", fg="red")
        click.secho(f"  Expected path: {platform_template_dir}", fg="yellow")
        click.secho(
            f"  Supported platforms: {[d.name for d in rl_template_root.glob('*') if d.is_dir()]}",
            fg="blue",
        )
        sys.exit(1)

    # Target workspace path
    target_workspace = Path.cwd() / workspace

    # Handle existing directory
    if target_workspace.exists():
        if not overwrite:
            click.secho(
                f"\nWarning: Target directory {target_workspace} already exists!",
                fg="yellow",
            )
            if not click.confirm("Overwrite?"):
                click.secho("Operation cancelled", fg="red")
                sys.exit(0)
        shutil.rmtree(target_workspace)
        click.secho(f"Cleared existing directory: {target_workspace}", fg="green")

    # Copy scaffold files
    try:
        shutil.copytree(
            src=platform_template_dir,
            dst=target_workspace,
            ignore=None,
            dirs_exist_ok=False,
        )
        click.secho("\nRL scaffold initialized successfully!", fg="green")
        click.secho(f"  - Project path: {target_workspace.absolute()}", fg="green")
    except PermissionError:
        click.secho(
            f"Error: Permission denied to write to {target_workspace}", fg="red"
        )
        sys.exit(1)
    except Exception as e:
        click.secho(f"Error: Failed to copy scaffold - {str(e)}", fg="red")
        sys.exit(1)


if __name__ == "__main__":
    rl_group()
