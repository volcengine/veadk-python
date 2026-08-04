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

"""CLI wrapper for Studio GitHub CI/CD pull request setup."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from veadk.cli.github_cicd import GitHubCicdError, create_github_cicd_pipeline


@click.command("github-cicd-pipeline")
@click.option("--github-url", required=True, help="GitHub repository URL.")
@click.option(
    "--github-branch",
    default="main",
    show_default=True,
    help="Base branch for the Studio pull request.",
)
@click.option(
    "--github-token",
    required=True,
    help="GitHub token with repository contents and pull request permissions.",
)
@click.option(
    "--project-json",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to an AgentProject JSON file exported by Studio.",
)
@click.option(
    "--region",
    default="cn-beijing",
    show_default=True,
    help="AgentKit Runtime region.",
)
def github_cicd_pipeline(
    github_url: str,
    github_branch: str,
    github_token: str,
    project_json: Path,
    region: str,
) -> None:
    """Create or update the GitHub PR for the generated Agent project."""

    def progress(message: str) -> None:
        click.echo(f"[github-cicd] {message}")

    try:
        project: dict[str, Any] = json.loads(project_json.read_text(encoding="utf-8"))
        result = create_github_cicd_pipeline(
            project=project,
            github_url=github_url,
            github_token=github_token,
            base_branch=github_branch,
            region=region,
            progress=progress,
        )
    except json.JSONDecodeError as error:
        raise click.ClickException(f"Invalid AgentProject JSON: {error}") from error
    except GitHubCicdError as error:
        raise click.ClickException(str(error)) from error

    click.echo(json.dumps(result, ensure_ascii=False, indent=2))
