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

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import ANY, Mock

import httpx
import pytest
import requests
from click.testing import CliRunner

from veadk.cli.cli_frontend import studio
from veadk.cli.frontend_branding import SiteLogo
from veadk.cli.studio_package import _stage_wheel_source, build_frontend_assets
from veadk.cli.studio_update import (
    StudioDeploymentTarget,
    find_studio_deployments,
    load_deployed_site_logo,
    retry_transient_cloud_operation,
)
from veadk.integrations.ve_faas.ve_faas import VeFaaS

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


@pytest.fixture
def scheduler_deploy(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def _deploy(service: object, **kwargs: object) -> tuple[str, str, str, str, str]:
        environment_overrides = kwargs.get("environment_overrides")
        calls.append(
            {
                "service": service,
                **kwargs,
                "environment_overrides": dict(
                    cast(dict[str, object], environment_overrides)
                ),
            }
        )
        return (
            "scheduler-function",
            "scheduler-timer",
            "worker-function",
            "worker-timer",
            "studio-app",
        )

    monkeypatch.setattr(
        "frontend.service.studio_scheduler.deploy.deploy_scheduler_for_studio_update",
        _deploy,
    )
    return calls


def _target(
    *,
    region: str = "cn-beijing",
    project: str = "default",
    application_id: str = "app-id",
) -> StudioDeploymentTarget:
    return StudioDeploymentTarget(
        application_name="studio-app",
        application_id=application_id,
        function_id=f"function-{application_id}",
        region=region,
        project=project,
        url="https://studio.example.com",
    )


def test_build_frontend_assets_runs_clean_install_and_production_build(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    frontend_root = source_root / "frontend"
    frontend_root.mkdir(parents=True)
    (source_root / "pyproject.toml").write_text("", encoding="utf-8")
    (source_root / "README.md").write_text("", encoding="utf-8")
    (source_root / "LICENSE").write_text("", encoding="utf-8")
    (frontend_root / "package.json").write_text("{}", encoding="utf-8")
    (frontend_root / "package-lock.json").write_text("{}", encoding="utf-8")
    (source_root / "veadk").mkdir()
    output_dir = tmp_path / "built"
    commands: list[list[str]] = []

    def _run(
        command: list[str], *, cwd: Path, env: dict[str, str], check: bool
    ) -> subprocess.CompletedProcess:
        commands.append(command)
        assert cwd == frontend_root
        assert json.loads(env["VITE_STUDIO_RELEASE_CHANGELOG"]) == []
        assert check is True
        if "build" in command:
            output_dir.mkdir()
            (output_dir / "index.html").write_text("built", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("veadk.cli.studio_package.shutil.which", lambda _: "/bin/npm")
    monkeypatch.setattr("veadk.cli.studio_package.subprocess.run", _run)

    build_frontend_assets(source_root, output_dir)

    assert commands == [
        ["/bin/npm", "ci"],
        ["/bin/npm", "run", "build", "--", "--outDir", str(output_dir)],
    ]


def test_stage_wheel_source_includes_studio_python_backend(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    (source_root / "veadk").mkdir(parents=True)
    (source_root / "veadk" / "__init__.py").write_text("", encoding="utf-8")
    (source_root / "frontend" / "server").mkdir(parents=True)
    (source_root / "frontend" / "__init__.py").write_text("", encoding="utf-8")
    (source_root / "frontend" / "server" / "__init__.py").write_text(
        "", encoding="utf-8"
    )
    (source_root / "frontend" / "server" / "routes.py").write_text(
        "ROUTES = []\n", encoding="utf-8"
    )
    (source_root / "frontend" / "service" / "studio_scheduler").mkdir(parents=True)
    (source_root / "frontend" / "service" / "__init__.py").write_text(
        "", encoding="utf-8"
    )
    (
        source_root / "frontend" / "service" / "studio_scheduler" / "__init__.py"
    ).write_text("", encoding="utf-8")
    (source_root / "frontend" / "service" / "studio_scheduler" / "app.py").write_text(
        "HANDLER = True\n", encoding="utf-8"
    )
    for filename in ("pyproject.toml", "README.md", "LICENSE"):
        (source_root / filename).write_text("", encoding="utf-8")
    frontend_assets = tmp_path / "assets"
    frontend_assets.mkdir()
    (frontend_assets / "index.html").write_text("built", encoding="utf-8")

    wheel_source = tmp_path / "wheel-source"
    _stage_wheel_source(source_root, frontend_assets, wheel_source)

    assert (wheel_source / "frontend" / "__init__.py").is_file()
    assert (wheel_source / "frontend" / "server" / "routes.py").read_text() == (
        "ROUTES = []\n"
    )
    assert (
        wheel_source / "frontend" / "service" / "studio_scheduler" / "app.py"
    ).read_text() == "HANDLER = True\n"


def test_find_studio_deployments_searches_regions_and_filters_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_regions: list[str] = []

    class _FakeVeFaaS:
        def __init__(self, **kwargs: str) -> None:
            self.region = kwargs["region"]
            checked_regions.append(self.region)
            self.client = SimpleNamespace(get_function=self._get_function)

        def _list_application(self, app_name: str) -> list[dict[str, object]]:
            assert app_name == "studio-app"
            return [
                {
                    "Name": "studio-app",
                    "Id": f"app-{self.region}",
                    "CloudResource": json.dumps(
                        {
                            "framework": {
                                "function": {"Id": f"fn-{self.region}"},
                                "url": {
                                    "system_url": f"https://{self.region}.example.com"
                                },
                            }
                        }
                    ),
                }
            ]

        def _get_function(self, _: object) -> SimpleNamespace:
            project = "wanted" if self.region == "cn-shanghai" else "other"
            return SimpleNamespace(project_name=project)

    monkeypatch.setattr("veadk.cli.studio_update.VeFaaS", _FakeVeFaaS)

    targets = find_studio_deployments(
        access_key="ak",
        secret_key="sk",
        application_name="studio-app",
        region=None,
        project="wanted",
    )

    assert checked_regions == ["cn-beijing", "cn-shanghai"]
    assert targets == [
        StudioDeploymentTarget(
            application_name="studio-app",
            application_id="app-cn-shanghai",
            function_id="fn-cn-shanghai",
            region="cn-shanghai",
            project="wanted",
            url="https://cn-shanghai.example.com",
        )
    ]


def test_find_studio_deployments_retries_transient_cloud_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []
    delays: list[float] = []

    class _FakeVeFaaS:
        def __init__(self, **_: str) -> None:
            self.client = SimpleNamespace(
                get_function=lambda _request: SimpleNamespace(project_name="default")
            )

        def _list_application(self, app_name: str) -> list[dict[str, object]]:
            assert app_name == "studio-app"
            attempts.append(len(attempts) + 1)
            if len(attempts) < 3:
                cause = requests.ReadTimeout("read timed out")
                raise ValueError("List application failed") from cause
            return [
                {
                    "Name": "studio-app",
                    "Id": "app-id",
                    "CloudResource": json.dumps(
                        {
                            "framework": {
                                "function": {"Id": "function-app-id"},
                                "url": {"system_url": "https://studio.example.com"},
                            }
                        }
                    ),
                }
            ]

    monkeypatch.setattr("veadk.cli.studio_update.VeFaaS", _FakeVeFaaS)

    targets = find_studio_deployments(
        access_key="ak",
        secret_key="sk",
        application_name="studio-app",
        region="ap-southeast-1",
        project="default",
        provider="byteplus",
        retry_delay_seconds=0.25,
        sleep=delays.append,
    )

    assert attempts == [1, 2, 3]
    assert delays == [0.25, 0.5]
    assert targets == [_target(region="ap-southeast-1")]


def test_find_studio_deployments_does_not_retry_non_transient_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    class _FakeVeFaaS:
        def __init__(self, **_: str) -> None:
            pass

        def _list_application(self, app_name: str) -> list[dict[str, object]]:
            nonlocal attempts
            attempts += 1
            raise ValueError(f"invalid application filter: {app_name}")

    monkeypatch.setattr("veadk.cli.studio_update.VeFaaS", _FakeVeFaaS)

    with pytest.raises(ValueError, match="invalid application filter"):
        find_studio_deployments(
            access_key="ak",
            secret_key="sk",
            application_name="studio-app",
            region="ap-southeast-1",
            project="default",
            provider="byteplus",
            sleep=lambda _: pytest.fail("non-transient failures must not sleep"),
        )

    assert attempts == 1


def test_list_applications_uses_deployment_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_regions: list[str] = []

    def _request(**kwargs: object) -> dict[str, object]:
        requested_regions.append(str(kwargs["region"]))
        return {"Result": {"Items": [], "Total": 0}}

    service = object.__new__(VeFaaS)
    service.ak = "ak"
    service.sk = "sk"
    service.region = "cn-shanghai"
    service.session_token = ""
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.ve_request", _request)

    assert service._list_application(app_name="studio-app") == []
    assert requested_regions == ["cn-shanghai"]


def test_application_template_matches_deployment_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "veadk.integrations.ve_faas.ve_faas.volcenginesdkcore.ApiClient",
        lambda _: object(),
    )
    monkeypatch.setattr(
        "veadk.integrations.ve_faas.ve_faas.volcenginesdkvefaas.VEFAASApi",
        lambda _: object(),
    )
    monkeypatch.setattr(
        "veadk.integrations.ve_faas.ve_faas.APIGateway",
        lambda *_, **__: object(),
    )

    service = VeFaaS("ak", "sk", region="cn-shanghai")

    assert service.template_id == "6a685988162bcd00083c9001"


def test_load_deployed_site_logo_uses_current_branding_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"branding": {"logoUrl": "/web/site-logo"}},
    )
    monkeypatch.setattr("veadk.cli.studio_update.httpx.get", lambda *_a, **_k: response)
    resolved_urls: list[str] = []
    expected = SiteLogo(content=_PNG, media_type="image/png", extension="png")

    def _resolve(url: str) -> SiteLogo:
        resolved_urls.append(url)
        return expected

    monkeypatch.setattr("veadk.cli.studio_update.resolve_site_logo", _resolve)

    assert load_deployed_site_logo(_target()) == expected
    assert resolved_urls == ["https://studio.example.com/web/site-logo"]


def test_load_deployed_site_logo_retries_timeout_and_suggests_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    delays: list[float] = []

    def _get(*_: object, **__: object) -> object:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("read timed out")

    monkeypatch.setattr("veadk.cli.studio_update.httpx.get", _get)

    with pytest.raises(ValueError, match=r"Retry later or pass --site-logo"):
        load_deployed_site_logo(
            _target(), retry_delay_seconds=0.25, sleep=delays.append
        )

    assert attempts == 3
    assert delays == [0.25, 0.5]


def test_studio_update_preserves_branding_and_updates_existing_ids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scheduler_deploy: list[dict[str, object]],
) -> None:
    target = _target()
    logo = SiteLogo(content=_PNG, media_type="image/png", extension="png")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "veadk.cli.studio_update.find_studio_deployments", lambda **_: [target]
    )
    monkeypatch.setattr(
        "veadk.cli.studio_update.load_deployed_site_logo", lambda _: logo
    )

    def _build_frontend(_: Path, output_dir: Path) -> None:
        output_dir.mkdir(parents=True)
        (output_dir / "index.html").write_text("built", encoding="utf-8")

    def _build_requirements(
        _: Path,
        package_dir: Path,
        *,
        frontend_assets: Path,
        provider: str,
    ) -> str:
        captured["frontend"] = (frontend_assets / "index.html").read_text()
        captured["requirements_provider"] = provider
        return "./veadk.whl\n"

    def _write_package(
        package_dir: Path,
        *,
        requirements: str,
        site_logo: SiteLogo | None,
        provider: str = "volcengine",
    ) -> None:
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "run.sh").write_text("run", encoding="utf-8")
        captured["requirements"] = requirements
        captured["logo"] = site_logo

    monkeypatch.setattr(
        "veadk.cli.studio_package.build_frontend_assets", _build_frontend
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.build_local_studio_requirements",
        _build_requirements,
    )
    monkeypatch.setattr("veadk.cli.studio_package.write_studio_package", _write_package)

    class _FakeVeFaaS:
        def __init__(self, **kwargs: str) -> None:
            captured["scope"] = kwargs

        def update_application_code_bundle(self, **kwargs: object) -> str:
            captured["update"] = kwargs
            assert (Path(str(kwargs["path"])) / "run.sh").is_file()
            return target.url

    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _FakeVeFaaS)

    result = CliRunner().invoke(
        studio,
        [
            "update",
            "--vefaas-app-name",
            "studio-app",
            "--path",
            str(tmp_path),
            "--volcengine-access-key",
            "ak",
            "--volcengine-secret-key",
            "sk",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["frontend"] == "built"
    assert captured["requirements_provider"] == "volcengine"
    assert captured["requirements"] == "./veadk.whl\n"
    assert captured["logo"] == logo
    assert captured["scope"] == {
        "access_key": "ak",
        "secret_key": "sk",
        "session_token": "",
        "region": "cn-beijing",
        "project_name": "default",
        "provider": "volcengine",
    }
    update = captured["update"]
    assert isinstance(update, dict)
    assert update["application_id"] == "app-id"
    assert update["function_id"] == "function-app-id"
    assert update["disable_gateway_cors"] is True
    assert update["environment_overrides"] == {
        "AGENTKIT_SANDBOX_REGION": "cn-beijing",
        "VEADK_STUDIO_CRONJOB_SCHEDULER_BASE": "studio-app",
        "VEADK_STUDIO_KNOWLEDGE_SIGNING_KEY": ANY,
    }
    assert len(scheduler_deploy) == 1
    scheduler_call = scheduler_deploy[0]
    assert scheduler_call["service"].__class__ is _FakeVeFaaS
    assert scheduler_call["studio_function_id"] == "function-app-id"
    assert scheduler_call["package_root"] == Path(str(update["path"]))
    assert scheduler_call["provider"] == "volcengine"
    assert scheduler_call["project"] == "default"
    assert scheduler_call["environment_overrides"] == {
        "AGENTKIT_SANDBOX_REGION": "cn-beijing",
        "VEADK_STUDIO_KNOWLEDGE_SIGNING_KEY": ANY,
    }


def test_studio_update_supports_byteplus_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scheduler_deploy: list[dict[str, object]],
) -> None:
    target = _target(region="ap-southeast-1")
    captured: dict[str, object] = {}

    def _find(**kwargs: object) -> list[StudioDeploymentTarget]:
        captured["search"] = kwargs
        return [target]

    monkeypatch.setattr("veadk.cli.studio_update.find_studio_deployments", _find)
    monkeypatch.setattr(
        "veadk.cli.studio_update.load_deployed_site_logo",
        lambda _: None,
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.build_frontend_assets",
        lambda *_: None,
    )

    def _build_requirements(
        _: Path,
        package_dir: Path,
        *,
        frontend_assets: Path,
        provider: str,
    ) -> str:
        captured["requirements_provider"] = provider
        package_dir.mkdir(parents=True, exist_ok=True)
        return "./veadk.whl\n./pydantic.whl\n"

    monkeypatch.setattr(
        "veadk.cli.studio_package.build_local_studio_requirements",
        _build_requirements,
    )

    def _write_package(
        package_dir: Path,
        *,
        requirements: str,
        site_logo: SiteLogo | None,
        provider: str,
    ) -> None:
        from veadk.cli.studio_package import studio_run_script

        captured["package_requirements"] = requirements
        captured["package_logo"] = site_logo
        captured["package_provider"] = provider
        run_script = studio_run_script(provider=provider)  # type: ignore[arg-type]
        captured["run_script"] = run_script
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "run.sh").write_text(run_script, encoding="utf-8")

    monkeypatch.setattr("veadk.cli.studio_package.write_studio_package", _write_package)

    class _FakeVeFaaS:
        def __init__(self, **kwargs: str) -> None:
            captured["scope"] = kwargs

        def update_application_code_bundle(self, **kwargs: object) -> str:
            captured["update"] = kwargs
            return target.url

    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _FakeVeFaaS)

    result = CliRunner().invoke(
        studio,
        [
            "update",
            "--provider",
            "byteplus",
            "--vefaas-app-name",
            "studio-app",
            "--path",
            str(tmp_path),
            "--byteplus-access-key",
            "bp-ak",
            "--byteplus-secret-key",
            "bp-sk",
            "--byteplus-session-token",
            "bp-token",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["requirements_provider"] == "byteplus"
    assert captured["package_provider"] == "byteplus"
    assert captured["package_requirements"] == "./veadk.whl\n./pydantic.whl\n"
    update = captured["update"]
    assert isinstance(update, dict)
    run_script = str(captured["run_script"])
    assert "--provider byteplus" in run_script
    assert "--provider volcengine" not in run_script
    assert captured["search"] == {
        "access_key": "bp-ak",
        "secret_key": "bp-sk",
        "session_token": "bp-token",
        "application_name": "studio-app",
        "region": "ap-southeast-1",
        "project": None,
        "provider": "byteplus",
    }
    assert captured["scope"] == {
        "access_key": "bp-ak",
        "secret_key": "bp-sk",
        "session_token": "bp-token",
        "region": "ap-southeast-1",
        "project_name": "default",
        "provider": "byteplus",
    }
    assert update["environment_overrides"] == {
        "AGENTKIT_SANDBOX_REGION": "ap-southeast-1",
        "CLOUD_PROVIDER": "byteplus",
        "AGENTKIT_CLOUD_PROVIDER": "byteplus",
        "BYTEPLUS_REGION": "ap-southeast-1",
        "DATABASE_VIKING_REGION": "cn-hongkong",
        "VEADK_STUDIO_CRONJOB_SCHEDULER_BASE": "studio-app",
        "VEADK_STUDIO_KNOWLEDGE_SIGNING_KEY": ANY,
    }
    assert len(scheduler_deploy) == 1


def test_studio_update_rejects_ambiguous_name_before_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "veadk.cli.studio_update.find_studio_deployments",
        lambda **_: [
            _target(),
            _target(
                region="cn-shanghai",
                project="other",
                application_id="other-app-id",
            ),
        ],
    )
    build = pytest.fail
    monkeypatch.setattr("veadk.cli.studio_package.build_frontend_assets", build)

    result = CliRunner().invoke(
        studio,
        [
            "update",
            "--vefaas-app-name",
            "studio-app",
            "--volcengine-access-key",
            "ak",
            "--volcengine-secret-key",
            "sk",
        ],
    )

    assert result.exit_code == 1
    assert "Multiple VeFaaS Applications" in result.output
    assert "cn-beijing/default" in result.output
    assert "cn-shanghai/other" in result.output


def test_studio_update_missing_target_does_not_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "veadk.cli.studio_update.find_studio_deployments", lambda **_: []
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.build_frontend_assets",
        lambda *_: pytest.fail("frontend should not be built"),
    )

    result = CliRunner().invoke(
        studio,
        [
            "update",
            "--vefaas-app-name",
            "missing-studio",
            "--volcengine-access-key",
            "ak",
            "--volcengine-secret-key",
            "sk",
        ],
    )

    assert result.exit_code == 1
    assert "was not found" in result.output


