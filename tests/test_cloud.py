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

import os
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import ANY, AsyncMock, Mock, patch

import pytest
import requests

os.environ["VOLCENGINE_ACCESS_KEY"] = "test_access_key"
os.environ["VOLCENGINE_SECRET_KEY"] = "test_secret_key"

from veadk.cloud.cloud_agent_engine import CloudAgentEngine
from veadk.integrations.ve_apig.ve_apig import APIGateway
from veadk.integrations.ve_code_pipeline.ve_code_pipeline import VeCodePipeline
from veadk.integrations.ve_faas.ve_faas import VeFaaS
from veadk.utils.cloud_provider import (
    CloudProvider,
    agentkit_openapi_base,
    apmplus_otlp_endpoint,
    cp_openapi_host,
    default_region,
)


def test_agentkit_openapi_base_uses_byteplus_control_plane_domain() -> None:
    assert agentkit_openapi_base("ap-southeast-1", "byteplus") == (
        "https://agentkit.ap-southeast-1.byteplusapi.com"
    )


def test_apmplus_otlp_endpoint_uses_region() -> None:
    assert (
        apmplus_otlp_endpoint("ap-southeast-1")
        == "http://apmplus-ap-southeast-1.volces.com:4317"
    )


def test_vefaas_create_function_uses_configured_project() -> None:
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        project_name="studio-project",
    )
    service.client = Mock()
    service.client.create_function.return_value = Mock(
        id="function-id", project_name="studio-project"
    )
    service._upload_and_mount_code = Mock()

    service._create_function("studio-function", ".")

    request = service.client.create_function.call_args.args[0]
    assert request.project_name == "studio-project"
    assert request.cpu_milli is None
    assert request.memory_mb == 2048


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("studio_resources", [False, True])
def test_cloud_deploy_function_resources(
    provider: CloudProvider, existing: bool, studio_resources: bool, tmp_path: Path
) -> None:
    engine = CloudAgentEngine(
        volcengine_access_key="test_access_key",
        volcengine_secret_key="test_secret_key",
        provider=provider,
        region="ap-southeast-1" if provider == "byteplus" else "cn-beijing",
    )
    service = engine._vefaas_service
    service.client = Mock()
    service.client.create_function.return_value = SimpleNamespace(
        id="function-id", project_name="default"
    )
    service.client.get_function.return_value = SimpleNamespace(
        command="bash ./run.sh", envs=[]
    )
    service.find_app_id_by_name = Mock(
        return_value="application-id" if existing else None
    )
    service._get_application_status = Mock(
        return_value=(
            "deploy_success",
            {
                "Result": {
                    "CloudResource": '{"framework":{"function":'
                    '{"Id":"function-id","Name":"studio-app-fn"}}}'
                }
            },
        )
    )
    service._upload_and_mount_code = Mock()
    service._create_application = Mock(return_value="application-id")
    service._release_application = Mock(return_value="https://studio.example")
    service.ensure_application_route_methods = Mock()
    service.get_application_route = Mock(return_value=("gateway", "service", "route"))

    with (
        patch("veadk.cloud.cloud_agent_engine.CloudApp"),
        patch.dict("veadk.config.veadk_environments", {}, clear=True),
    ):
        engine.deploy(
            "studio-app",
            str(tmp_path),
            gateway_name="gateway",
            gateway_service_name="service",
            gateway_upstream_name="upstream",
            cpu_milli=8000 if studio_resources else None,
            memory_mb=16384 if studio_resources else None,
            max_instance=1 if studio_resources else None,
        )

    operation = (
        service.client.update_function if existing else service.client.create_function
    )
    operation.assert_called_once()
    request = operation.call_args.args[0]
    assert request.cpu_milli == (8000 if studio_resources else None)
    assert request.memory_mb == (
        16384 if studio_resources else None if existing else 2048
    )
    service.client.update_function_resource.assert_called_once()
    resources = service.client.update_function_resource.call_args.args[0]
    assert resources.function_id == "function-id"
    assert resources.min_instance == 1
    assert resources.max_instance == (1 if studio_resources else None)
    assert resources.reserved_frozen_instance is None


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_vefaas_sets_only_minimum_instance(provider: str) -> None:
    requests = []
    service = object.__new__(VeFaaS)
    service.provider = provider
    service.client = SimpleNamespace(update_function_resource=requests.append)

    service._set_function_min_instance("function-id")

    assert len(requests) == 1
    request = requests[0]
    assert request.function_id == "function-id"
    assert request.min_instance == 1
    assert request.max_instance is None
    assert request.reserved_frozen_instance is None


