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

from veadk.cli.cli_deploy import deploy
from veadk.cli.cli_init import init
from veadk.cli.cli_prompt import prompt
from veadk.cli.cli_studio import studio
from veadk.cli.cli_web import web
from veadk.version import VERSION


@click.group()
@click.version_option(
    version=VERSION, prog_name="Volcengine Agent Development Kit (VeADK)"
)
def veadk():
    """Volcengine ADK command line tools"""
    pass


veadk.add_command(deploy)
veadk.add_command(init)
veadk.add_command(prompt)
veadk.add_command(studio)
veadk.add_command(web)

if __name__ == "__main__":
    veadk()
