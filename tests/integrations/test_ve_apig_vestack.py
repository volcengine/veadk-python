import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from veadk.integrations.ve_apig.ve_apig import APIGateway


def _thread(result):
    thread = MagicMock()
    thread.get.return_value = result
    return thread


def test_create_vestack_gateway_uses_cluster_native_request_shape() -> None:
    apig = APIGateway.__new__(APIGateway)
    apig.region = "e70"
    apig.apig_client = MagicMock()
    apig.apig_client.create_gateway.return_value = _thread(
        SimpleNamespace(to_dict=lambda: {"id": "gw-1"})
    )
    apig.apig_client.list_gateways.return_value = _thread(
        SimpleNamespace(
            items=[SimpleNamespace(to_dict=lambda: {"id": "gw-1", "status": "Running"})]
        )
    )

    gateway_id = apig.create_serverless_gateway(
        "studio-gateway",
        vestack_cluster_id="cluster-1",
        vestack_namespace="studio-apig",
        vestack_cluster_name="aio",
    )

    assert gateway_id == "gw-1"
    request = apig.apig_client.create_gateway.call_args.args[0]
    assert request.cluster_spec == {
        "ClusterId": "cluster-1",
        "Namespace": "studio-apig",
        "ClusterName": "aio",
    }
    assert request.resource_spec["Replicas"] == 2
    assert request.attribute_map["cluster_spec"] == "ClusterSpec"


def test_create_vestack_gateway_requires_namespace() -> None:
    apig = APIGateway.__new__(APIGateway)
    apig.region = "e70"

    try:
        apig.create_serverless_gateway(
            "studio-gateway",
            vestack_cluster_id="cluster-1",
        )
    except ValueError as error:
        assert str(error) == "VeStack APIG namespace is required"
    else:
        raise AssertionError("missing VeStack namespace must fail")


def test_create_public_gateway_keeps_sdk_resource_spec() -> None:
    apig = APIGateway.__new__(APIGateway)
    apig.region = "cn-beijing"
    apig.apig_client = MagicMock()
    apig.apig_client.create_gateway.return_value = _thread(
        SimpleNamespace(to_dict=lambda: {"id": "gw-public"})
    )
    apig.apig_client.list_gateways.return_value = _thread(
        SimpleNamespace(
            items=[
                SimpleNamespace(
                    to_dict=lambda: {"id": "gw-public", "status": "Running"}
                )
            ]
        )
    )

    assert apig.create_serverless_gateway("studio-gateway") == "gw-public"

    request = apig.apig_client.create_gateway.call_args.args[0]
    assert request.resource_spec.replicas == 2
    assert request.resource_spec.network_type == {
        "EnablePublicNetwork": True,
        "EnablePrivateNetwork": False,
    }


def test_get_vestack_gateway_external_http_address_restores_transport() -> None:
    apig = APIGateway.__new__(APIGateway)
    response = SimpleNamespace(
        data=json.dumps(
            {
                "Result": {
                    "Gateway": {
                        "GatewayExternalAddress": {
                            "IPs": ["192.0.2.10"],
                            "Items": [
                                {"Protocol": "HTTPS", "Port": 443},
                                {"Protocol": "HTTP", "Port": 32968},
                            ],
                        }
                    }
                }
            }
        ).encode()
    )
    original_request = MagicMock(return_value=response)
    rest_client = SimpleNamespace(request=original_request)
    apig.apig_client = SimpleNamespace(
        api_client=SimpleNamespace(rest_client=rest_client),
    )
    apig.apig_client.get_gateway = MagicMock(
        side_effect=lambda _request: rest_client.request("GET", "/gateway")
    )

    assert apig.get_gateway_external_http_address("gw-1") == (
        "192.0.2.10",
        32968,
    )
    assert rest_client.request is original_request


def test_get_vestack_gateway_external_http_address_requires_http_listener() -> None:
    apig = APIGateway.__new__(APIGateway)
    response = SimpleNamespace(
        data=json.dumps(
            {
                "Result": {
                    "Gateway": {
                        "GatewayExternalAddress": {
                            "IPs": ["192.0.2.10"],
                            "Items": [{"Protocol": "HTTPS", "Port": 443}],
                        }
                    }
                }
            }
        )
    )
    rest_client = SimpleNamespace(request=MagicMock(return_value=response))
    apig.apig_client = SimpleNamespace(
        api_client=SimpleNamespace(rest_client=rest_client),
    )
    apig.apig_client.get_gateway = MagicMock(
        side_effect=lambda _request: rest_client.request("GET", "/gateway")
    )

    try:
        apig.get_gateway_external_http_address("gw-1")
    except RuntimeError as error:
        assert "external HTTP address" in str(error)
    else:
        raise AssertionError("missing HTTP listener must fail")


def test_create_vestack_service_uses_service_domain_spec() -> None:
    apig = APIGateway.__new__(APIGateway)
    apig.apig_client = MagicMock()
    apig.apig_client.create_gateway_service.return_value = _thread(
        SimpleNamespace(to_dict=lambda: {"id": "svc-1"})
    )

    service_id = apig.create_gateway_service(
        "gw-1",
        "studio-service",
        custom_domain="studio.example.com",
        vestack=True,
    )

    assert service_id == "svc-1"
    request = apig.apig_client.create_gateway_service.call_args.args[0]
    assert request.service_domain_spec == [
        {"Domain": "studio.example.com", "Protocol": ["HTTP"]}
    ]
    assert request.attribute_map["service_domain_spec"] == "ServiceDomainSpec"


def test_create_vestack_service_requires_domain() -> None:
    apig = APIGateway.__new__(APIGateway)
    apig.apig_client = MagicMock()

    try:
        apig.create_gateway_service("gw-1", "studio-service", vestack=True)
    except ValueError as error:
        assert str(error) == "VeStack APIG service requires a domain"
    else:
        raise AssertionError("missing VeStack service domain must fail")


def test_create_public_service_keeps_sdk_custom_domain() -> None:
    apig = APIGateway.__new__(APIGateway)
    apig.apig_client = MagicMock()
    apig.apig_client.create_gateway_service.return_value = _thread(
        SimpleNamespace(to_dict=lambda: {"id": "svc-public"})
    )

    service_id = apig.create_gateway_service(
        "gw-1",
        "studio-service",
        custom_domain="studio.example.com",
    )

    assert service_id == "svc-public"
    request = apig.apig_client.create_gateway_service.call_args.args[0]
    assert request.custom_domains[0].domain == "studio.example.com"
    assert not hasattr(request, "service_domain_spec")


def test_find_helpers_return_only_named_resources() -> None:
    missing = SimpleNamespace(name="other")
    service = SimpleNamespace(name="studio-service")
    upstream = SimpleNamespace(name="studio-upstream")
    route = SimpleNamespace(name="studio-route")
    apig = APIGateway.__new__(APIGateway)
    apig.apig_client = MagicMock()
    apig.apig_20221112_client = MagicMock()
    apig.apig_client.list_gateway_services.return_value = SimpleNamespace(
        items=[missing, service]
    )
    apig.apig_client.list_upstreams.return_value = SimpleNamespace(
        items=[missing, upstream]
    )
    apig.apig_20221112_client.list_routes.return_value = SimpleNamespace(
        items=[missing, route]
    )

    assert apig.find_gateway_service("gw-1", "studio-service") is service
    assert apig.find_upstream("gw-1", "studio-upstream") is upstream
    assert apig.find_route("svc-1", "studio-route") is route
