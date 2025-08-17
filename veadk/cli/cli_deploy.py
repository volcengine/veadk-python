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
