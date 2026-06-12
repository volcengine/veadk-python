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
from agentkit.toolkit.cli.cli import app as agentkit_typer_app
from typer.main import get_command


@click.group()
def agentkit():
    """AgentKit-compatible commands"""
    pass


agentkit_commands = get_command(agentkit_typer_app)

# Re-export the AgentKit CLI's subcommands under `veadk agentkit`. Iterate by
# duck-typing on `.commands` rather than gating on `isinstance(..., click.Group)`:
# since Typer 0.26 a TyperGroup is no longer a click.Group subclass, so the
# isinstance check silently evaluates False and drops every command.
for cmd_name, cmd in getattr(agentkit_commands, "commands", {}).items():
    agentkit.add_command(cmd, name=cmd_name)
