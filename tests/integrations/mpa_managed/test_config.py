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


def test_explicit_runtime_image_is_optional_and_not_exposed(tmp_path, monkeypatch):
    profile = load_profile(profile_file(tmp_path, monkeypatch))
    assert profile.managed.runtime.image is None
    profile = load_profile(
        profile_file(
            tmp_path, monkeypatch, runtime={"image": "registry.example/mpa:v1"}
        )
    )
    assert profile.managed.runtime.image == "registry.example/mpa:v1"
    assert profile.summary()["runtimeImage"] == "registry.example/mpa:v1"


@pytest.mark.parametrize(
    "runtime",
    [
        {"image": ""},
        {"image": " "},
        {"image": "bad image"},
        {"image": "repo/<tag>"},
        {"unknown": "value"},
    ],
)
def test_invalid_runtime_image_settings_fail_locally(tmp_path, monkeypatch, runtime):
    with pytest.raises(ConfigurationError):
        load_profile(profile_file(tmp_path, monkeypatch, runtime=runtime))


def test_flat_mode_accepts_explicit_runtime_image_and_still_requires_other_fields(
    tmp_path, monkeypatch
):
    path = profile_file(
        tmp_path,
        monkeypatch,
        **{"from-runtime": "", "runtime": {"image": "registry.example/mpa:v1"}},
    )
    data = yaml.safe_load(path.read_text())
    data.update(
        {
            "pg-host": "pg.example",
            "pg-user": "app",
            "pg-password": "fake",
            "model-provider": "openai",
            "model-api-base": "https://model.example",
            "model-api-key": "fake",
            "model-name": "model",
        }
    )
    path.write_text(yaml.safe_dump(data))
    profile = load_profile(path)
    assert "image" not in profile.values
    assert profile.managed.runtime.image == "registry.example/mpa:v1"
    del data["pg-host"]
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ConfigurationError, match="pg_host"):
        load_profile(path)


def test_runtime_environment_resolves_secret_refs_without_exposing_values(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("TEST_RUNTIME_SECRET", "private-test-value")
    profile = load_profile(
        profile_file(
            tmp_path,
            monkeypatch,
            runtime={"env": {"MODEL_AGENT_API_KEY": "${TEST_RUNTIME_SECRET}"}},
        )
    )
    assert profile.managed.runtime.env["MODEL_AGENT_API_KEY"] == "private-test-value"
    assert "private-test-value" not in str(profile.summary())
    monkeypatch.delenv("TEST_RUNTIME_SECRET")
    with pytest.raises(ConfigurationError, match="TEST_RUNTIME_SECRET"):
        load_profile(
            profile_file(
                tmp_path,
                monkeypatch,
                runtime={"env": {"MODEL_AGENT_API_KEY": "${TEST_RUNTIME_SECRET}"}},
            )
        )


@pytest.mark.parametrize(
    "settings",
    [
        {"cpu-milli": 0},
        {"memory-mb": -1},
        {"min-instance": -1},
        {"max-instance": 0},
        {"max-concurrency": 0},
        {"min-instance": 3, "max-instance": 2},
        {"env": {"NOT A KEY": "private-test-value"}},
        {"env": {"PGDATABASE": "private-test-value"}},
        {"env": {"MPA_AGENT_ID": "private-test-value"}},
        {"env": {"AGENTKIT_RUNTIME_ID": "private-test-value"}},
        {"env": {"SKILL_SPACE_ID": "private-test-value"}},
        {"env": {"AGENTKIT_TOOL_ID": "private-test-value"}},
        {"env": {"CHANNEL_STATE_ENCRYPTION_KEY": "private-test-value"}},
        {"env": {"SHARED_APIG_DATABASE_URL": "private-test-value"}},
        {"env": {"DEPLOYMENT_DATABASE_ADMIN_URL": "private-test-value"}},
    ],
)
def test_runtime_override_validation_is_safe(tmp_path, monkeypatch, settings):
    with pytest.raises(ConfigurationError) as error:
        load_profile(profile_file(tmp_path, monkeypatch, runtime=settings))
    assert "private-test-value" not in str(error.value)
