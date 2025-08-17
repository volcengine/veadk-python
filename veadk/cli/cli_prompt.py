import click


@click.command()
@click.option(
    "--path", default=".", help="Agent file path with global variable `agent=...`"
)
@click.option("--feedback", default=None, help="Suggestions for prompt optimization")
@click.option("--api-key", default=None, help="API Key of PromptPilot")
@click.option(
    "--model-name",
    default="doubao-1.5-pro-32k-250115",
    help="Model name for prompt optimization",
)
def prompt(path: str, feedback: str, api_key: str, model_name: str) -> None:
    """Optimize agent system prompt from a local file."""
    from pathlib import Path

    from veadk.agent import Agent
    from veadk.config import getenv
    from veadk.integrations.ve_prompt_pilot.ve_prompt_pilot import VePromptPilot
    from veadk.utils.misc import load_module_from_file

    module_name = "agents_for_prompt_pilot"
    module_abs_path = Path(path).resolve()

    module = load_module_from_file(
        module_name=module_name, file_path=str(module_abs_path)
    )

    # get all global variables from module
    globals_in_module = vars(module)

    agents = []
    for global_variable_name, global_variable_value in globals_in_module.items():
        if isinstance(global_variable_value, Agent):
            agent = global_variable_value
            agents.append(agent)

    if len(agents) > 0:
        click.echo(f"Found {len(agents)} agents in {module_abs_path}")

        if not api_key:
            api_key = getenv("PROMPT_PILOT_API_KEY")
        ve_prompt_pilot = VePromptPilot(api_key)
        ve_prompt_pilot.optimize(
            agents=agents, feedback=feedback, model_name=model_name
        )
    else:
        click.echo(f"No agents found in {module_abs_path}")