def test_vefaas_deploy_cleans_created_resources_on_release_failure() -> None:
    service = object.__new__(VeFaaS)
    service.find_app_id_by_name = Mock(return_value=None)
    service._create_function = Mock(return_value=("studio-app-fn", "function-id"))
    service._set_function_min_instance = Mock()
    service._create_application = Mock(return_value="application-id")
    service._release_application = Mock(side_effect=RuntimeError("release failed"))
    service.delete = Mock()
    service.delete_function = Mock()

    with pytest.raises(RuntimeError, match="release failed"):
        service.deploy(
            "studio-app",
            ".",
            gateway_name="gateway",
            gateway_service_name="service",
            gateway_upstream_name="upstream",
        )

    service.delete.assert_called_once_with("application-id")
    service.delete_function.assert_called_once_with("function-id")
    service._set_function_min_instance.assert_not_called()


def test_vefaas_deploy_can_keep_failed_resources_for_inspection() -> None:
    service = object.__new__(VeFaaS)
    service.find_app_id_by_name = Mock(return_value=None)
    service._create_function = Mock(return_value=("studio-app-fn", "function-id"))
    service._set_function_min_instance = Mock()
    service._create_application = Mock(return_value="application-id")
    service._release_application = Mock(side_effect=RuntimeError("release failed"))
    service.delete = Mock()
    service.delete_function = Mock()

    with pytest.raises(RuntimeError, match="release failed"):
        service.deploy(
            "studio-app",
            ".",
            gateway_name="gateway",
            gateway_service_name="service",
            gateway_upstream_name="upstream",
            keep_failed_deploy=True,
        )

    service.delete.assert_not_called()
    service.delete_function.assert_not_called()
    service._set_function_min_instance.assert_not_called()


def test_vefaas_update_code_uses_resource_updating_bundle_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project = tmp_path / "agent"
    project.mkdir()
    service = object.__new__(VeFaaS)
    service.find_app_id_by_name = Mock(return_value="application-id")
    service._get_application_status = Mock(
        return_value=(
            "deploy_success",
            {
                "Result": {
                    "CloudResource": (
                        '{"framework":{"function":{"Name":"studio-app-fn",'
                        '"Id":"function-id"}}}'
                    )
                }
            },
        )
    )
    service._replace_application_code_bundle = Mock()
    service._release_application = Mock(return_value="https://studio.example")
    service._set_function_min_instance = Mock()
    service.ensure_application_route_methods = Mock()

    def _cookiecutter(*, output_dir: str, extra_context: dict, **_: object) -> None:
        package = Path(output_dir) / str(extra_context["local_dir_name"])
        (package / "src").mkdir(parents=True)

    monkeypatch.setattr(
        "veadk.integrations.ve_faas.ve_faas.formatted_timestamp", lambda: "stamp"
    )
    monkeypatch.setattr(
        "veadk.integrations.ve_faas.ve_faas.tempfile.gettempdir",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        "veadk.integrations.ve_faas.ve_faas.cookiecutter", _cookiecutter
    )

    result = service._update_function_code("studio-app", str(project))

    assert result == ("https://studio.example", "application-id", "function-id")
    service._replace_application_code_bundle.assert_called_once_with(
        function_id="function-id",
        path=str(tmp_path / "agent_update_stamp" / "src"),
        environment_overrides=None,
        request_timeout=1800,
    )
    service._set_function_min_instance.assert_called_once_with("function-id")