def test_studio_update_surfaces_compact_discovery_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _find(**_: object) -> list[StudioDeploymentTarget]:
        cause = requests.ReadTimeout("read timed out")
        raise ValueError("List application failed") from cause

    monkeypatch.setattr("veadk.cli.studio_update.find_studio_deployments", _find)
    monkeypatch.setattr(
        "veadk.cli.studio_package.build_frontend_assets",
        lambda *_: pytest.fail("frontend should not be built"),
    )

    result = CliRunner().invoke(
        studio,
        [
            "update",
            "--provider",
            "byteplus",
            "--vefaas-app-name",
            "studio-app",
            "--byteplus-access-key",
            "bp-ak",
            "--byteplus-secret-key",
            "bp-sk",
        ],
    )

    assert result.exit_code == 1
    assert "Could not query the existing Studio deployment after retrying" in (
        result.output
    )
    assert "Traceback" not in result.output


def test_studio_update_explicit_branding_overrides_cloud_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scheduler_deploy: list[dict[str, object]],
) -> None:
    target = _target()
    logo_path = tmp_path / "logo.png"
    logo_path.write_bytes(_PNG)
    captured: dict[str, object] = {}

    def _find(**kwargs: object) -> list[StudioDeploymentTarget]:
        captured["search"] = kwargs
        return [target]

    monkeypatch.setattr(
        "veadk.cli.studio_update.find_studio_deployments",
        _find,
    )
    monkeypatch.setattr(
        "veadk.cli.studio_update.load_deployed_site_logo",
        lambda _: pytest.fail("cloud logo should not be loaded"),
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.build_frontend_assets", lambda *_: None
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.build_local_studio_requirements",
        lambda *_a, **_k: "./veadk.whl\n",
    )

    def _write_package(
        package_dir: Path,
        *,
        requirements: str,
        site_logo: SiteLogo | None,
        provider: str = "volcengine",
    ) -> None:
        package_dir.mkdir(parents=True, exist_ok=True)
        captured["logo"] = site_logo

    monkeypatch.setattr("veadk.cli.studio_package.write_studio_package", _write_package)

    class _FakeVeFaaS:
        def __init__(self, **_: str) -> None:
            pass

        def update_application_code_bundle(self, **kwargs: object) -> str:
            captured["update"] = kwargs
            return target.url

    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _FakeVeFaaS)

    result = CliRunner().invoke(
        studio,
        [
            "update",
            "--vefaas-app-name",
            "studio-app",
            "--path",
            str(tmp_path),
            "--region",
            "cn-beijing",
            "--project",
            "default",
            "--site-logo",
            str(logo_path),
            "--site-title",
            "新标题",
            "--volcengine-access-key",
            "ak",
            "--volcengine-secret-key",
            "sk",
        ],
    )

    assert result.exit_code == 0, result.output
    logo = captured["logo"]
    assert isinstance(logo, SiteLogo)
    assert logo.content == _PNG
    search = captured["search"]
    assert isinstance(search, dict)
    assert search["region"] == "cn-beijing"
    assert search["project"] == "default"
    update = captured["update"]
    assert isinstance(update, dict)
    assert update["environment_overrides"] == {
        "AGENTKIT_SANDBOX_REGION": "cn-beijing",
        "VEADK_SITE_TITLE": "新标题",
        "VEADK_STUDIO_CRONJOB_SCHEDULER_BASE": "studio-app",
        "VEADK_STUDIO_KNOWLEDGE_SIGNING_KEY": ANY,
    }
    assert len(scheduler_deploy) == 1


