import click
from agentkit.toolkit.cli.cli import app as agentkit_typer_app
from typer.main import get_command


@click.group()
def agentkit():
    """AgentKit-compatible commands"""
    pass


agentkit_commands = get_command(agentkit_typer_app)

if isinstance(agentkit_commands, click.Group):
    for cmd_name, cmd in agentkit_commands.commands.items():
        agentkit.add_command(cmd, name=cmd_name)
