"""Managed configuration fails before any cloud or database write."""

import pytest
import yaml

from veadk.integrations.mpa.managed.config import load_profile, ConfigurationError


def profile_file(tmp_path, monkeypatch, **managed):
    monkeypatch.setenv("TEST_MPA_ADMIN", "postgresql://admin:fake@db/registry")
    monkeypatch.setenv("TEST_MPA_REGISTRY", "postgresql://user:fake@db/registry")
    data = {
        "region": "cn-beijing",
        "managed": {
            "version": 1,
            "database-admin-url-env": "TEST_MPA_ADMIN",
            "shared-database-url-env": "TEST_MPA_REGISTRY",
            "from-runtime": "r-source",
            "worker": {"existing-id": "t-worker"},
            **managed,
        },
    }
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_summary_contains_no_secrets(tmp_path, monkeypatch):
    profile = load_profile(profile_file(tmp_path, monkeypatch))
    assert profile.region == "cn-beijing"
    assert "fake" not in str(profile.summary())
    assert "postgresql" not in str(profile.summary())


def test_invalid_profile_and_missing_secret_are_safe(tmp_path, monkeypatch):
    path = profile_file(tmp_path, monkeypatch, **{"provider-root": "/not-supported"})
    with pytest.raises(ConfigurationError):
        load_profile(path)
    path = profile_file(tmp_path, monkeypatch)
    monkeypatch.delenv("TEST_MPA_ADMIN")
    with pytest.raises(ConfigurationError, match="TEST_MPA_ADMIN"):
        load_profile(path)


def test_profile_rejects_region_change_and_ambiguous_source(tmp_path, monkeypatch):
    path = profile_file(tmp_path, monkeypatch)
    with pytest.raises(ConfigurationError, match="region"):
        load_profile(path, region="cn-shanghai")
    path = profile_file(tmp_path, monkeypatch, **{"template-file": "private.json"})
    with pytest.raises(ConfigurationError):
        load_profile(path)


def test_invalid_yaml_does_not_echo_secret(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_text("password: [never-echo-this")
    with pytest.raises(ConfigurationError) as error:
        load_profile(path)
    assert "never-echo-this" not in str(error.value)


def test_adoption_requires_explicit_network_before_mutations(tmp_path, monkeypatch):
    path = profile_file(tmp_path, monkeypatch, apig={"adopt-id": "g-existing"})
    with pytest.raises(ConfigurationError, match="VPC"):
        load_profile(path)


def test_cli_managed_dry_run_never_calls_cloud(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from veadk.cli.cli_mpa import mpa
    from veadk.integrations.mpa.managed import service

    monkeypatch.setattr(
        service, "RuntimeCloud", lambda **kw: pytest.fail("dry-run called cloud")
    )
    path = profile_file(tmp_path, monkeypatch)
    result = CliRunner().invoke(
        mpa, ["provision", "--config", str(path), "--agent-id", "my-agent", "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert '"dryRun": true' in result.output
    assert "fake" not in result.output


def test_missing_profile_reports_server_setting_without_disclosing_path(tmp_path):
    with pytest.raises(ConfigurationError) as error:
        load_profile(tmp_path / "private-deployment.yaml")
    message = str(error.value)
    assert "configuration file was not found" in message
    assert "VEADK_MPA_CREATE_CONFIG" in message
    assert str(tmp_path) not in message


def test_invalid_yaml_identifies_syntax_without_echoing_input(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_text("password: [never-echo-this")
    with pytest.raises(ConfigurationError) as error:
        load_profile(path)
    assert "Invalid YAML" in str(error.value)
    assert "never-echo-this" not in str(error.value)


def test_missing_template_is_distinct_from_missing_profile(tmp_path, monkeypatch):
    path = profile_file(
        tmp_path, monkeypatch, **{"from-runtime": "", "template-file": "missing.json"}
    )
    with pytest.raises(ConfigurationError, match="Runtime template file was not found"):
        load_profile(path)


def test_unreadable_profile_has_actionable_safe_error(tmp_path, monkeypatch):
    from pathlib import Path

    path = tmp_path / "private.yaml"
    path.write_text("managed: {}")

    def denied(*args, **kwargs):
        raise PermissionError("private-path-and-details")

    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(ConfigurationError) as error:
        load_profile(path)
    assert "permission" in str(error.value).lower()
    assert "private-path-and-details" not in str(error.value)


def test_invalid_template_json_does_not_echo_input(tmp_path, monkeypatch):
    (tmp_path / "template.json").write_text('{"password": "never-echo-this"')
    path = profile_file(
        tmp_path, monkeypatch, **{"from-runtime": "", "template-file": "template.json"}
    )
    with pytest.raises(ConfigurationError) as error:
        load_profile(path)
    assert "Invalid Runtime template JSON" in str(error.value)
    assert "never-echo-this" not in str(error.value)
