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

from pathlib import Path
from typing import Literal

import click


@click.command()
@click.option(
    "--backend",
    type=click.Choice(
        ["local", "opensearch", "viking", "redis"],
        case_sensitive=False,
    ),
    required=True,
)
@click.option(
    "--app_name",
    default="",
    help="`app_name` for init your knowledgebase",
)
@click.option(
    "--index",
    default="",
    help="Knowledgebase index",
)
@click.option(
    "--path",
    required=True,
    help="Knowledge file or directory path",
)
def add(
    backend: Literal["local", "opensearch", "viking", "redis"],
    app_name: str,
    index: str,
    path: str,
):
    """Add files to knowledgebase"""
    _path = Path(path)
    assert _path.exists(), f"Path {path} not exists. Please check your input."

    from veadk.knowledgebase import KnowledgeBase

    knowledgebase = KnowledgeBase(backend=backend, app_name=app_name, index=index)

    if _path.is_file():
        knowledgebase.add_from_files(files=[path])
    elif _path.is_dir():
        knowledgebase.add_from_directory(directory=path)
    else:
        raise RuntimeError(
            "Unsupported knowledgebase file type, only support a single file and a directory."
        )


@click.group()
def kb():
    """VeADK Knowledgebase management"""
    pass


kb.add_command(add)