def test_studio_update_only_overrides_explicit_sandbox_tool_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scheduler_deploy: list[dict[str, object]],
) -> None:
    target = _target()
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "veadk.cli.studio_update.find_studio_deployments", lambda **_: [target]
    )
    monkeypatch.setattr(
        "veadk.cli.studio_update.load_deployed_site_logo", lambda _: None
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.build_frontend_assets", lambda *_: None
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.build_local_studio_requirements",
        lambda *_a, **_k: "./veadk.whl\n",
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.write_studio_package", lambda *_a, **_k: None
    )

    class _FakeVeFaaS:
        def __init__(self, **_: str) -> None:
            pass

        def update_application_code_bundle(self, **kwargs: object) -> str:
            captured.update(kwargs)
            return target.url

    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _FakeVeFaaS)

    result = CliRunner().invoke(
        studio,
        [
            "update",
            "--vefaas-app-name",
            "studio-app",
            "--path",
            str(tmp_path),
            "--sandbox-chat-codex-tool-id",
            "chat-tool-new",
            "--sandbox-dev-tool-id",
            "dev-tool-new",
            "--sandbox-chat-codex-snapshot-tool-id",
            "chat-snapshot-tool-new",
            "--sandbox-chat-openclaw-snapshot-tool-id",
            "openclaw-snapshot-tool-new",
            "--sandbox-chat-hermes-snapshot-tool-id",
            "hermes-snapshot-tool-new",
            "--volcengine-access-key",
            "ak",
            "--volcengine-secret-key",
            "sk",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["environment_overrides"] == {
        "AGENTKIT_SANDBOX_REGION": "cn-beijing",
        "SANDBOX_CHAT_CODEX": "chat-tool-new",
        "SANDBOX_CHAT_CODEX_SNAPSHOT": "chat-snapshot-tool-new",
        "SANDBOX_CHAT_OPENCLAW_SNAPSHOT": "openclaw-snapshot-tool-new",
        "SANDBOX_CHAT_HERMES_SNAPSHOT": "hermes-snapshot-tool-new",
        "SANDBOX_DEV": "dev-tool-new",
        "VEADK_STUDIO_CRONJOB_SCHEDULER_BASE": "studio-app",
        "VEADK_STUDIO_KNOWLEDGE_SIGNING_KEY": ANY,
    }
    assert len(scheduler_deploy) == 1


def test_volcengine_studio_update_repairs_missing_snapshot_tools_and_oauth_callback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scheduler_deploy: list[dict[str, object]],
) -> None:
    target = _target()
    captured: dict[str, object] = {}
    code_tools: list[dict[str, object]] = []
    agent_tools: list[dict[str, object]] = []
    code_credentials: list[dict[str, object]] = []
    agent_credentials: list[dict[str, object]] = []
    role_policy_syncs: list[dict[str, object]] = []
    identity_clients: list[dict[str, object]] = []
    identity_callbacks: list[dict[str, object]] = []
    stagger_delays: list[float] = []
    monkeypatch.setattr(
        "veadk.cli.studio_update.find_studio_deployments", lambda **_: [target]
    )
    monkeypatch.setattr(
        "veadk.cli.studio_update.load_deployed_site_logo", lambda _: None
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.build_frontend_assets", lambda *_: None
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.build_local_studio_requirements",
        lambda *_a, **_k: "./veadk.whl\n",
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.write_studio_package", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._new_studio_deploy_id",
        lambda: "stddep_update",
    )
    monkeypatch.setattr("veadk.cli.cli_frontend.sleep", stagger_delays.append)
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_code_env_tool",
        lambda **kwargs: code_tools.append(kwargs) or "codex-snapshot-tool",
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_agent_tool",
        lambda **kwargs: (
            agent_tools.append(kwargs) or f"{kwargs['kind']}-snapshot-tool"
        ),
    )
    monkeypatch.setattr(
        "veadk.cli.frontend_skill_creator.ensure_skill_creator_model_credential",
        lambda **kwargs: code_credentials.append(kwargs),
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_agent_model_credential",
        lambda **kwargs: agent_credentials.append(kwargs),
    )
    monkeypatch.setattr(
        "veadk.cli.frontend_deploy_iam.ensure_default_frontend_role_policy",
        lambda role, **kwargs: (
            role_policy_syncs.append({"role": role, **kwargs}) or True
        ),
    )

    class _FakeIdentityClient:
        def __init__(self, **kwargs: object) -> None:
            identity_clients.append(kwargs)

        def register_callback_for_user_pool_client(self, **kwargs: object) -> None:
            identity_callbacks.append(kwargs)

    monkeypatch.setattr(
        "veadk.integrations.ve_identity.identity_client.IdentityClient",
        _FakeIdentityClient,
    )

    class _FakeVeFaaS:
        def __init__(self, **_: str) -> None:
            self.client = SimpleNamespace(
                get_function=lambda _request: SimpleNamespace(
                    role="trn:iam::123:role/VeADKFrontendServiceRole",
                    envs=[
                        SimpleNamespace(
                            key="OAUTH2_USER_POOL_ID",
                            value="legacy-user-pool",
                        ),
                        SimpleNamespace(
                            key="OAUTH2_USER_POOL_CLIENT_ID",
                            value="legacy-user-pool-client",
                        ),
                        SimpleNamespace(
                            key="VEIDENTITY_REGION",
                            value="cn-shanghai",
                        ),
                    ],
                )
            )

        def update_application_code_bundle(self, **kwargs: object) -> str:
            captured.update(kwargs)
            return target.url

    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _FakeVeFaaS)

    result = CliRunner().invoke(
        studio,
        [
            "update",
            "--vefaas-app-name",
            "studio-app",
            "--path",
            str(tmp_path),
            "--volcengine-access-key",
            "ak",
            "--volcengine-secret-key",
            "sk",
        ],
    )

    assert result.exit_code == 0, result.output
    assert role_policy_syncs == [
        {
            "role": "trn:iam::123:role/VeADKFrontendServiceRole",
            "access_key": "ak",
            "secret_key": "sk",
            "session_token": "",
            "provider": "volcengine",
        }
    ]
    assert identity_clients == [
        {
            "access_key": "ak",
            "secret_key": "sk",
            "session_token": "",
            "region": "cn-shanghai",
            "provider": "volcengine",
        }
    ]
    assert identity_callbacks == [
        {
            "user_pool_uid": "legacy-user-pool",
            "client_uid": "legacy-user-pool-client",
            "callback_url": "https://studio.example.com/oauth2/callback",
            "web_origin": "https://studio.example.com",
            "dismiss_login_page_enabled": False,
            "skip_consent_enabled": True,
        }
    ]
    assert len(code_tools) == 1
    assert code_tools[0]["enable_snapshot"] is True
    assert code_tools[0]["create_min_interval"] == 0.5
    assert str(code_tools[0]["name"]).endswith("_snapshot")
    assert {str(call["kind"]) for call in agent_tools} == {"openclaw", "hermes"}
    assert {bool(call["enable_snapshot"]) for call in agent_tools} == {True}
    assert {float(call["create_min_interval"]) for call in agent_tools} == {0.5}
    assert stagger_delays == [0.5, 0.5]
    assert {str(call["provider"]) for call in code_credentials} == {"volcengine"}
    assert {str(call["provider"]) for call in agent_credentials} == {"volcengine"}
    overrides = captured["environment_overrides"]
    assert overrides == {
        "AGENTKIT_SANDBOX_REGION": "cn-beijing",
        "VEADK_STUDIO_DEPLOY_ID": "stddep_update",
        "VEADK_STUDIO_USER_POOL_ID": "legacy-user-pool",
        "VEADK_STUDIO_APPLICATION_ID": "app-id",
        "VEADK_STUDIO_FUNCTION_ID": "function-app-id",
        "VEADK_STUDIO_DEPLOY_REGION": "cn-beijing",
        "VEADK_STUDIO_PROJECT": "default",
        "VEADK_STUDIO_ACCOUNT_ID": "123",
        "VEADK_STUDIO_ACCOUNT_ID_RESOLUTION_ERROR": "",
        "OAUTH2_REDIRECT_URI": "https://studio.example.com/oauth2/callback",
        "SANDBOX_CHAT_CODEX_SNAPSHOT": "codex-snapshot-tool",
        "SANDBOX_CHAT_OPENCLAW_SNAPSHOT": "openclaw-snapshot-tool",
        "SANDBOX_CHAT_HERMES_SNAPSHOT": "hermes-snapshot-tool",
        "VEADK_STUDIO_CRONJOB_SCHEDULER_BASE": "studio-app",
        "VEADK_STUDIO_KNOWLEDGE_SIGNING_KEY": ANY,
    }
    assert len(scheduler_deploy) == 1


