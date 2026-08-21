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

from __future__ import annotations

from threading import Thread
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from veadk.integrations.agentkit.studio_routes import (
    ROUTE_PROTOCOL_VERSION,
    mount_studio_route_host,
    route_catalog_revision,
)


def _manifest(path: str = "/print_hello") -> dict[str, Any]:
    return {
        "id": "print_hello",
        "method": "GET",
        "path": path,
        "handler_revision": "demo-v1",
        "timeout_ms": 30_000,
        "response_mode": "json",
    }


def test_route_catalog_revision_is_stable() -> None:
    first = _manifest("/print_hello")
    second = {
        **_manifest("/print_goodbye"),
        "id": "print_goodbye",
        "method": "POST",
    }

    assert route_catalog_revision([first, second]) == route_catalog_revision(
        [second, first]
    )


def test_route_host_advertises_explicit_opt_in() -> None:
    app = FastAPI()
    mount_studio_route_host(app=app, enabled=False)

    response = TestClient(app).get("/__studio/routes/v1/capabilities")

    assert response.json() == {
        "enabled": False,
        "protocol": ROUTE_PROTOCOL_VERSION,
        "transports": [],
        "route_modes": [],
    }


def test_websocket_catalog_makes_runtime_path_execute_on_bff() -> None:
    app = FastAPI()
    mount_studio_route_host(app=app, enabled=True)
    manifest = _manifest()
    revision = route_catalog_revision([manifest])
    result: dict[str, Any] = {}

    with TestClient(app) as client:
        with client.websocket_connect("/__studio/routes/v1/channel") as websocket:
            websocket.send_json(
                {
                    "type": "channel.hello",
                    "protocol": ROUTE_PROTOCOL_VERSION,
                    "studio_instance_id": "studio-1",
                }
            )
            assert websocket.receive_json()["type"] == "channel.ready"
            websocket.send_json(
                {
                    "type": "route.catalog.replace",
                    "revision": revision,
                    "routes": [manifest],
                }
            )
            assert websocket.receive_json() == {
                "type": "route.catalog.ack",
                "revision": revision,
                "active_routes": 1,
            }

            def request_route() -> None:
                response = client.get("/print_hello")
                result["status"] = response.status_code
                result["body"] = response.json()

            request_thread = Thread(target=request_route)
            request_thread.start()
            route_call = websocket.receive_json()
            assert route_call["type"] == "route.call"
            assert route_call["route_id"] == "print_hello"
            assert route_call["request"]["path"] == "/print_hello"
            assert "authorization" not in route_call["request"]["headers"]
            websocket.send_json(
                {
                    "type": "route.result",
                    "request_id": route_call["request_id"],
                    "catalog_revision": revision,
                    "response": {
                        "status": 200,
                        "headers": {"content-type": "application/json"},
                        "body": {
                            "message": "hello from Studio BFF",
                            "executed_by": "studio-bff",
                        },
                    },
                }
            )
            request_thread.join(timeout=5)

    assert result == {
        "status": 200,
        "body": {
            "message": "hello from Studio BFF",
            "executed_by": "studio-bff",
        },
    }


def test_segment_template_route_sends_validated_path_parameter_to_bff() -> None:
    app = FastAPI()
    mount_studio_route_host(app=app, enabled=True)
    manifest = {
        **_manifest("/harness/skills/spaces/{space_id}/skills"),
        "id": "studio_list_skills_in_space",
    }
    revision = route_catalog_revision([manifest])
    result: dict[str, Any] = {}

    with TestClient(app) as client:
        with client.websocket_connect("/__studio/routes/v1/channel") as websocket:
            websocket.send_json(
                {"type": "channel.hello", "protocol": ROUTE_PROTOCOL_VERSION}
            )
            ready = websocket.receive_json()
            assert ready["type"] == "channel.ready"
            websocket.send_json(
                {
                    "type": "route.catalog.replace",
                    "revision": revision,
                    "routes": [manifest],
                }
            )
            assert websocket.receive_json()["type"] == "route.catalog.ack"

            def request_route() -> None:
                response = client.get(
                    "/harness/skills/spaces/space-123/skills?region=cn-beijing"
                )
                result["status"] = response.status_code
                result["body"] = response.json()

            request_thread = Thread(target=request_route)
            request_thread.start()
            route_call = websocket.receive_json()
            assert route_call["route_id"] == "studio_list_skills_in_space"
            assert route_call["request"]["path_params"] == {"space_id": "space-123"}
            websocket.send_json(
                {
                    "type": "route.result",
                    "request_id": route_call["request_id"],
                    "catalog_revision": revision,
                    "response": {
                        "status": 200,
                        "body": {"items": [], "totalCount": 0},
                    },
                }
            )
            request_thread.join(timeout=5)

    assert result == {
        "status": 200,
        "body": {"items": [], "totalCount": 0},
    }