def test_vefaas_deploy_updates_existing_application_in_place() -> None:
    service = object.__new__(VeFaaS)
    service.find_app_id_by_name = Mock(return_value="application-id")
    service._get_application_status = Mock(
        return_value=(
            "deploy_success",
            {
                "Result": {
                    "CloudResource": '{"framework":{"function":'
                    '{"Id":"function-id","Name":"studio-app-fn"}}}'
                }
            },
        )
    )
    service.update_application_code_bundle = Mock(
        return_value="https://studio.example.com"
    )
    service._create_function = Mock()
    service._create_application = Mock()

    with patch.dict(
        "veadk.config.veadk_environments",
        {"VEADK_STUDIO_DEPLOY_ID": "deploy-id"},
        clear=True,
    ):
        result = service.deploy(
            "studio-app",
            "/tmp/studio-bundle",
            disable_gateway_cors=True,
        )

    assert result == (
        "https://studio.example.com",
        "application-id",
        "function-id",
    )
    service.update_application_code_bundle.assert_called_once_with(
        application_id="application-id",
        function_id="function-id",
        path="/tmp/studio-bundle",
        environment_overrides={"VEADK_STUDIO_DEPLOY_ID": "deploy-id"},
        disable_gateway_cors=True,
        normalize_studio_entrypoint=True,
        cpu_milli=None,
        memory_mb=None,
        max_instance=None,
    )
    service._create_function.assert_not_called()
    service._create_application.assert_not_called()


def test_apig_uses_session_token() -> None:
    gateway = APIGateway(
        access_key="test_access_key",
        secret_key="test_secret_key",
        session_token="test_session_token",
    )

    assert gateway.session_token == "test_session_token"
    assert gateway.api_client.configuration.session_token == "test_session_token"
    assert gateway.api_client.configuration.host == "https://open.volcengineapi.com"


def test_vefaas_passes_session_token_to_apig() -> None:
    with patch("veadk.integrations.ve_faas.ve_faas.APIGateway") as apig:
        VeFaaS(
            access_key="test_access_key",
            secret_key="test_secret_key",
            session_token="test_session_token",
            region="cn-shanghai",
        )

    apig.assert_called_once_with(
        "test_access_key",
        "test_secret_key",
        "cn-shanghai",
        session_token="test_session_token",
        provider="volcengine",
    )


def _vefaas_with_application_route(
    *, methods: list[str], cors_enabled: bool
) -> tuple[VeFaaS, Mock]:
    service = object.__new__(VeFaaS)
    service.get_application_route = Mock(
        return_value=("gateway-id", "service-id", "route-id")
    )
    route = SimpleNamespace(
        id="route-id",
        name="default",
        enable=True,
        priority=100,
        match_rule=SimpleNamespace(
            method=methods,
            path=SimpleNamespace(match_content="/", match_type="Prefix"),
        ),
        upstream_list=[
            SimpleNamespace(
                ai_provider_settings=None,
                upstream_id="upstream-id",
                version=None,
                weight=100,
            )
        ],
        advanced_setting=SimpleNamespace(
            cors_policy_setting=SimpleNamespace(
                allow_credentials=True,
                allow_headers=["*"],
                allow_methods=["GET", "POST"],
                allow_origins=[SimpleNamespace(match_type="regex", value=".*")],
                enable=cors_enabled,
                expose_headers=None,
                max_age=None,
            ),
            timeout_setting=SimpleNamespace(enable=False, timeout=30),
        ),
    )
    get_route = Mock()
    get_route.return_value.get.return_value = SimpleNamespace(route=route)
    update_route = Mock()
    update_route.return_value.get.return_value = None
    cast(Any, service).apig_client = SimpleNamespace(
        apig_20221112_client=SimpleNamespace(
            get_route=get_route,
            update_route=update_route,
        )
    )
    return service, update_route


def test_vefaas_application_route_adds_patch_without_losing_configuration() -> None:
    service, update_route = _vefaas_with_application_route(
        methods=["GET", "POST"], cors_enabled=True
    )

    assert service.ensure_application_route_methods("application-id") is True

    request = update_route.call_args.args[0]
    assert request.match_rule.method == ["GET", "POST", "PATCH"]
    assert request.upstream_list[0].upstream_id == "upstream-id"
    assert request.advanced_setting.cors_policy_setting.allow_methods == [
        "GET",
        "POST",
        "PATCH",
    ]
    assert request.advanced_setting.cors_policy_setting.allow_origins[0].value == ".*"
    assert request.advanced_setting.cors_policy_setting.allow_credentials is True
    assert request.advanced_setting.cors_policy_setting.enable is True


