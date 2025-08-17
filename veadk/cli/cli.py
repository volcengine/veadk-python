import click

from veadk.cli.cli_deploy import deploy
from veadk.cli.cli_init import init
from veadk.cli.cli_prompt import prompt


@click.group()
def veadk():
    """Volcengine ADK command line tools"""
    pass


veadk.add_command(deploy)
veadk.add_command(prompt)
veadk.add_command(init)

if __name__ == "__main__":
    veadk()
