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


@click.command()
@click.option(
    "--access-key",
    default=None,
    help="Volcengine access key",
)
@click.option(
    "--secret-key",
    default=None,
    help="Volcengine secret key",
)
@click.option("--name", help="Expected Volcengine FaaS application name")
@click.option("--path", default=".", help="Local project path")
def deploy(access_key: str, secret_key: str, name: str, path: str) -> None:
    """Deploy a user project to Volcengine FaaS application."""
    from pathlib import Path

    from veadk.config import getenv
    from veadk.integrations.ve_faas.ve_faas import VeFaaS

    if not access_key:
        access_key = getenv("VOLCENGINE_ACCESS_KEY")
    if not secret_key:
        secret_key = getenv("VOLCENGINE_SECRET_KEY")

    user_proj_abs_path = Path(path).resolve()

    ve_faas = VeFaaS(access_key=access_key, secret_key=secret_key)
    ve_faas.deploy(name=name, path=str(user_proj_abs_path))