def test_vefaas_application_route_disables_cors_when_methods_are_present() -> None:
    service, update_route = _vefaas_with_application_route(
        methods=["GET", "POST", "PATCH"], cors_enabled=True
    )

    assert (
        service.ensure_application_route_methods("application-id", disable_cors=True)
        is True
    )

    request = update_route.call_args.args[0]
    assert request.match_rule.method == ["GET", "POST", "PATCH"]
    assert request.advanced_setting.cors_policy_setting.allow_origins is None
    assert request.advanced_setting.cors_policy_setting.allow_credentials is None
    assert request.advanced_setting.cors_policy_setting.enable is False


def test_vefaas_application_route_skips_safe_configuration() -> None:
    service, update_route = _vefaas_with_application_route(
        methods=["GET", "POST", "PATCH"], cors_enabled=False
    )

    assert (
        service.ensure_application_route_methods("application-id", disable_cors=True)
        is False
    )
    update_route.assert_not_called()


def test_vefaas_deploy_can_disable_gateway_cors() -> None:
    service = object.__new__(VeFaaS)
    service.find_app_id_by_name = Mock(return_value=None)
    cast(Any, service).apig_client = SimpleNamespace(
        list_gateways=Mock(return_value=SimpleNamespace(items=[]))
    )
    service._create_function = Mock(return_value=("studio-app-fn", "function-id"))
    service._create_application = Mock(return_value="application-id")
    service._release_application = Mock(return_value="https://studio.example.com")
    service._set_function_min_instance = Mock()
    service.ensure_application_route_methods = Mock()

    service.deploy(
        "studio-app",
        ".",
        gateway_name="gateway",
        gateway_service_name="service",
        gateway_upstream_name="upstream",
        disable_gateway_cors=True,
    )

    service.ensure_application_route_methods.assert_called_once_with(
        "application-id",
        disable_cors=True,
    )
    service._set_function_min_instance.assert_called_once_with(
        "function-id", max_instance=None
    )


def test_vefaas_code_upload_callback_uses_configured_region() -> None:
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="cn-shanghai",
    )
    service.client = Mock()
    service.client.get_code_upload_address.return_value = Mock(
        upload_address="https://example.com/upload"
    )

    with (
        patch(
            "veadk.integrations.ve_faas.ve_faas.zip_and_encode_folder",
            return_value=(b"archive", 7, None),
        ),
        patch("veadk.integrations.ve_faas.ve_faas.requests.put") as upload,
        patch("veadk.integrations.ve_faas.ve_faas.signed_request") as callback,
    ):
        upload.return_value = Mock(status_code=200)
        service._upload_and_mount_code("function-id", ".")

    upload.assert_called_once_with(
        url="https://example.com/upload",
        data=ANY,
        headers={"Content-Type": "application/zip"},
        timeout=(300, 300),
    )
    callback.assert_called_once_with(
        ak="test_access_key",
        sk="test_secret_key",
        target="CodeUploadCallback",
        body={"FunctionId": "function-id"},
        region="cn-shanghai",
        session_token="",
        host="open.volcengineapi.com",
    )


def test_vefaas_large_code_upload_uses_bounded_extended_timeout() -> None:
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="cn-shanghai",
    )
    service.client = Mock()
    service.client.get_code_upload_address.return_value = Mock(
        upload_address="https://example.com/upload"
    )
    archive_size = 64 * 1024 * 1024 + 1

    with (
        patch(
            "veadk.integrations.ve_faas.ve_faas.zip_and_encode_folder",
            return_value=(b"archive", archive_size, None),
        ),
        patch("veadk.integrations.ve_faas.ve_faas.requests.put") as upload,
        patch("veadk.integrations.ve_faas.ve_faas.signed_request"),
    ):
        upload.return_value = Mock(status_code=200)
        service._upload_and_mount_code("function-id", ".")

    upload.assert_called_once_with(
        url="https://example.com/upload",
        data=ANY,
        headers={"Content-Type": "application/zip"},
        timeout=(300, 1800),
    )