@pytest.mark.parametrize("dev_tool_id", [None, "replacement-dev-tool"])
def test_byteplus_studio_update_repairs_missing_sandbox_tools(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    dev_tool_id: str | None,
    scheduler_deploy: list[dict[str, object]],
) -> None:
    target = _target(region="ap-southeast-1")
    captured: dict[str, object] = {}
    code_tools: list[dict[str, object]] = []
    dev_tools: list[dict[str, object]] = []
    agent_tools: list[dict[str, object]] = []
    code_credentials: list[dict[str, object]] = []
    agent_credentials: list[dict[str, object]] = []
    role_policy_syncs: list[dict[str, object]] = []
    monkeypatch.setattr(
        "veadk.cli.studio_update.find_studio_deployments", lambda **_: [target]
    )
    monkeypatch.setattr(
        "veadk.cli.studio_update.load_deployed_site_logo", lambda _: None
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.build_frontend_assets", lambda *_: None
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.build_local_studio_requirements",
        lambda *_a, **_k: "./veadk.whl\n",
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.write_studio_package", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_code_env_tool",
        lambda **kwargs: code_tools.append(kwargs) or f"{kwargs['name']}-tool",
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_agent_tool",
        lambda **kwargs: (
            agent_tools.append(kwargs)
            or (
                f"{kwargs['kind']}-snapshot-tool"
                if kwargs["enable_snapshot"]
                else f"{kwargs['kind']}-tool"
            )
        ),
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_dev_env_tool",
        lambda **kwargs: dev_tools.append(kwargs) or f"{kwargs['name']}-tool",
    )
    monkeypatch.setattr(
        "veadk.cli.frontend_skill_creator.ensure_skill_creator_model_credential",
        lambda **kwargs: code_credentials.append(kwargs),
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_agent_model_credential",
        lambda **kwargs: agent_credentials.append(kwargs),
    )
    monkeypatch.setattr(
        "veadk.cli.frontend_deploy_iam.ensure_default_frontend_role_policy",
        lambda role, **kwargs: (
            role_policy_syncs.append({"role": role, **kwargs}) or True
        ),
    )

    class _FakeVeFaaS:
        def __init__(self, **_: str) -> None:
            self.client = SimpleNamespace(
                get_function=lambda _request: SimpleNamespace(
                    role="trn:iam::3001037806:role/VeADKFrontendServiceRole",
                    envs=[
                        SimpleNamespace(
                            key="SANDBOX_CHAT_CODEX",
                            value="existing-codex-tool",
                        )
                    ],
                )
            )

        def update_application_code_bundle(self, **kwargs: object) -> str:
            captured.update(kwargs)
            return target.url

    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _FakeVeFaaS)

    args = [
        "update",
        "--provider",
        "byteplus",
        "--vefaas-app-name",
        "studio-app",
        "--path",
        str(tmp_path),
        "--byteplus-access-key",
        "ak",
        "--byteplus-secret-key",
        "sk",
    ]
    if dev_tool_id is not None:
        args.extend(["--sandbox-dev-tool-id", dev_tool_id])
    result = CliRunner().invoke(studio, args)

    assert result.exit_code == 0, result.output
    assert role_policy_syncs == [
        {
            "role": "trn:iam::3001037806:role/VeADKFrontendServiceRole",
            "access_key": "ak",
            "secret_key": "sk",
            "session_token": "",
            "provider": "byteplus",
        }
    ]
    assert len(code_tools) == 1
    assert code_tools[0]["enable_snapshot"] is True
    assert "-codex-" in str(code_tools[0]["name"])
    assert len(code_tools[0]["legacy_names"]) == 1
    assert "-chat-" in str(code_tools[0]["legacy_names"][0])
    assert str(code_tools[0]["name"]).endswith("_snapshot")
    if dev_tool_id is None:
        assert len(dev_tools) == 1
        expected_dev_tool_id = f"{dev_tools[0]['name']}-tool"
    else:
        assert dev_tools == []
        expected_dev_tool_id = dev_tool_id
    assert {str(call["kind"]) for call in agent_tools} == {"openclaw", "hermes"}
    assert {bool(call["enable_snapshot"]) for call in agent_tools} == {False, True}
    assert {str(call["provider"]) for call in code_credentials} == {"byteplus"}
    assert {str(call["provider"]) for call in agent_credentials} == {"byteplus"}
    assert {str(call["model_base_url"]) for call in agent_credentials} == {
        "https://ark.ap-southeast.bytepluses.com/api/v3"
    }
    overrides = captured["environment_overrides"]
    assert isinstance(overrides, dict)
    assert overrides["SANDBOX_CHAT_CODEX"] == "existing-codex-tool"
    assert overrides["SANDBOX_CHAT_CODEX_SNAPSHOT"] == (f"{code_tools[0]['name']}-tool")
    assert "SANDBOX_SKILL_CREATOR" not in overrides
    assert overrides["SANDBOX_CHAT_OPENCLAW"] == "openclaw-tool"
    assert overrides["SANDBOX_CHAT_HERMES"] == "hermes-tool"
    assert overrides["SANDBOX_CHAT_OPENCLAW_SNAPSHOT"] == "openclaw-snapshot-tool"
    assert overrides["SANDBOX_CHAT_HERMES_SNAPSHOT"] == "hermes-snapshot-tool"
    assert overrides["SANDBOX_DEV"] == expected_dev_tool_id
    assert overrides["CLOUD_PROVIDER"] == "byteplus"
    assert overrides["VEADK_STUDIO_ACCOUNT_ID"] == "3001037806"
    assert overrides["VEADK_STUDIO_CRONJOB_SCHEDULER_BASE"] == "studio-app"
    assert len(scheduler_deploy) == 1


