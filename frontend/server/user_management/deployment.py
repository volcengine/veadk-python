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

"""Initialize Identity roles before publishing a Studio deployment"""

from collections.abc import Callable, Mapping
from pathlib import Path
from zipfile import ZipFile

import click

from veadk.utils.cloud_provider import CloudProvider

from .directory import IdentityDirectory
from .errors import UserManagementError
from .service import UserManagementService


def package_supports_identity_roles(package: Path) -> bool:
    """Check the shipped code, not the updating process's installed version"""
    module = "frontend/server/user_management/service.py"
    if (package / "site-packages" / module).is_file():
        return True
    for wheel in package.glob("veadk*.whl"):
        with ZipFile(wheel) as archive:
            if module in archive.namelist():
                return True
    return False


def prepare_identity_roles(
    *,
    pool_uid: str,
    client_uid: str,
    provider: CloudProvider,
    region: str,
    access_key: str,
    secret_key: str,
    session_token: str = "",
    super_admin: str | None = None,
    legacy_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Persist the initial role assignment, then return the runtime switch"""
    if not pool_uid or not client_uid:
        raise click.ClickException(
            "Identity user management requires an existing user pool and client"
        )
    legacy = legacy_environment or {}
    legacy_pool = legacy.get("OAUTH2_USER_POOL_ID") or legacy.get(
        "VEADK_STUDIO_USER_POOL_ID"
    )
    legacy_client = legacy.get("OAUTH2_USER_POOL_CLIENT_ID")
    if (legacy_pool and legacy_pool != pool_uid) or (
        legacy_client and legacy_client != client_uid
    ):
        raise click.ClickException(
            "Legacy roles belong to a different Identity pool/client"
        )
    directory = IdentityDirectory(
        pool_uid, provider, region, lambda: (access_key, secret_key, session_token)
    )
    service = UserManagementService(directory, pool_uid, client_uid, provider)
    try:
        service.initialize(
            (super_admin or legacy.get("VEADK_STUDIO_SUPER_ADMIN", "")).strip(),
            legacy.get("VEADK_STUDIO_ADMINS", ""),
            legacy.get("VEADK_STUDIO_DEVELOPERS", ""),
            allow_initialize=legacy.get("VEADK_STUDIO_IDENTITY_ROLES", "")
            .strip()
            .lower()
            not in {"1", "true", "yes"},
        )
    except UserManagementError as error:
        messages = {
            "roles_not_initialized": (
                "Identity role metadata is missing; restore the application role groups "
                "before retrying"
            ),
            "bootstrap_user_not_unique": (
                "The initial super administrator must match exactly one existing "
                "Identity user. Add or sign in that user first, then retry"
            ),
            "legacy_role_member_not_unique": (
                "An old admin/developer entry cannot be matched uniquely to an "
                "Identity user. Correct the old role list before migrating"
            ),
        }
        raise click.ClickException(
            f"Studio role setup failed for pool {pool_uid}: "
            f"{messages.get(error.code, error.code)}"
        ) from error
    # The bootstrap identity is already stored in Identity; instances only read it
    return {
        "VEADK_STUDIO_IDENTITY_ROLES": "1",
        "VEADK_STUDIO_SUPER_ADMIN": "",
        "VEADK_STUDIO_ADMINS": "",
        "VEADK_STUDIO_DEVELOPERS": "",
    }


def clear_legacy_role_environment(
    *,
    function_client,
    function_id: str,
    pool_uid: str,
    client_uid: str,
) -> None:
    """Clear the cloud Function configuration after Identity initialization succeeds

    Startup can run inside an ongoing Application release, so this updates only
    the Function configuration and does not submit a competing release
    """
    import volcenginesdkvefaas as sdk

    function = function_client.get_function(sdk.GetFunctionRequest(id=function_id))
    environment = {
        str(item.key): str(item.value)
        for item in (getattr(function, "envs", None) or [])
        if getattr(item, "key", None)
    }
    if (
        environment.get("OAUTH2_USER_POOL_ID")
        or environment.get("VEADK_STUDIO_USER_POOL_ID")
    ) != pool_uid or environment.get("OAUTH2_USER_POOL_CLIENT_ID") != client_uid:
        raise click.ClickException(
            "Studio Identity configuration changed during migration"
        )
    cleaned = {
        **environment,
        "VEADK_STUDIO_IDENTITY_ROLES": "1",
        "VEADK_STUDIO_SUPER_ADMIN": "",
        "VEADK_STUDIO_ADMINS": "",
        "VEADK_STUDIO_DEVELOPERS": "",
    }
    if cleaned != environment:
        function_client.update_function(
            sdk.UpdateFunctionRequest(
                id=function_id,
                envs=[
                    sdk.EnvForUpdateFunctionInput(key=key, value=value)
                    for key, value in cleaned.items()
                ],
            )
        )


def initialize_runtime_roles(
    *,
    pool_uid: str,
    client_uid: str,
    provider: CloudProvider,
    identity_region: str,
    credentials: Callable[[], tuple[str, str, str | None]],
    environment: Mapping[str, str],
    super_admin: str = "",
    admins: str = "",
    developers: str = "",
) -> UserManagementService:
    """Migrate older releases on startup before accepting authenticated requests"""
    initialized = environment.get(
        "VEADK_STUDIO_IDENTITY_ROLES", ""
    ).strip().lower() in {"1", "true", "yes"}
    service = UserManagementService(
        IdentityDirectory(pool_uid, provider, identity_region, credentials),
        pool_uid,
        client_uid,
        provider,
    )
    try:
        service.initialize(
            super_admin, admins, developers, allow_initialize=not initialized
        )
    except UserManagementError as error:
        raise click.ClickException(
            f"Studio Identity role setup failed: {error.code}; check Identity user/group "
            "permissions and the legacy role lists, then retry"
        ) from error
    legacy_keys = (
        "VEADK_STUDIO_SUPER_ADMIN",
        "VEADK_STUDIO_ADMINS",
        "VEADK_STUDIO_DEVELOPERS",
    )
    if (not initialized or any(environment.get(key) for key in legacy_keys)) and (
        function_id := environment.get("VEADK_STUDIO_FUNCTION_ID")
    ):
        from veadk.integrations.ve_faas.ve_faas import VeFaaS

        ak, sk, token = credentials()
        deployment = VeFaaS(
            access_key=ak,
            secret_key=sk,
            session_token=token or "",
            region=environment.get("VEADK_STUDIO_DEPLOY_REGION") or identity_region,
            project_name=environment.get("VEADK_STUDIO_PROJECT", "default"),
            provider=provider,
        )
        clear_legacy_role_environment(
            function_client=deployment.client,
            function_id=function_id,
            pool_uid=pool_uid,
            client_uid=client_uid,
        )
    return service
