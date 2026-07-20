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

"""Tests for Studio title and logo validation."""

import base64
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest
from click.testing import CliRunner

from veadk.cli.frontend_branding import (
    DEFAULT_SITE_TITLE,
    normalize_site_title,
    resolve_site_logo,
)
from veadk.cli.cli_frontend import studio

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)


class _LogoResponse:
    def raise_for_status(self) -> None:
        pass

    def iter_bytes(self) -> Iterator[bytes]:
        yield _PNG


class _LogoStream:
    def __enter__(self) -> _LogoResponse:
        return _LogoResponse()

    def __exit__(self, *args: object) -> None:
        pass


def test_normalize_site_title_uses_default_and_accepts_six_characters() -> None:
    assert normalize_site_title(None) == DEFAULT_SITE_TITLE
    assert normalize_site_title(" 火山助手 ") == "火山助手"
    assert normalize_site_title("ABC123") == "ABC123"


@pytest.mark.parametrize("title", ["", "       ", "ABCDEFG", "火山智能助手平台"])
def test_normalize_site_title_rejects_invalid_values(title: str) -> None:
    with pytest.raises(ValueError):
        normalize_site_title(title)


def test_studio_cli_rejects_overlong_site_title() -> None:
    result = CliRunner().invoke(studio, ["--site-title", "ABCDEFG"])

    assert result.exit_code == 1
    assert "at most 6 characters" in result.output


def test_resolve_site_logo_reads_and_validates_local_image(tmp_path: Path) -> None:
    logo_path = tmp_path / "logo.png"
    logo_path.write_bytes(_PNG)

    logo = resolve_site_logo(str(logo_path))

    assert logo is not None
    assert logo.content == _PNG
    assert logo.media_type == "image/png"
    assert logo.extension == "png"


def test_resolve_site_logo_rejects_non_image(tmp_path: Path) -> None:
    logo_path = tmp_path / "logo.txt"
    logo_path.write_text("not an image", encoding="utf-8")

    with pytest.raises(ValueError, match="must be PNG"):
        resolve_site_logo(str(logo_path))


def test_resolve_site_logo_downloads_network_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("httpx.stream", lambda *args, **kwargs: _LogoStream())

    logo = resolve_site_logo("https://example.com/logo.png")

    assert logo is not None
    assert logo.content == _PNG
    assert logo.media_type == "image/png"


@pytest.mark.parametrize(
    ("title_args", "expected_site_title"),
    [([], None), (["--site-title", "火山助手"], "火山助手")],
)
def test_studio_deploy_bundles_logo_and_optional_title(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    title_args: list[str],
    expected_site_title: str | None,
) -> None:
    logo_path = tmp_path / "logo.png"
    logo_path.write_bytes(_PNG)
    captured: dict[str, object] = {}
    environments: dict[str, str] = {}

    class _FakeCloudAgentEngine:
        def __init__(self, **kwargs: object) -> None:
            pass

        def deploy(self, **kwargs: object) -> SimpleNamespace:
            deploy_root = Path(str(kwargs["path"]))
            packaged_logo = deploy_root / "site-logo.png"
            captured["logo"] = packaged_logo.read_bytes()
            captured["run_script"] = (deploy_root / "run.sh").read_text(
                encoding="utf-8"
            )
            return SimpleNamespace(
                vefaas_endpoint="",
                vefaas_application_id="app-id",
                vefaas_function_id="",
            )

    monkeypatch.setattr("veadk.config.veadk_environments", environments)
    monkeypatch.setattr(
        "veadk.cloud.cloud_agent_engine.CloudAgentEngine", _FakeCloudAgentEngine
    )
    monkeypatch.setattr(
        "veadk.cli.studio_deploy_serverless_iam.ensure_serverless_application_role",
        lambda *_: False,
    )

    args = [
        "deploy",
        "--user-pool-id",
        "pool-id",
        "--allowed-client-id",
        "client-id",
        "--vefaas-app-name",
        "branded-studio",
        "--iam-role",
        "trn:iam::role/test",
        "--gateway-name",
        "gateway",
        "--volcengine-access-key",
        "ak",
        "--volcengine-secret-key",
        "sk",
        "--site-logo",
        str(logo_path),
    ]
    result = CliRunner().invoke(studio, args + title_args)

    assert result.exit_code == 0, result.output
    assert captured["logo"] == _PNG
    assert '--site-logo "$ROOT_DIR/site-logo.png"' in str(captured["run_script"])
    if expected_site_title is None:
        assert "VEADK_SITE_TITLE" not in environments
    else:
        assert environments["VEADK_SITE_TITLE"] == expected_site_title