def test_update_application_code_bundle_merges_only_explicit_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updated_requests: list[Any] = []
    service = object.__new__(VeFaaS)
    service.session_token = ""
    cast(Any, service).client = SimpleNamespace(
        get_function=lambda _: SimpleNamespace(
            envs=[
                SimpleNamespace(key="EXISTING", value="kept"),
                SimpleNamespace(key="VEADK_SITE_TITLE", value="old"),
            ]
        ),
        update_function=updated_requests.append,
    )
    monkeypatch.setattr(service, "_upload_and_mount_code", lambda *_: None)
    monkeypatch.setattr(service, "_release_application", lambda _: "https://same")
    ensure_route = Mock()
    monkeypatch.setattr(service, "ensure_application_route_methods", ensure_route)

    url = service.update_application_code_bundle(
        application_id="app-id",
        function_id="function-id",
        path=str(tmp_path),
        environment_overrides={"VEADK_SITE_TITLE": "新标题"},
        disable_gateway_cors=True,
    )

    assert url == "https://same"
    request = updated_requests[0]
    assert request.id == "function-id"
    assert {item.key: item.value for item in request.envs} == {
        "EXISTING": "kept",
        "VEADK_SITE_TITLE": "新标题",
    }
    ensure_route.assert_called_once_with("app-id", disable_cors=True)