def test_vefaas_large_code_upload_retries_one_connection_interruption() -> None:
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="cn-shanghai",
    )
    service.client = Mock()
    service.client.get_code_upload_address.return_value = Mock(
        upload_address="https://example.com/upload"
    )
    archive_size = 64 * 1024 * 1024 + 1
    sent = []

    def send_archive(**kwargs):
        body = kwargs["data"]
        assert body.uploaded == 0
        sent.append(b"".join(body))
        if len(sent) == 1:
            raise requests.ConnectionError()
        return Mock(status_code=200)

    with (
        patch(
            "veadk.integrations.ve_faas.ve_faas.zip_and_encode_folder",
            return_value=(b"archive", archive_size, None),
        ),
        patch(
            "veadk.integrations.ve_faas.ve_faas.requests.put",
            side_effect=send_archive,
        ) as upload,
        patch("veadk.integrations.ve_faas.ve_faas.signed_request") as callback,
        patch("veadk.integrations.ve_faas.ve_faas.time.sleep") as sleep,
    ):
        service._upload_and_mount_code("function-id", ".")

    assert upload.call_count == 2
    assert sent == [b"archive", b"archive"]
    assert (
        upload.call_args_list[0].kwargs["data"] is not upload.call_args.kwargs["data"]
    )
    sleep.assert_called_once_with(1)
    callback.assert_called_once()


@pytest.mark.parametrize(
    "provider,region", [("volcengine", "cn-shanghai"), ("byteplus", "ap-southeast-1")]
)
@pytest.mark.parametrize("status_code", [200, 403, 503])
def test_vefaas_progress_upload_preserves_http_body_and_checks_response(
    provider: str, region: str, status_code: int, capsys: pytest.CaptureFixture[str]
) -> None:
    archive = bytes(range(256)) * 1024 + b"zip trailer"
    received = []

    class UploadHandler(BaseHTTPRequestHandler):
        def do_PUT(self) -> None:
            received.append(
                (
                    dict(self.headers),
                    self.rfile.read(int(self.headers["Content-Length"])),
                )
            )
            self.send_response(status_code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), UploadHandler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    service = VeFaaS(
        "test_access_key", "test_secret_key", region=region, provider=provider
    )
    service.client = Mock()
    service.client.get_code_upload_address.return_value = Mock(
        upload_address=f"http://127.0.0.1:{server.server_port}/upload"
    )
    try:
        with (
            patch(
                "veadk.integrations.ve_faas.ve_faas.zip_and_encode_folder",
                return_value=(archive, len(archive), None),
            ),
            patch("veadk.integrations.ve_faas.ve_faas.signed_request") as callback,
        ):
            if status_code == 200:
                service._upload_and_mount_code("function-id", ".")
                callback.assert_called_once()
                assert callback.call_args.kwargs["region"] == region
            else:
                with pytest.raises(ValueError, match=f"status code {status_code}"):
                    service._upload_and_mount_code("function-id", ".")
                callback.assert_not_called()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)

    assert len(received) == 1
    headers, payload = received[0]
    assert payload == archive
    assert headers["Content-Length"] == str(len(archive))
    assert headers["Content-Type"] == "application/zip"
    assert "Transfer-Encoding" not in headers
    output = capsys.readouterr().err
    assert "100%" in output
    assert "MB/s" in output
    assert "Waiting for response" in output
    assert ("Uploaded code" in output) == (status_code == 200)
    assert ("Upload failed" in output) == (status_code != 200)


