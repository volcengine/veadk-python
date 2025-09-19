from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field
from ruamel.yaml import YAML
from typing_extensions import Literal


class _VeFaaSConfig(BaseModel):
    region: Optional[str] = ""

    application_name: Optional[str] = ""

    function_name: Optional[str] = ""

    enable_key_auth: bool = True

    enable_mcp_session_keepalive: bool = True

    ignore_files: list[str] = Field(default_factory=lambda: ["*.pyc", "__pycache__"])


class _VeApigConfig(BaseModel):
    instance_name: Optional[str] = ""

    service_name: Optional[str] = ""

    upstream_name: Optional[str] = ""


class _VeADKConfig(BaseModel):
    entrypoint_agent: Optional[str] = ""

    envs: list[dict[str, Any]] = Field(
        default_factory=lambda: [
            {"VOLCENGINE_ACCESS_KEY": None},
            {"VOLCENGINE_SECRET_KEY": None},
        ]
    )

    deploy_mode: Literal["A2A/MCP", "WEB"] = "A2A/MCP"


class VeDeployConfig(BaseModel):
    vefaas: _VeFaaSConfig = Field(default_factory=_VeFaaSConfig)

    veapig: _VeApigConfig = Field(default_factory=_VeApigConfig)

    veadk: _VeADKConfig = Field(default_factory=_VeADKConfig)

    @classmethod
    def read_yaml(cls, file_path: Path, encoding: str = "utf-8") -> Dict:
        """Read yaml file and return a dict"""
        if not file_path.exists():
            return {}
        with open(file_path, "r", encoding=encoding) as file:
            return yaml.safe_load(file)

    @classmethod
    def from_yaml_file(cls, file_path: Path):
        """Read yaml file and return a YamlModel instance"""
        return cls(**cls.read_yaml(file_path))

    def to_yaml_file(self, file_path: Path, encoding: str = "utf-8") -> None:
        """Dump YamlModel instance to yaml file"""
        yaml_obj = YAML()
        yaml_obj.default_flow_style = False
        yaml_obj.indent(mapping=2, sequence=4, offset=2)
        with open(file_path, "w", encoding="utf-8") as f:
            yaml_obj.dump(self.model_dump(), f)