def test_application_operations_use_deployment_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    service = object.__new__(VeFaaS)
    service.session_token = ""
    cast(Any, service).ak = "ak"
    cast(Any, service).sk = "sk"
    cast(Any, service).region = "cn-shanghai"
    cast(Any, service).template_id = "template-id"

    def _ve_request(**kwargs: object) -> dict[str, object]:
        action = cast(str, kwargs["action"])
        region = cast(str, kwargs["region"])
        calls.append((action, region))
        if action == "CreateApplication":
            request_body = cast(dict[str, Any], kwargs["request_body"])
            config = cast(dict[str, Any], request_body["Config"])
            assert config["Region"] == "cn-shanghai"
            return {"Result": {"Status": "create_success", "Id": "application-id"}}
        if action == "GetApplication":
            return {"Result": {"Status": "create_success"}}
        if action == "ListApplications":
            return {"Result": {"Items": [], "Total": 0}}
        if action == "GetApplicationRevisionLog":
            return {"Result": {"LogLines": []}}
        return {}

    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.ve_request", _ve_request)

    application_id = service._create_application(
        "studio-app",
        "studio-function",
        "gateway",
        "upstream",
        "service",
    )
    service._start_application_release(application_id)
    status, _ = service._get_application_status("application-id")
    applications = service._list_application(app_name="studio-app")
    service.delete("application-id")
    logs = service._get_application_logs("application-id", revision_number=1)

    assert application_id == "application-id"
    assert status == "create_success"
    assert applications == []
    assert logs == []
    assert calls == [
        ("CreateApplication", "cn-shanghai"),
        ("ReleaseApplication", "cn-shanghai"),
        ("GetApplication", "cn-shanghai"),
        ("ListApplications", "cn-shanghai"),
        ("DeleteApplication", "cn-shanghai"),
        ("GetApplicationRevisionLog", "cn-shanghai"),
    ]