def test_vefaas_code_upload_callback_uses_byteplus_host() -> None:
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="ap-southeast-1",
        provider="byteplus",
    )
    service.client = Mock()
    service.client.get_code_upload_address.return_value = Mock(
        upload_address="https://example.com/upload"
    )

    with (
        patch(
            "veadk.integrations.ve_faas.ve_faas.zip_and_encode_folder",
            return_value=(b"archive", 7, None),
        ),
        patch("veadk.integrations.ve_faas.ve_faas.requests.put") as upload,
        patch("veadk.integrations.ve_faas.ve_faas.signed_request") as callback,
    ):
        upload.return_value = Mock(status_code=200)
        service._upload_and_mount_code("function-id", ".")

    callback.assert_called_once_with(
        ak="test_access_key",
        sk="test_secret_key",
        target="CodeUploadCallback",
        body={"FunctionId": "function-id"},
        region="ap-southeast-1",
        session_token="",
        host="vefaas.ap-southeast-1.byteplusapi.com",
    )


@pytest.mark.parametrize(
    "provider,region", [("volcengine", "cn-shanghai"), ("byteplus", "ap-southeast-1")]
)
@pytest.mark.parametrize("retry_succeeds", [True, False])
def test_vefaas_partial_upload_retry_restarts_body_and_progress(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    provider: str,
    region: str,
    retry_succeeds: bool,
) -> None:
    archive = b"x" * 150_000
    service = VeFaaS(
        "test_access_key", "test_secret_key", region=region, provider=provider
    )
    service.client = Mock()
    service.client.get_code_upload_address.return_value = Mock(
        upload_address="https://example.com/upload"
    )
    monkeypatch.setattr(
        "veadk.integrations.ve_faas.ve_faas._LARGE_CODE_BUNDLE_BYTES", 100_000
    )
    attempts = []

    def send_archive(**kwargs):
        body = kwargs["data"]
        assert body.uploaded == 0
        attempts.append(body)
        if len(attempts) == 1 or not retry_succeeds:
            chunks = iter(body)
            assert next(chunks) == archive[: 64 * 1024]
            next(chunks)
            assert body.uploaded == 64 * 1024
            raise requests.Timeout("upload timed out")
        assert b"".join(body) == archive
        return Mock(status_code=200)

    with (
        patch(
            "veadk.integrations.ve_faas.ve_faas.zip_and_encode_folder",
            return_value=(archive, len(archive), None),
        ),
        patch(
            "veadk.integrations.ve_faas.ve_faas.requests.put", side_effect=send_archive
        ),
        patch("veadk.integrations.ve_faas.ve_faas.signed_request") as callback,
        patch("veadk.integrations.ve_faas.ve_faas.time.sleep"),
    ):
        if retry_succeeds:
            service._upload_and_mount_code("function-id", ".")
            callback.assert_called_once()
        else:
            with pytest.raises(ValueError, match="upload request failed"):
                service._upload_and_mount_code("function-id", ".")
            callback.assert_not_called()
    assert len(attempts) == 2
    output = capsys.readouterr().err
    assert "(1/2)" in output
    assert "(2/2)" in output
    retry_line = next(line for line in output.splitlines() if "(2/2)" in line)
    assert "  0%" in retry_line
    assert "0.00 / 0.14 MB" in retry_line
    assert ("Uploaded code" in output) == retry_succeeds


def test_vefaas_byteplus_application_uses_configured_template() -> None:
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="ap-southeast-1",
        provider="byteplus",
        application_template_id="byteplus-template-id",
    )

    with patch("veadk.integrations.ve_faas.ve_faas.ve_request") as request:
        request.return_value = {"Result": {"Status": "create_success", "Id": "app-id"}}

        app_id = service._create_application(
            "studio-app",
            "studio-function",
            "gateway",
            "upstream",
            "service",
        )

    assert app_id == "app-id"
    request_body = request.call_args.kwargs["request_body"]
    assert request_body["TemplateId"] == "byteplus-template-id"
    assert request_body["Config"]["Region"] == "ap-southeast-1"
    assert request_body["Config"]["EnableMcpSession"] is True


def test_vefaas_application_can_disable_mcp_session() -> None:
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="ap-southeast-1",
        provider="byteplus",
        application_template_id="byteplus-template-id",
    )

    with patch("veadk.integrations.ve_faas.ve_faas.ve_request") as request:
        request.return_value = {"Result": {"Status": "create_success", "Id": "app-id"}}

        service._create_application(
            "studio-app",
            "studio-function",
            "gateway",
            "upstream",
            "service",
            enable_mcp_session=False,
        )

    request_body = request.call_args.kwargs["request_body"]
    assert request_body["Config"]["EnableMcpSession"] is False