def test_only_allowlisted_harness_routes_can_be_registered() -> None:
    app = FastAPI()
    mount_studio_route_host(app=app, enabled=True)
    manifest = _manifest("/harness/apps")
    revision = route_catalog_revision([manifest])

    with TestClient(app) as client:
        with client.websocket_connect("/__studio/routes/v1/channel") as websocket:
            websocket.send_json(
                {"type": "channel.hello", "protocol": ROUTE_PROTOCOL_VERSION}
            )
            websocket.receive_json()
            websocket.send_json(
                {
                    "type": "route.catalog.replace",
                    "revision": revision,
                    "routes": [manifest],
                }
            )
            rejection = websocket.receive_json()

    assert rejection["type"] == "route.catalog.nack"
    assert "reserved route path" in rejection["error"]


def test_skill_catalog_routes_reject_write_methods() -> None:
    app = FastAPI()
    mount_studio_route_host(app=app, enabled=True)
    manifest = {
        **_manifest("/harness/skills/spaces"),
        "method": "POST",
    }
    revision = route_catalog_revision([manifest])

    with TestClient(app) as client:
        with client.websocket_connect("/__studio/routes/v1/channel") as websocket:
            websocket.send_json(
                {"type": "channel.hello", "protocol": ROUTE_PROTOCOL_VERSION}
            )
            websocket.receive_json()
            websocket.send_json(
                {
                    "type": "route.catalog.replace",
                    "revision": revision,
                    "routes": [manifest],
                }
            )
            rejection = websocket.receive_json()

    assert rejection["type"] == "route.catalog.nack"
    assert "must use GET" in rejection["error"]


def test_arbitrary_path_templates_are_rejected() -> None:
    manifest = _manifest("/customer/{customer_id}")

    try:
        route_catalog_revision([manifest])
    except ValueError as error:
        assert "path parameters are limited" in str(error)
    else:
        raise AssertionError("arbitrary path template was accepted")


def test_reserved_route_catalog_is_rejected_without_replacing_native_route() -> None:
    app = FastAPI()

    @app.post("/run_sse")
    async def run_sse() -> dict[str, bool]:
        return {"native": True}

    mount_studio_route_host(app=app, enabled=True)
    manifest = {**_manifest("/run_sse"), "method": "POST"}

    with TestClient(app) as client:
        with client.websocket_connect("/__studio/routes/v1/channel") as websocket:
            websocket.send_json(
                {"type": "channel.hello", "protocol": ROUTE_PROTOCOL_VERSION}
            )
            websocket.receive_json()
            websocket.send_json(
                {
                    "type": "route.catalog.replace",
                    "revision": route_catalog_revision([manifest]),
                    "routes": [manifest],
                }
            )
            rejection = websocket.receive_json()
        native = client.post("/run_sse")

    assert rejection["type"] == "route.catalog.nack"
    assert "reserved route path" in rejection["error"]
    assert native.json() == {"native": True}


def test_registered_route_returns_503_after_provider_disconnects() -> None:
    app = FastAPI()
    mount_studio_route_host(app=app, enabled=True)
    manifest = _manifest()
    revision = route_catalog_revision([manifest])

    with TestClient(app) as client:
        with client.websocket_connect("/__studio/routes/v1/channel") as websocket:
            websocket.send_json(
                {"type": "channel.hello", "protocol": ROUTE_PROTOCOL_VERSION}
            )
            websocket.receive_json()
            websocket.send_json(
                {
                    "type": "route.catalog.replace",
                    "revision": revision,
                    "routes": [manifest],
                }
            )
            websocket.receive_json()
        response = client.get("/print_hello")

    assert response.status_code == 503
    assert response.json() == {"detail": "studio_route_provider_offline"}


def test_dynamic_dispatcher_stays_inside_existing_authentication_middleware() -> None:
    app = FastAPI()

    @app.middleware("http")
    async def require_test_identity(request: Any, call_next: Any):
        if request.headers.get("x-test-identity") != "verified":
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)

    mount_studio_route_host(app=app, enabled=True)
    manifest = _manifest()
    revision = route_catalog_revision([manifest])

    with TestClient(app) as client:
        with client.websocket_connect("/__studio/routes/v1/channel") as websocket:
            websocket.send_json(
                {"type": "channel.hello", "protocol": ROUTE_PROTOCOL_VERSION}
            )
            websocket.receive_json()
            websocket.send_json(
                {
                    "type": "route.catalog.replace",
                    "revision": revision,
                    "routes": [manifest],
                }
            )
            websocket.receive_json()
        unauthenticated = client.get("/print_hello")
        authenticated = client.get(
            "/print_hello",
            headers={"x-test-identity": "verified"},
        )

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 503