def test_application_status_retries_transient_network_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    delays: list[float] = []
    service = object.__new__(VeFaaS)
    service.session_token = ""
    cast(Any, service).ak = "ak"
    cast(Any, service).sk = "sk"
    cast(Any, service).region = "ap-southeast-1"
    cast(Any, service).provider = "byteplus"

    def _ve_request(**_: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise requests.ReadTimeout("TLS handshake operation timed out")
        return {"Result": {"Status": "deploy_success"}}

    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.ve_request", _ve_request)

    status, _ = service._get_application_status(
        "application-id", retry_delay_seconds=0.25, sleep=delays.append
    )

    assert status == "deploy_success"
    assert calls == 3
    assert delays == [0.25, 0.5]


def test_application_status_does_not_retry_non_transient_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    service = object.__new__(VeFaaS)
    service.session_token = ""
    cast(Any, service).ak = "ak"
    cast(Any, service).sk = "sk"
    cast(Any, service).region = "cn-beijing"
    cast(Any, service).provider = "volcengine"

    def _ve_request(**_: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise ValueError("permission denied")

    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.ve_request", _ve_request)

    with pytest.raises(ValueError, match="permission denied"):
        service._get_application_status("application-id", sleep=lambda _: None)

    assert calls == 1


def test_retry_transient_cloud_operation_retries_idempotent_call() -> None:
    calls = 0
    delays: list[float] = []

    def _operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise requests.ReadTimeout("read timed out")
        return "ready"

    assert (
        retry_transient_cloud_operation(
            _operation,
            retry_delay_seconds=0.25,
            sleep=delays.append,
        )
        == "ready"
    )
    assert calls == 3
    assert delays == [0.25, 0.5]


def test_retry_transient_cloud_operation_does_not_retry_permanent_error() -> None:
    calls = 0

    def _operation() -> None:
        nonlocal calls
        calls += 1
        raise ValueError("permission denied")

    with pytest.raises(ValueError, match="permission denied"):
        retry_transient_cloud_operation(_operation, sleep=lambda _: None)

    assert calls == 1


def test_application_logs_use_latest_revision_and_bounded_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []
    service = object.__new__(VeFaaS)
    service.session_token = ""
    cast(Any, service).ak = "ak"
    cast(Any, service).sk = "sk"
    cast(Any, service).region = "cn-beijing"
    monkeypatch.setattr(
        service,
        "_get_application_status",
        lambda _app_id: (
            "deploying",
            {"Result": {"NewRevisionNumber": 8, "StableRevisionNumber": 7}},
        ),
    )

    def _ve_request(**kwargs: Any) -> dict[str, Any]:
        requests.append(kwargs)
        return {"Result": {"LogLines": ["building", "published"]}}

    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.ve_request", _ve_request)

    logs = service._get_application_logs("application-id", limit=99_999)

    assert logs == ["building", "published"]
    assert requests[0]["request_body"] == {
        "Id": "application-id",
        "Limit": 50_000,
        "RevisionNumber": 8,
    }


def test_application_logs_retry_with_tail_window_when_response_is_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []
    service = object.__new__(VeFaaS)
    service.session_token = ""
    cast(Any, service).ak = "ak"
    cast(Any, service).sk = "sk"
    cast(Any, service).region = "cn-beijing"

    def _ve_request(**kwargs: Any) -> dict[str, Any]:
        request_body = kwargs["request_body"]
        requests.append(request_body)
        if "Offset" not in request_body:
            return {
                "Result": {
                    "LogLines": ["logs truncated"],
                    "NextOffset": 70_000,
                }
            }
        return {
            "Result": {
                "LogLines": ["partial first line", "tail one", "tail two"],
                "NextOffset": 70_000,
            }
        }

    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.ve_request", _ve_request)

    logs = service._get_application_logs(
        "application-id",
        revision_number=9,
    )

    assert logs == ["tail one", "tail two"]
    assert requests == [
        {"Id": "application-id", "Limit": 50_000, "RevisionNumber": 9},
        {
            "Id": "application-id",
            "Limit": 50_000,
            "RevisionNumber": 9,
            "Offset": 20_000,
        },
    ]


def test_release_failure_includes_status_when_logs_are_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = object.__new__(VeFaaS)
    monkeypatch.setattr(
        service,
        "_start_application_release",
        lambda _app_id: {"Result": {"RevisionNumber": 9}},
    )
    monkeypatch.setattr(
        service,
        "_get_application_status",
        lambda _app_id: (
            "deploy_fail",
            {
                "Result": {
                    "Status": "deploy_fail",
                    "NewRevisionNumber": 9,
                    "Message": "runtime start failed",
                    "ApiKey": "sensitive-token-value",
                }
            },
        ),
    )
    monkeypatch.setattr(service, "_get_application_logs", lambda **_kwargs: [])

    with pytest.raises(Exception) as exc:
        service._release_application("application-id")

    message = str(exc.value)
    assert "No application revision logs were returned" in message
    assert "Application status response" in message
    assert "runtime start failed" in message
    assert "sensitive-token-value" not in message
    assert "******" in message


def test_update_application_code_bundle_preserves_unspecified_sandbox_tool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updated_requests: list[Any] = []
    service = object.__new__(VeFaaS)
    service.session_token = ""
    cast(Any, service).client = SimpleNamespace(
        get_function=lambda _: SimpleNamespace(
            envs=[
                SimpleNamespace(key="SANDBOX_CHAT_CODEX", value="chat-old"),
                SimpleNamespace(key="SANDBOX_CHAT_HERMES", value="hermes-old"),
            ]
        ),
        update_function=updated_requests.append,
    )
    monkeypatch.setattr(service, "_upload_and_mount_code", lambda *_: None)
    monkeypatch.setattr(service, "_release_application", lambda _: "https://same")

    service.update_application_code_bundle(
        application_id="app-id",
        function_id="function-id",
        path=str(tmp_path),
        environment_overrides={"SANDBOX_CHAT_CODEX": "chat-new"},
    )

    request = updated_requests[0]
    assert {item.key: item.value for item in request.envs} == {
        "SANDBOX_CHAT_CODEX": "chat-new",
        "SANDBOX_CHAT_HERMES": "hermes-old",
    }


def test_update_application_code_bundle_does_not_read_or_replace_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updated_requests: list[Any] = []
    service = object.__new__(VeFaaS)
    service.session_token = ""
    cast(Any, service).client = SimpleNamespace(
        get_function=lambda _: pytest.fail("environment should not be read"),
        update_function=updated_requests.append,
    )
    monkeypatch.setattr(service, "_upload_and_mount_code", lambda *_: None)
    monkeypatch.setattr(service, "_release_application", lambda _: "https://same")

    service.update_application_code_bundle(
        application_id="app-id",
        function_id="function-id",
        path=str(tmp_path),
    )

    request = updated_requests[0]
    assert request.id == "function-id"
    assert request.envs is None
    assert request.request_timeout is None
