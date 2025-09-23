from typing import Any, Optional, Union

from pydantic import BaseModel, Field
from typing_extensions import Literal


class CreateVeFaaSConfig(BaseModel):
    region: Optional[str] = ""

    application_name: Optional[str] = ""

    function_name: Optional[str] = ""

    function_description: Optional[str] = (
        "Created by Volcengine Agent Development Kit (VeADK)"
    )

    function_startup_command: str = "bash ./run.sh"

    function_envs: list[dict[str, Any]] = Field(
        default_factory=lambda: [
            {"VOLCENGINE_ACCESS_KEY": None},
            {"VOLCENGINE_SECRET_KEY": None},
        ]
    )
    """Environment variables for the function instance."""

    function_tags: dict[str, str] = {"provider": "veadk"}

    function_runtime: str = "native-python3.10/v1"

    function_memory_in_mb: int = 2048
    """Memory size in MB. Default is 2GB. CPU core is allocated based on memory size / 2."""


class CreateVeApigConfig(BaseModel):
    instance_name: Optional[str] = ""

    service_name: Optional[str] = ""

    upstream_name: Optional[str] = ""

    enable_key_auth: bool = True

    enable_mcp_session_keepalive: bool = True


class VeDeployConfig(BaseModel):
    vefaas: CreateVeFaaSConfig = Field(default_factory=CreateVeFaaSConfig)

    veapig: CreateVeApigConfig = Field(default_factory=CreateVeApigConfig)

    user_project_path: str = "."
    """Always use current dir as the working directory."""

    entrypoint_agent: Optional[str] = ""

    ignore_files: list[str] = Field(default_factory=lambda: ["*.pyc", "__pycache__"])

    deploy_mode: Union[Literal["A2A/MCP", "WEB"], int] = "A2A/MCP"
    """0 for `A2A/MCP` mode, 1 for `WEB` mode. Or, use literal to define this attribute."""
