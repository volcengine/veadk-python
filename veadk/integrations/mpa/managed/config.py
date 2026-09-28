"""Validated profiles for CLI YAML and built-in Studio MPA provisioning."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from sqlalchemy.engine import make_url

from .network import NetworkOptions
from .studio_profile import studio_profile_values

ADMIN_DATABASE_NAME = "mpa_admin_db"
ADMIN_WORKSPACE_NAME = "mpa_admin_workspace"
STUDIO_MPA_IDENTITY_FIELDS = (
    ("VEADK_STUDIO_MPA_USER_POOL_NAME", "user_pool_name", "MPA_USER_POOL_NAME"),
    (
        "VEADK_STUDIO_MPA_USER_POOL_CLIENT_NAME",
        "user_pool_client_name",
        "MPA_USER_POOL_CLIENT_NAME",
    ),
    (
        "VEADK_STUDIO_MPA_IDENTITY_CALLBACK_URL",
        "identity_callback_url",
        "IDENTITY_CALLBACK_URL",
    ),
    ("VEADK_STUDIO_MPA_IDENTITY_REGION", "identity_region", "IDENTITY_REGION"),
)


class ConfigurationError(ValueError):
    """A safe configuration error without user input or secret values."""


def reuse_studio_identity(values: dict, runtime_env: dict[str, str]) -> None:
    """Apply one complete Studio-owned Identity set without hiding YAML conflicts."""
    stored = [
        os.getenv(env_key, "").strip() for env_key, _, _ in STUDIO_MPA_IDENTITY_FIELDS
    ]
    if not any(stored):
        return
    if not all(stored):
        raise ConfigurationError("Incomplete Studio MPA identity configuration")
    for (_env_key, field, runtime_key), expected in zip(
        STUDIO_MPA_IDENTITY_FIELDS, stored, strict=True
    ):
        for explicit in (values.get(field), runtime_env.get(runtime_key)):
            if explicit and str(explicit).strip() != expected:
                raise ConfigurationError(
                    f"MPA identity {field} differs from Studio deployment"
                )
        values[field] = expected


def validate_creation_resources(values: dict[str, str]) -> dict[str, str]:
    """Validate nonsecret, per-creation resource choices."""
    selected = {
        key: str(values.get(key, "")).strip()
        for key in ("pgHost", "pgPort", "openvikingUrl", "openvikingResourceId")
    }
    host, port = selected["pgHost"], selected["pgPort"]
    if (
        bool(host) != bool(port)
        or host
        and (
            len(host) > 255
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", host)
            or ".." in host
        )
    ):
        raise ConfigurationError("Enter a valid PostgreSQL host and port")
    if port and (
        not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535
    ):
        raise ConfigurationError("Enter a valid PostgreSQL port")
    url, resource_id = selected["openvikingUrl"], selected["openvikingResourceId"]
    api_key = str(values.get("openvikingApiKey", ""))
    if any((url, resource_id, api_key)) and not all(
        (url, resource_id, api_key.strip())
    ):
        raise ConfigurationError(
            "Enter an OpenViking URL, resource ID and API Key together"
        )
    if url:
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
            port_number = parsed.port
        except ValueError:
            raise ConfigurationError(
                "Enter a valid HTTPS OpenViking service URL"
            ) from None
        if (
            len(url) > 1024
            or any(c.isspace() for c in url)
            or parsed.scheme != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or ":" in parsed.netloc
            or port_number is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ConfigurationError("Enter a valid HTTPS OpenViking service URL")
    if resource_id and (
        not url
        or len(resource_id) > 128
        or not re.fullmatch(r"ov-[a-zA-Z0-9_-]+", resource_id)
    ):
        raise ConfigurationError("Enter a valid OpenViking URL and resource ID")
    return selected


def validate_image_reference(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if (
        len(value) > 1024
        or not re.fullmatch(r"[A-Za-z0-9._:/@-]+", value)
        or "//" in value
        or ("@" in value and not re.fullmatch(r"[^@]+@sha256:[a-fA-F0-9]{64}", value))
    ):
        raise ValueError("Invalid container image reference")
    return value


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


class Runtime(Options):
    image: str | None = Field(default=None, min_length=1, pattern=r"^[^\s<>]+$")
    role_name: str | None = Field(default=None, min_length=1)
    cpu_milli: int | None = Field(default=None, gt=0)
    memory_mb: int | None = Field(default=None, gt=0)
    min_instance: int | None = Field(default=None, ge=0)
    max_instance: int | None = Field(default=None, gt=0)
    max_concurrency: int | None = Field(default=None, gt=0)
    apmplus_enable: bool | None = None
    project_name: str | None = Field(default=None, min_length=1)
    env: dict[str, str] = Field(default_factory=dict)

    @field_validator("env")
    @classmethod
    def validate_environment(cls, value):
        reserved = {
            "MPA_AGENT_ID",
            "AGENTKIT_RUNTIME_ID",
            "AGENTKIT_TOOL_ID",
            "AGENTKIT_TOOL_REGION",
            "SKILL_SPACE_ID",
            "PGDATABASE",
            "A2A_PUBLIC_URL",
            "CODEX_MCP_RUNTIME_API_KEY",
            "CHANNEL_STATE_ENCRYPTION_KEY",
            "DEPLOYMENT_DATABASE_ADMIN_URL",
            "SHARED_APIG_DATABASE_URL",
            "MODEL_AGENT_CLIENT_REQ_ID",
            "OTEL_SERVICE_NAME",
        }
        if any(
            not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key) or key in reserved
            for key in value
        ):
            raise ValueError("Invalid or provisioner-owned environment key")
        return value

    @model_validator(mode="after")
    def validate_scaling(self):
        if (
            self.min_instance is not None
            and self.max_instance is not None
            and self.min_instance > self.max_instance
        ):
            raise ValueError("Minimum instances exceed maximum instances")
        return self


class PostgresWorkspaces(Options):
    mode: Literal["manual", "auto"] = "manual"
    legacy_urls: Literal["reject", "ignore"] = "reject"
    admin_workspace_id: str = Field(
        default="", max_length=128, pattern=r"^[A-Za-z0-9_-]*$"
    )
    business_workspace_id: str = Field(
        default="", max_length=128, pattern=r"^[A-Za-z0-9_-]*$"
    )
    admin_workspace_name: Literal["mpa_admin_workspace"] = ADMIN_WORKSPACE_NAME
    business_workspace_name: str = Field(
        default="mpa_business_workspace",
        min_length=1,
        max_length=63,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    project_name: str = Field(default="default", min_length=1, max_length=128)
    bootstrap_path: str = Field(default=".adk/mpa-pg-bootstrap.sqlite3", min_length=1)
    timeout_seconds: int = Field(default=600, ge=30, le=1800)
    admin_database_url_env: str = Field(
        default="MPA_ADMIN_DATABASE_ADMIN_URL", pattern=r"^[A-Z][A-Z0-9_]{0,127}$"
    )

    @model_validator(mode="after")
    def distinct_workspaces(self):
        if self.mode != "auto" and self.legacy_urls != "reject":
            raise ValueError("Ignoring legacy URLs requires automatic PostgreSQL mode")
        if self.mode == "manual" and not (
            self.admin_workspace_id and self.business_workspace_id
        ):
            raise ValueError("Manual configuration requires both Workspace IDs")
        if (
            self.admin_workspace_id
            and self.admin_workspace_id == self.business_workspace_id
        ):
            raise ValueError("Management and business Workspaces must differ")
        if self.business_workspace_name == self.admin_workspace_name:
            raise ValueError("Management and business Workspace names must differ")
        return self


class Managed(Options):
    version: Literal[1]
    database_admin_url_env: str = "DEPLOYMENT_DATABASE_ADMIN_URL"
    shared_database_url_env: str = "SHARED_APIG_DATABASE_URL"
    postgres: PostgresWorkspaces | None = None
    credential_file: str = ""
    from_runtime: str = ""
    template_file: str = ""
    network: Network = Field(default_factory=Network)
    apig: Apig = Field(default_factory=Apig)
    runtime: Runtime = Field(default_factory=Runtime)
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
    openviking_enabled: bool | None = None

    def image_defaults(self):
        runtime_image = self.managed.runtime.image or (
            (self.template or {}).get("ArtifactUrl", "")
            if self.template or self.managed.from_runtime
            else self.values.get("image", "")
        )
        try:
            return {
                "runtimeImage": validate_image_reference(runtime_image),
                "workerImage": validate_image_reference(self.managed.worker.image),
            }
        except (ValueError, AttributeError):
            raise ConfigurationError(
                "Invalid configured container image reference"
            ) from None

    def summary(self):
        auto = (
            self.managed.postgres is not None and self.managed.postgres.mode == "auto"
        )
        admin = make_url(self.admin_url) if self.admin_url and not auto else None
        migration_required = auto and bool(self.shared_url)
        return {
            **self.image_defaults(),
            "pgHost": (admin.host or "") if admin else "",
            "pgPort": str(admin.port or 5432) if admin else "",
            **({"postgresMode": "auto"} if auto else {}),
            **({"postgresMigrationRequired": True} if migration_required else {}),
            **(
                {
                    "postgresLayout": "split-workspaces",
                    "adminWorkspaceName": ADMIN_WORKSPACE_NAME,
                    "adminDatabaseName": ADMIN_DATABASE_NAME,
                }
                if self.managed.postgres
                else {}
            ),
            "region": self.region,
            "configured": not migration_required,
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


def with_creation_images(profile: Profile, images: dict[str, str]) -> Profile:
    managed = profile.managed.model_copy(deep=True)
    runtime_image = validate_image_reference(images.get("runtimeImage", ""))
    worker_image = validate_image_reference(images.get("workerImage", ""))
    if runtime_image:
        managed.runtime.image = runtime_image
    if worker_image:
        managed.worker.image = worker_image
        managed.worker.existing_id = ""
    return replace(profile, managed=managed)


def with_creation_resources(profile: Profile, resources: dict[str, str]) -> Profile:
    selected = validate_creation_resources(resources)
    managed = profile.managed.model_copy(deep=True)
    host, port = selected["pgHost"], selected["pgPort"]
    if (
        profile.managed.postgres
        and profile.managed.postgres.mode == "auto"
        and profile.shared_url
    ):
        raise ConfigurationError(
            "Migrate the existing shared registry before automatic PG provisioning"
        )
    if (
        profile.managed.postgres
        and profile.managed.postgres.mode == "auto"
        and (host or port)
    ):
        raise ConfigurationError(
            "Automatic PG provisioning does not accept PostgreSQL host or port inputs"
        )
    if host:
        admin = make_url(profile.admin_url)
        if (host.lower(), int(port)) != (
            (admin.host or "").lower(),
            admin.port or 5432,
        ):
            raise ConfigurationError(
                "PostgreSQL host and port must match the configured administrator connection"
            )
        managed.runtime.env.update(
            PGHOST=admin.host or host, PGPORT=str(admin.port or 5432)
        )
    for key in list(managed.runtime.env):
        if key.startswith("OPENVIKING_"):
            managed.runtime.env.pop(key)
    if selected["openvikingUrl"]:
        managed.runtime.env["OPENVIKING_URL"] = selected["openvikingUrl"]
        managed.runtime.env["OPENVIKING_RESOURCE_ID"] = selected["openvikingResourceId"]
        managed.runtime.env["OPENVIKING_API_KEY"] = resources["openvikingApiKey"]
        managed.runtime.env["OPENVIKING_USER"] = "default"
    return replace(
        profile, managed=managed, openviking_enabled=bool(selected["openvikingUrl"])
    )


def _secret(name: str) -> str:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", name):
        raise ConfigurationError("Invalid secret environment variable name")
    value = os.getenv(name, "")
    if not value or value.startswith("<"):
        raise ConfigurationError(f"Missing server environment variable: {name}")
    return value


def validate_postgres_layout(profile: Profile) -> None:
    """Check configured boundaries; cloud Workspace ownership is operator-verified."""
    if not profile.managed.postgres:
        return
    if profile.managed.postgres.mode == "auto":
        return
    business, shared = make_url(profile.admin_url), make_url(profile.shared_url)
    if shared.database != ADMIN_DATABASE_NAME:
        raise ConfigurationError("The management connection must use mpa_admin_db")
    if (business.host or "").lower() == (shared.host or "").lower():
        raise ConfigurationError(
            "Management and business Workspaces require distinct PostgreSQL hosts"
        )
    if not shared.username:
        raise ConfigurationError("The management connection requires a database owner")


def management_admin_url(profile: Profile, value: str = "") -> str:
    """Resolve the maintenance credential only for explicit registry initialization."""
    settings = profile.managed.postgres
    if settings is None:
        raise ConfigurationError(
            "Configure managed.postgres before preparing mpa_admin_db"
        )
    validate_postgres_layout(profile)
    value = value or _secret(settings.admin_database_url_env)
    try:
        admin, shared = make_url(value), make_url(profile.shared_url)
        if (
            admin.get_backend_name() != "postgresql"
            or not admin.database
            or not admin.username
            or (admin.host or "").lower() != (shared.host or "").lower()
            or (admin.port or 5432) != (shared.port or 5432)
            or admin.database == ADMIN_DATABASE_NAME
        ):
            raise ValueError()
    except Exception:
        raise ConfigurationError(
            "Management maintenance connection must use another database on the management host/port"
        ) from None
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


def load_studio_profile(*, region: str = "") -> Profile:
    """Load the code-owned Studio profile without a configuration file."""
    return load_profile(None, region=region)


def load_profile(path: str | Path | None, *, region: str = "") -> Profile:
    try:
        file = Path(path) if path is not None else None
        if file is None:
            values = studio_profile_values()
        else:
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
        managed_values = dict(values["managed"])
        auto = (
            isinstance(managed_values.get("postgres"), dict)
            and managed_values["postgres"].get("mode") == "auto"
        )
        if isinstance(managed_values.get("runtime"), dict):
            managed_values["runtime"] = dict(managed_values["runtime"])
            if "env" in managed_values["runtime"]:
                managed_values["runtime"]["env"] = _resolve(
                    {
                        k: v
                        for k, v in managed_values["runtime"]["env"].items()
                        if not (auto and k.startswith("PG"))
                    }
                )
        managed = Managed.model_validate(managed_values)
        ignore_legacy_urls = (
            auto
            and managed.postgres is not None
            and managed.postgres.legacy_urls == "ignore"
        )
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
        if auto:
            admin = (
                ""
                if ignore_legacy_urls
                else os.getenv(managed.database_admin_url_env, "")
            )
            shared = (
                ""
                if ignore_legacy_urls
                else os.getenv(managed.shared_database_url_env, "")
            )
        else:
            admin = _secret(managed.database_admin_url_env)
            shared = _secret(managed.shared_database_url_env)
        for value in (admin, shared):
            if auto and not value:
                continue
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
            if file is None:
                raise ConfigurationError(
                    "Built-in Studio profile cannot use a template file"
                )
            template_path = file.parent / managed.template_file
            try:
                template = json.loads(
                    _read_configuration_file(template_path, template=True)
                )
                if auto and isinstance(template, dict):
                    template["Envs"] = [
                        item
                        for item in template.get("Envs", [])
                        if not str(item.get("Key", "")).startswith("PG")
                    ]
                template = _resolve(template)
            except json.JSONDecodeError:
                raise ConfigurationError(
                    "Invalid Runtime template JSON; check managed.template-file syntax"
                ) from None
            if not isinstance(template, dict):
                raise ConfigurationError("Runtime template must be an object")
        values = _resolve(
            {
                str(k).replace("-", "_"): v
                for k, v in values.items()
                if k != "managed"
                and not (auto and str(k).replace("-", "_").startswith("pg_"))
            }
        )
        reuse_studio_identity(values, managed.runtime.env)
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
                if auto and key.startswith("pg_"):
                    continue
                if key == "image" and managed.runtime.image:
                    continue
                if not values.get(key) or str(values[key]).startswith("<"):
                    raise ConfigurationError(f"Missing configured field: {key}")
        profile = Profile(selected, managed, values, template, admin, shared)
        validate_postgres_layout(profile)
        return profile
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
            "Unable to load MPA configuration; check server settings"
            if path is None
            else "Unable to load MPA configuration; check YAML, template and network settings"
        ) from None
