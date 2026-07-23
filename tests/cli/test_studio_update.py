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

import pytest

from click.testing import CliRunner

from veadk.cli.cli_frontend import studio
from veadk.cli.frontend_branding import SiteLogo
from veadk.cli.studio_update import (
    StudioDeploymentTarget,
    find_studio_deployments,
    load_deployed_site_logo,
)
from veadk.cli.studio_package import build_frontend_assets
from veadk.integrations.ve_faas.ve_faas import VeFaaS

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


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
        command: list[str], *, cwd: Path, check: bool
    ) -> subprocess.CompletedProcess:
        commands.append(command)
        assert cwd == frontend_root
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


def test_list_applications_uses_application_control_plane_region(
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
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.ve_request", _request)

    assert service._list_application(app_name="studio-app") == []
    assert requested_regions == ["cn-beijing"]


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


def test_studio_update_preserves_branding_and_updates_existing_ids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
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
        _: Path, package_dir: Path, *, frontend_assets: Path
    ) -> str:
        captured["frontend"] = (frontend_assets / "index.html").read_text()
        return "./veadk.whl\n"

    def _write_package(
        package_dir: Path, *, requirements: str, site_logo: SiteLogo | None
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
    assert captured["requirements"] == "./veadk.whl\n"
    assert captured["logo"] == logo
    assert captured["scope"] == {
        "access_key": "ak",
        "secret_key": "sk",
        "region": "cn-beijing",
        "project_name": "default",
    }
    update = captured["update"]
    assert isinstance(update, dict)
    assert update["application_id"] == "app-id"
    assert update["function_id"] == "function-app-id"
    assert update["environment_overrides"] == {"AGENTKIT_SANDBOX_REGION": "cn-beijing"}


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


def test_studio_update_explicit_branding_overrides_cloud_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
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
        package_dir: Path, *, requirements: str, site_logo: SiteLogo | None
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
    }


def test_studio_update_only_overrides_explicit_sandbox_tool_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
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
    }


def test_update_application_code_bundle_merges_only_explicit_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updated_requests: list[Any] = []
    service = object.__new__(VeFaaS)
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

    url = service.update_application_code_bundle(
        application_id="app-id",
        function_id="function-id",
        path=str(tmp_path),
        environment_overrides={"VEADK_SITE_TITLE": "新标题"},
    )

    assert url == "https://same"
    request = updated_requests[0]
    assert request.id == "function-id"
    assert {item.key: item.value for item in request.envs} == {
        "EXISTING": "kept",
        "VEADK_SITE_TITLE": "新标题",
    }


def test_application_control_plane_uses_beijing_for_shanghai_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    service = object.__new__(VeFaaS)
    cast(Any, service).ak = "ak"
    cast(Any, service).sk = "sk"
    cast(Any, service).region = "cn-shanghai"

    def _ve_request(**kwargs: object) -> dict[str, object]:
        action = cast(str, kwargs["action"])
        region = cast(str, kwargs["region"])
        calls.append((action, region))
        if action == "GetApplication":
            return {"Result": {"Status": "create_success"}}
        return {"Result": {"Items": [], "Total": 0}}

    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.ve_request", _ve_request)

    status, _ = service._get_application_status("application-id")
    applications = service._list_application(app_name="studio-app")

    assert status == "create_success"
    assert applications == []
    assert calls == [
        ("GetApplication", "cn-beijing"),
        ("ListApplications", "cn-beijing"),
    ]


def test_update_application_code_bundle_preserves_unspecified_sandbox_tool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updated_requests: list[Any] = []
    service = object.__new__(VeFaaS)
    cast(Any, service).client = SimpleNamespace(
        get_function=lambda _: SimpleNamespace(
            envs=[
                SimpleNamespace(key="SANDBOX_CHAT_CODEX", value="chat-old"),
                SimpleNamespace(key="SANDBOX_SKILL_CREATOR", value="skill-old"),
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
        "SANDBOX_SKILL_CREATOR": "skill-old",
    }


def test_update_application_code_bundle_does_not_read_or_replace_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updated_requests: list[Any] = []
    service = object.__new__(VeFaaS)
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
