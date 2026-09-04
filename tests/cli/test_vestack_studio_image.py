from pathlib import Path

from veadk.utils.cloud_provider import (
    apig_openapi_host,
    configure_openapi_tls,
    iam_openapi_host,
    vefaas_openapi_host,
)


def test_vestack_control_plane_hosts_are_overridable(monkeypatch) -> None:
    monkeypatch.setenv("VEFAAS_OPENAPI_HOST", "http://top.vestack.cloud/")
    monkeypatch.setenv("APIG_OPENAPI_HOST", "top.vestack.cloud")
    monkeypatch.setenv("IAM_OPENAPI_HOST", "https://top.vestack.cloud/")

    assert vefaas_openapi_host("cn-bj", "volcengine") == "top.vestack.cloud"
    assert apig_openapi_host("cn-bj", "volcengine") == "top.vestack.cloud"
    assert iam_openapi_host("volcengine") == "top.vestack.cloud"


def test_vestack_control_plane_tls_is_explicit(monkeypatch) -> None:
    class Configuration:
        ssl_ca_cert = ""
        verify_ssl = True

    configuration = Configuration()
    monkeypatch.setenv("VOLCENGINE_OPENAPI_CA_BUNDLE", "/etc/ssl/private-ca.pem")
    monkeypatch.setenv("VOLCENGINE_OPENAPI_VERIFY_SSL", "false")
    configure_openapi_tls(configuration)
    assert configuration.ssl_ca_cert == "/etc/ssl/private-ca.pem"
    assert configuration.verify_ssl is True

    monkeypatch.delenv("VOLCENGINE_OPENAPI_CA_BUNDLE")
    configure_openapi_tls(configuration)
    assert configuration.verify_ssl is False


def test_vestack_image_exposes_platform_entrypoint_and_healthcheck() -> None:
    root = Path(__file__).resolve().parents[2]
    dockerfile = (root / "docker" / "Dockerfile.vestack").read_text()
    entrypoint = (root / "docker" / "vestack-entrypoint.sh").read_text()

    assert "EXPOSE 8000" in dockerfile
    assert "COPY docker/vestack-entrypoint.sh /app/run.sh" in dockerfile
    assert 'ENTRYPOINT ["/app/run.sh"]' in dockerfile
    assert "127.0.0.1:8000/ping" in dockerfile
    assert "VOLCENGINE_AGENTKIT_HOST:=top.vestack.cloud" in entrypoint
    assert "VEADK_STUDIO_AUTH_MODE:=gateway" in entrypoint
    assert "VEADK_STUDIO_LISTEN_PORT" in entrypoint
    assert '--auth-mode "${VEADK_STUDIO_AUTH_MODE}"' in entrypoint
