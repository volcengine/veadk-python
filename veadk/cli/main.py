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

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import typer
import uvicorn

from veadk.utils.logger import get_logger
from veadk.version import VERSION

logger = get_logger(__name__)

app = typer.Typer(name="vego")


def set_variable_in_file(file_path: str, setting_values: dict):
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

    print("Your project has beed created.")


@app.command()
def init():
    """Init a veadk project that can be deployed to Volcengine VeFaaS."""
    from rich.prompt import Confirm, Prompt

    cwd = Path.cwd()
    template_dir = Path(__file__).parent.resolve() / "services" / "vefaas" / "template"

    local_dir_name = Prompt.ask("Local directory name", default="veadk-cloud-proj")

    target_dir = cwd / local_dir_name

    if target_dir.exists():
        response = Confirm.ask(
            f"Target directory '{target_dir}' already exists, do you want to overwrite it?: "
        )
        if not response:
            print("Operation cancelled.")
            return
        else:
            shutil.rmtree(target_dir)
            print(f"Deleted existing directory: {target_dir}")

    vefaas_application_name = Prompt.ask(
        "Volcengine FaaS application name", default="veadk-cloud-agent"
    )

    gateway_name = Prompt.ask(
        "Volcengine gateway instance name", default="", show_default=True
    )

    gateway_service_name = Prompt.ask(
        "Volcengine gateway service name", default="", show_default=True
    )

    gateway_upstream_name = Prompt.ask(
        "Volcengine gateway upstream name", default="", show_default=True
    )

    deploy_mode_options = {
        "1": "A2A Server",
        "2": "VeADK Studio",
        "3": "VeADK Web / Google ADK Web",
    }

    deploy_mode = Prompt.ask(
        """Choose your deploy mode:
1. A2A Server
2. VeADK Studio
3. VeADK Web / Google ADK Web
""",
        default="1",
    )

    if deploy_mode in deploy_mode_options:
        deploy_mode = deploy_mode_options[deploy_mode]
    else:
        print("Invalid deploy mode, set default to A2A Server")
        deploy_mode = deploy_mode_options["1"]

    setting_values = {
        "VEFAAS_APPLICATION_NAME": vefaas_application_name,
        "GATEWAY_NAME": gateway_name,
        "GATEWAY_SERVICE_NAME": gateway_service_name,
        "GATEWAY_UPSTREAM_NAME": gateway_upstream_name,
        "USE_STUDIO": deploy_mode == deploy_mode_options["2"],
        "USE_ADK_WEB": deploy_mode == deploy_mode_options["3"],
    }

    shutil.copytree(template_dir, target_dir)
    set_variable_in_file(target_dir / "deploy.py", setting_values)


# @app.command()
# def web(
#     path: str = typer.Option(".", "--path", help="Agent project path"),
# ):
#     from google.adk.cli import cli_tools_click

#     def my_decorator(func):
#         @wraps(func)
#         def wrapper(*args, **kwargs):
#             adk_app: FastAPI = func(*args, **kwargs)
#             import importlib.util
#             import mimetypes

#             from fastapi.staticfiles import StaticFiles

#             mimetypes.add_type("application/javascript", ".js", True)
#             mimetypes.add_type("text/javascript", ".js", True)

#             spec = importlib.util.find_spec("veadk.cli.browser")
#             if spec is not None:
#                 ANGULAR_DIST_PATH = spec.submodule_search_locations[0]
#                 logger.info(f"Static source path: {ANGULAR_DIST_PATH}")
#             else:
#                 raise Exception("veadk.cli.browser not found")

#             # ----- 8< Unmount app -----
#             from starlette.routing import Mount

#             for index, route in enumerate(adk_app.routes):
#                 if isinstance(route, Mount) and route.path == "/dev-ui":
#                     del adk_app.routes[index]
#                     break
#             # ----- 8< Mount our app -----

#             adk_app.mount(
#                 "/dev-ui/",
#                 StaticFiles(directory=ANGULAR_DIST_PATH, html=True),
#                 name="static",
#             )

#             from fastapi.middleware.cors import CORSMiddleware

#             adk_app.add_middleware(
#                 CORSMiddleware,
#                 allow_origins=["*"],
#                 allow_credentials=True,
#                 allow_methods=["*"],
#                 allow_headers=["*"],
#             )
#             return adk_app

#         return wrapper

#     # Monkey patch
#     fast_api.get_fast_api_app = my_decorator(fast_api.get_fast_api_app)

#     # reload cli_tools_click
#     importlib.reload(cli_tools_click)

#     agents_dir = str(Path(path).resolve())
#     logger.info(f"Agents dir is {agents_dir}")
#     cli_tools_click.cli_web.main(args=[agents_dir])


