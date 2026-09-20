"""Shared YAML contract for CLI and Studio managed MPA provisioning."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.engine import make_url

from .network import NetworkOptions


class ConfigurationError(ValueError):
    """A safe configuration error without user input or secret values."""


class Options(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        alias_generator=lambda value: value.replace("_", "-"),
    )


class Network(Options):
    vpc_id: str = ""
    subnet_ids: list[str] = Field(default_factory=list, max_length=5)
    vpc_cidr: str = "172.20.0.0/16"
    subnet_prefix: int = Field(default=24, ge=1, le=29)
    zone: str = ""


class Worker(Options):
    existing_id: str = ""
    image: str = ""
    reference_id: str = ""
    role_name: str = "IDRoleForArkClawShareAgent"

    @model_validator(mode="after")
    def validate_source(self):
        if bool(self.existing_id) == bool(self.image):
            raise ValueError("Select an existing worker or a worker image")
        return self


class Apig(Options):
    adopt_id: str = ""


class Managed(Options):
    version: Literal[1]
    database_admin_url_env: str = "DEPLOYMENT_DATABASE_ADMIN_URL"
    shared_database_url_env: str = "SHARED_APIG_DATABASE_URL"
    credential_file: str = ""
    from_runtime: str = ""
    template_file: str = ""
    network: Network = Field(default_factory=Network)
    apig: Apig = Field(default_factory=Apig)
    worker: Worker
    timeout_seconds: int = Field(default=1800, ge=60, le=7200)

    @model_validator(mode="after")
    def validate_source(self):
        if self.from_runtime and self.template_file:
            raise ValueError("Choose one template source")
        return self


@dataclass(repr=False)
class Profile:
    region: str
    managed: Managed
    values: dict
    template: dict | None
    admin_url: str
    shared_url: str

    def summary(self):
        return {
            "region": self.region,
            "configured": True,
            "source": "reference" if self.managed.from_runtime else "template",
            "resources": [
                "network",
                "gateway",
                "database",
                "skills",
                "worker",
                "runtime",
            ],
            "checks": ["configuration"],
            "requiresLiveChecks": True,
        }


def _secret(name: str) -> str:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", name):
        raise ConfigurationError("Invalid secret environment variable name")
    value = os.getenv(name, "")
    if not value or value.startswith("<"):
        raise ConfigurationError(f"Missing server environment variable: {name}")
    return value


def _resolve(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _resolve(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v) for v in value]
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return _secret(value[2:-1])
    return value


def _read_configuration_file(path: Path, *, template: bool = False) -> str:
    label = "Runtime template" if template else "MPA creation configuration"
    setting = "managed.template-file" if template else "VEADK_MPA_CREATE_CONFIG"
    try:
        if path.stat().st_size > 262144:
            raise ConfigurationError(f"{label} exceeds 256 KiB")
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigurationError(
            f"{label} file was not found; configure {setting} with an existing file"
        ) from None
    except PermissionError:
        raise ConfigurationError(
            f"Permission denied reading {label.lower()}; grant the Studio process read access"
        ) from None
    except IsADirectoryError:
        raise ConfigurationError(
            f"{setting} must point to a file, not a directory"
        ) from None
    except UnicodeError:
        raise ConfigurationError(f"{label} must use UTF-8 encoding") from None
    except OSError:
        raise ConfigurationError(
            f"Unable to read {label.lower()}; check {setting} and file access"
        ) from None


def load_profile(path: str | Path, *, region: str = "") -> Profile:
    try:
        file = Path(path)
        try:
            values = yaml.safe_load(_read_configuration_file(file))
        except yaml.YAMLError:
            raise ConfigurationError(
                "Invalid YAML in MPA creation configuration; check its syntax"
            ) from None
        if not isinstance(values, dict) or not isinstance(values.get("managed"), dict):
            raise ConfigurationError(
                "Configure the managed section in VEADK_MPA_CREATE_CONFIG"
            )
        managed = Managed.model_validate(values["managed"])
        selected = str(values.get("region", "cn-beijing"))
        if not re.fullmatch(r"cn-[a-z]+", selected) or region and selected != region:
            raise ConfigurationError("No managed configuration for the selected region")
        NetworkOptions(
            managed.network.vpc_cidr,
            managed.network.subnet_prefix,
            managed.network.zone,
        ).validate()
        if managed.network.subnet_ids and not managed.network.vpc_id:
            raise ConfigurationError("Subnet IDs require a VPC ID")
        if managed.apig.adopt_id and not managed.network.vpc_id:
            raise ConfigurationError(
                "Explicit APIG adoption requires its existing VPC ID"
            )
        admin = _secret(managed.database_admin_url_env)
        shared = _secret(managed.shared_database_url_env)
        for value in (admin, shared):
            url = make_url(value)
            if (
                url.get_backend_name() != "postgresql"
                or not url.host
                or not url.database
            ):
                raise ConfigurationError(
                    "Administrator and shared registry URLs must use PostgreSQL"
                )
        template = None
        if managed.template_file:
            template_path = file.parent / managed.template_file
            try:
                template = _resolve(
                    json.loads(_read_configuration_file(template_path, template=True))
                )
            except json.JSONDecodeError:
                raise ConfigurationError(
                    "Invalid Runtime template JSON; check managed.template-file syntax"
                ) from None
            if not isinstance(template, dict):
                raise ConfigurationError("Runtime template must be an object")
        values = _resolve(
            {str(k).replace("-", "_"): v for k, v in values.items() if k != "managed"}
        )
        if not template and not managed.from_runtime:
            for key in (
                "image",
                "pg_host",
                "pg_user",
                "pg_password",
                "model_provider",
                "model_api_base",
                "model_api_key",
                "model_name",
            ):
                if not values.get(key) or str(values[key]).startswith("<"):
                    raise ConfigurationError(f"Missing configured field: {key}")
        return Profile(selected, managed, values, template, admin, shared)
    except ConfigurationError:
        raise
    except ValidationError as error:
        fields = sorted(
            {
                ".".join(str(p) for p in item["loc"])
                for item in error.errors(include_input=False)
            }
        )
        raise ConfigurationError(
            "Invalid managed settings: " + ", ".join(fields)
        ) from None
    except Exception:
        raise ConfigurationError(
            "Unable to load MPA configuration; check YAML, template and network settings"
        ) from None