def test_vefaas_byteplus_application_uses_builtin_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VEFAAS_APPLICATION_TEMPLATE_ID", raising=False)
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="ap-southeast-1",
        provider="byteplus",
    )

    with patch("veadk.integrations.ve_faas.ve_faas.ve_request") as request:
        request.return_value = {"Result": {"Status": "create_success", "Id": "app-id"}}

        app_id = service._create_application(
            "studio-app",
            "studio-function",
            "gateway",
            "upstream",
            "service",
        )

    assert app_id == "app-id"
    request_body = request.call_args.kwargs["request_body"]
    assert request_body["TemplateId"] == "697a03b8adb54b0008fdebd0"


def test_vefaas_byteplus_application_requires_template_for_unknown_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VEFAAS_APPLICATION_TEMPLATE_ID", raising=False)
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="ap-southeast-2",
        provider="byteplus",
    )

    with (
        patch("veadk.integrations.ve_faas.ve_faas.ve_request") as request,
        pytest.raises(ValueError, match="No built-in TemplateId"),
    ):
        service._create_application(
            "studio-app",
            "studio-function",
            "gateway",
            "upstream",
            "service",
        )

    request.assert_not_called()


def test_cloud_agent_engine_passes_application_template() -> None:
    with (
        patch("veadk.cloud.cloud_agent_engine.VeFaaS") as vefaas_class,
        patch("veadk.cloud.cloud_agent_engine.APIGateway"),
        patch("veadk.cloud.cloud_agent_engine.IdentityClient"),
    ):
        CloudAgentEngine(
            volcengine_access_key="test_access_key",
            volcengine_secret_key="test_secret_key",
            region="ap-southeast-1",
            provider="byteplus",
            vefaas_application_template_id="byteplus-template-id",
        )

    assert (
        vefaas_class.call_args.kwargs["application_template_id"]
        == "byteplus-template-id"
    )


def test_default_volcengine_region_uses_region_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGION", "cn-shanghai")

    assert default_region("volcengine") == "cn-shanghai"


def test_code_pipeline_uses_region_env_for_volcengine_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGION", "cn-shanghai")

    service = VeCodePipeline(
        volcengine_access_key="test_access_key",
        volcengine_secret_key="test_secret_key",
        provider="volcengine",
    )

    assert service.region == "cn-shanghai"
    assert service.host == "open.volcengineapi.com"


def test_cloud_agent_engine_uses_region_env_when_region_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGION", "cn-shanghai")

    with (
        patch("veadk.cloud.cloud_agent_engine.VeFaaS") as vefaas_class,
        patch("veadk.cloud.cloud_agent_engine.APIGateway") as apig_class,
        patch("veadk.cloud.cloud_agent_engine.IdentityClient") as identity_class,
    ):
        CloudAgentEngine(
            volcengine_access_key="test_access_key",
            volcengine_secret_key="test_secret_key",
        )

    assert vefaas_class.call_args.kwargs["region"] == "cn-shanghai"
    assert apig_class.call_args.kwargs["region"] == "cn-shanghai"
    assert identity_class.call_args.kwargs["region"] == "cn-shanghai"


def test_code_pipeline_uses_byteplus_region_host() -> None:
    service = VeCodePipeline(
        volcengine_access_key="test_access_key",
        volcengine_secret_key="test_secret_key",
        provider="byteplus",
    )

    assert service.region == "ap-southeast-1"
    assert service.host == "cp.ap-southeast-1.byteplusapi.com"
    assert cp_openapi_host("ap-southeast-1", "byteplus") == service.host