@app.command()
def web(
    session_service_uri: str = typer.Option(
        None,
        "--session_service_uri",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
    ),
):
    from google.adk.memory import in_memory_memory_service

    from veadk.memory.long_term_memory import LongTermMemory

    in_memory_memory_service.InMemoryMemoryService = LongTermMemory

    from google.adk.cli import cli_tools_click

    importlib.reload(cli_tools_click)
    agents_dir = os.getcwd()
    if not session_service_uri:
        session_service_uri = ""

    cli_tools_click.cli_web.main(
        args=[agents_dir, "--session_service_uri", session_service_uri, "--host", host]
    )


@app.command()
def studio(
    path: str = typer.Option(".", "--path", help="Project path"),
):
    from veadk.cli.studio.fast_api import get_fast_api_app

    path = Path(path).resolve()

    agent_py_path = os.path.join(path, "agent.py")
    if not os.path.exists(agent_py_path):
        raise FileNotFoundError(f"agent.py not found in {path}")

    spec = spec_from_file_location("agent", agent_py_path)
    if spec is None:
        raise ImportError(f"Could not load spec for agent from {agent_py_path}")

    module = module_from_spec(spec)

    try:
        spec.loader.exec_module(module)
    except Exception as e:
        raise ImportError(f"Failed to execute agent.py: {e}")

    agent = None
    short_term_memory = None
    try:
        agent = module.agent
        short_term_memory = module.short_term_memory
    except AttributeError as e:
        missing = str(e).split("'")[1] if "'" in str(e) else "unknown"
        raise AttributeError(f"agent.py is missing required variable: {missing}")

    app = get_fast_api_app(agent, short_term_memory)

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        loop="asyncio",  # for deepeval
    )


@app.command()
def prompt(
    path: str = typer.Option(
        ...,
        "--path",
        help="Your agent file path. Please ensure that your agent(s) are global variable(s).",
    ),
    feedback: str = typer.Option(
        "",
        "--feedback",
        help="Feedback of prompt from agent evaluation.",
    ),
    api_key: str = typer.Option(
        ..., "--api-key", help="API Key of AgentPilot Platform"
    ),
    model_name: str = typer.Option(
        "doubao-1.5-pro-32k-250115",
        "--model-name",
        help="Model name for prompt optimization",
    ),
):
    from veadk import Agent

    """
    NOTE(nkfyz): Detecting agents from a file is not fully correct, we will fix this feature asap.
    """
    module_name = "veadk_agent"
    path = Path(path).resolve()
    logger.info(f"Detect agents in {path}")

    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    globals_in_module = vars(module)  # get all global variables in module

    agents = []
    for global_variable_name, global_variable_value in globals_in_module.items():
        if isinstance(global_variable_value, Agent):
            agent = global_variable_value
            agents.append(agent)
    logger.info(f"Found {len(agents)} agent(s) in {path}")

    if len(agents) == 0:
        logger.info(
            "No agent found. Please put your agent definition as a global variable in your agent file."
        )
        print(
            f"No agent found in {path}. Please put your agent definition as a global variable in your agent file."
        )
        return

    from veadk.cli.services.agentpilot import AgentPilot

    ap = AgentPilot(api_key)
    ap.optimize(agents=agents, feedback=feedback, model_name=model_name)


# @app.command()
# def studio():
#     import os

#     # pre-load
#     from veadk import Agent  # noqa

#     os.environ["VEADK_STUDIO_AGENTS_DIR"] = os.getcwd()
#     app_path = os.path.join(os.path.dirname(__file__), "../../app/app.py")

#     os.system(f"streamlit run {app_path}")


@app.command()
def deploy(
    access_key: str = typer.Option(..., "--access-key", help="Access Key"),
    secret_key: str = typer.Option(..., "--secret-key", help="Secret Key"),
    name: str = typer.Option(..., "--name", help="Deployment name"),
    path: str = typer.Option(".", "--path", help="Project path"),
):
    from veadk.cli.services.vefaas import VeFaaS

    path = Path(path).resolve()
    vefaas = VeFaaS(access_key, secret_key)
    vefaas.deploy(name=name, path=path)


@app.command()
def log(
    access_key: str = typer.Option(..., "--access-key", help="Access Key"),
    secret_key: str = typer.Option(..., "--secret-key", help="Secret Key"),
    query: str = typer.Option(..., "--query", help="Query statement"),
    topic_id: str = typer.Option(..., "--topic-id", help="Topic ID in VeTLS"),
    dump_path: str = typer.Option(
        ".", "--dump-path", help="Local path for log storage file"
    ),
):
    path = Path(dump_path).resolve()

    from veadk.cli.services.vetls import VeTLS

    vetls = VeTLS(access_key, secret_key, dump_path=str(path))
    vetls.query(topic_id=topic_id, query=query)


@app.command()
def version():
    print(f"VeADK {VERSION}")


if __name__ == "__main__":
    app()