@pytest.mark.asyncio
async def test_cloud():
    app_name = "test-app"
    key = "CloudTestIdentifier123"
    test_endpoint = "https://test-endpoint.volcengine.com"
    test_message = "Hello cloud agent"

    # Create temporary directory with required agent.py file for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        with open(os.path.join(temp_dir, "agent.py"), "w") as f:
            f.write(f"# Test agent implementation with {key}")

        # Mock shutil.copy to avoid template file copying issues
        with patch("shutil.copy"):
            with patch("veadk.cloud.cloud_agent_engine.VeFaaS") as mock_vefaas_class:
                # Setup mock VeFaaS service for all operations
                mock_vefaas_service = Mock()
                mock_vefaas_class.return_value = mock_vefaas_service

                # Mock deploy operation
                mock_vefaas_service.deploy.return_value = (
                    test_endpoint,
                    "app-123",
                    "func-456",
                )

                # Mock update operation
                mock_vefaas_service._update_function_code.return_value = (
                    test_endpoint,
                    "app-123",
                    "func-456",
                )

                # Mock remove operation
                mock_vefaas_service.find_app_id_by_name.return_value = "app-123"
                mock_vefaas_service.delete.return_value = None

                mock_vefaas_service.get_application_route.return_value = (
                    "gw-123",
                    "svc-456",
                    "route-789",
                )

                # Test CloudAgentEngine creation and deploy functionality
                engine = CloudAgentEngine(
                    project="studio-project",
                    volcengine_access_key="test_access_key",
                    volcengine_secret_key="test_secret_key",
                    volcengine_session_token="test_session_token",
                )
                mock_vefaas_class.assert_called_once_with(
                    access_key="test_access_key",
                    secret_key="test_secret_key",
                    session_token="test_session_token",
                    region="cn-beijing",
                    project_name="studio-project",
                    provider="volcengine",
                    application_template_id="",
                )

                # Test deploy operation
                cloud_app = engine.deploy(application_name=app_name, path=temp_dir)

                assert (
                    mock_vefaas_service.deploy.call_args.kwargs["disable_gateway_cors"]
                    is False
                )
                # Verify deployment result contains expected values
                assert cloud_app.vefaas_application_name == app_name
                assert cloud_app.vefaas_endpoint == test_endpoint
                assert cloud_app.vefaas_application_id == "app-123"

                # Test update_function_code operation
                updated_app = engine.update_function_code(
                    application_name=app_name, path=temp_dir
                )

                # Verify update result maintains same endpoint
                assert updated_app.vefaas_endpoint == test_endpoint

                # Test remove operation with mocked user input
                with patch("builtins.input", return_value="y"):
                    engine.remove(app_name)
                    mock_vefaas_service.find_app_id_by_name.assert_called_with(app_name)
                    mock_vefaas_service.delete.assert_called_with("app-123")

                # Test CloudApp message_send functionality
                mock_response = Mock()
                mock_message = Mock()
                mock_response.root.result = mock_message

                with patch.object(cloud_app, "_get_a2a_client") as mock_get_client:
                    mock_client = AsyncMock()
                    mock_client.send_message = AsyncMock(return_value=mock_response)
                    mock_get_client.return_value = mock_client

                    # Test message sending to cloud agent
                    result = await cloud_app.message_send(
                        message=test_message,
                        session_id="session-123",
                        user_id="user-456",
                    )

                    # Verify message sending result
                    assert result == mock_message
                    mock_client.send_message.assert_called_once()

                # Test CloudApp delete_self functionality
                with patch("builtins.input", return_value="y"):
                    with patch(
                        "veadk.integrations.ve_faas.ve_faas.VeFaaS"
                    ) as mock_vefaas_in_app:
                        mock_vefaas_client = Mock()
                        mock_vefaas_in_app.return_value = mock_vefaas_client
                        mock_vefaas_client.delete.return_value = None
                        with patch.object(
                            cloud_app, "_get_vefaas_application_id_by_name"
                        ) as mock_get_id_by_name:
                            mock_get_id_by_name.return_value = None
                            cloud_app.delete_self(
                                volcengine_ak="test_access_key",
                                volcengine_sk="test_secret_key",
                            )
                            mock_vefaas_client.delete.assert_called_with("app-123")

                # Verify all mocks were called as expected
                mock_vefaas_service.deploy.assert_called_once()
                mock_vefaas_service._update_function_code.assert_called_once()
