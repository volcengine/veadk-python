"""Immutable Studio image selection and trusted registry protocol checks."""

import asyncio
import copy
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from veadk.integrations.mpa.managed import image_snapshot as snapshots
from veadk.integrations.mpa.managed import service
from veadk.integrations.mpa.managed.config import Managed, Profile, Runtime, Worker
from veadk.integrations.mpa.managed.database import DeploymentError

HOST = "agentkit-platform-123-ap-southeast-1.cr.bytepluses.com"
IMAGE = f"{HOST}/mpa/worker:latest"
MEDIA = "application/vnd.oci.image.manifest.v1+json"
BODY = json.dumps({"schemaVersion": 2, "mediaType": MEDIA, "config": {}}).encode()
DIGEST = "sha256:" + hashlib.sha256(BODY).hexdigest()
PINNED = IMAGE.removesuffix("latest") + "mpa-sha256-" + DIGEST[7:]
SELECTION = {"digest": DIGEST, "image": PINNED}


class Response:
    def __init__(self, status=200, body=BODY, headers=None):
        self.status_code = status
        self.body = body
        self.headers = {
            "Content-Type": MEDIA,
            "Docker-Content-Digest": "sha256:" + hashlib.sha256(body).hexdigest(),
            **(headers or {}),
        }
        self.closed = False

    def iter_content(self, chunk_size):
        yield self.body

    def close(self):
        self.closed = True


def cloud(provider="byteplus"):
    return SimpleNamespace(
        provider=provider,
        region="ap-southeast-1",
        _credentials=lambda: SimpleNamespace(
            access_key_id="test-ak",
            secret_access_key="test-sk",
            session_token="test-sts",
        ),
    )


def http(monkeypatch, *responses):
    session = Mock(headers={})
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    session.request.side_effect = responses
    monkeypatch.setattr(snapshots.requests, "Session", lambda: session)
    factory = Mock()
    factory.return_value._get_authorization_token.return_value = ("user", "password", 0)
    monkeypatch.setattr(snapshots, "VeCR", factory)
    return session, factory


def test_publish_preserves_bytes_and_rechecks_digest(monkeypatch):
    session, factory = http(
        monkeypatch, Response(), Response(404), Response(201), Response()
    )
    assert snapshots.snapshot_image(IMAGE, cloud()) == SELECTION
    assert session.request.call_args_list[2].kwargs["data"] == BODY
    assert all(
        c.kwargs["allow_redirects"] is False for c in session.request.call_args_list
    )
    assert factory.call_args.kwargs["session_token"] == "test-sts"
    factory.return_value._get_authorization_token.assert_called_once_with(
        "agentkit-platform-123"
    )
    assert session.request.call_args_list[2].args[1].endswith(PINNED.split(":")[-1])


def test_existing_snapshot_is_verified_without_overwrite(monkeypatch):
    session, _ = http(monkeypatch, Response(), Response())
    assert snapshots.snapshot_image(IMAGE, cloud()) == SELECTION
    assert [c.args[0] for c in session.request.call_args_list] == ["GET", "GET"]


def test_retry_reads_only_pinned_reference(monkeypatch):
    session, _ = http(monkeypatch, Response())
    assert snapshots.snapshot_image(IMAGE, cloud(), selection=SELECTION) == SELECTION
    assert len(session.request.call_args_list) == 1
    assert not session.request.call_args.args[1].endswith(":latest")


def test_bearer_challenge_is_restricted_and_authorization_replaced(monkeypatch):
    challenge = Response(
        401,
        headers={
            "WWW-Authenticate": f'Bearer realm="https://{HOST}/service/token",service="registry"'
        },
    )
    token = Response(body=b'{"token":"test-bearer"}')
    session, _ = http(monkeypatch, challenge, token, Response(), Response())
    assert snapshots.snapshot_image(IMAGE, cloud()) == SELECTION
    assert session.auth is None
    assert session.headers["Authorization"] == "Bearer test-bearer"
    assert (
        session.request.call_args_list[1].kwargs["params"]["scope"]
        == "repository:mpa/worker:pull,push"
    )
    assert challenge.closed


@pytest.mark.parametrize(
    "realm",
    [
        "http://" + HOST,
        "https://evil.test",
        "https://user@" + HOST,
        "https://" + HOST + ":444",
    ],
)
def test_challenge_cannot_forward_credentials(monkeypatch, realm):
    session, _ = http(
        monkeypatch,
        Response(401, headers={"WWW-Authenticate": f'Bearer realm="{realm}"'}),
    )
    with pytest.raises(DeploymentError):
        snapshots.snapshot_image(IMAGE, cloud())
    assert len(session.request.call_args_list) == 1


@pytest.mark.parametrize(
    "image,provider",
    [
        ("evil.test/mpa:latest", "byteplus"),
        (IMAGE, "volcengine"),
        ("https://" + IMAGE, "byteplus"),
        (IMAGE.replace("/mpa/", "/x/../"), "byteplus"),
    ],
)
def test_untrusted_reference_rejected_before_credentials(monkeypatch, image, provider):
    session, factory = http(monkeypatch)
    with pytest.raises(DeploymentError):
        snapshots.snapshot_image(image, cloud(provider))
    factory.assert_not_called()
    session.request.assert_not_called()


@pytest.mark.parametrize(
    "responses",
    [
        [Response(403)],
        [Response(headers={"Docker-Content-Digest": "sha256:" + "0" * 64})],
        [Response(headers={"Content-Type": "text/html"})],
        [Response(body=b"not-json")],
        [Response(body=b"[]")],
        [Response(body=b'{"schemaVersion":1}')],
        [Response(body=b"x" * (1024 * 1024 + 1))],
        [Response(), Response(body=b'{"schemaVersion":2,"config":{"other":true}}')],
        [Response(), Response(404), Response(403)],
        [Response(), Response(404), Response(201), Response(404)],
        [requests.Timeout("sensitive-url")],
        [Response(401)],
        [
            Response(
                401,
                headers={"WWW-Authenticate": f'Bearer realm="https://{HOST}/token"'},
            ),
            Response(body=b"{}"),
        ],
    ],
)
def test_invalid_registry_responses_fail_closed_and_redact(monkeypatch, responses):
    http(monkeypatch, *responses)
    with pytest.raises(DeploymentError) as error:
        snapshots.snapshot_image(IMAGE, cloud())
    assert "sensitive-url" not in str(error.value)
    assert "test-sk" not in str(error.value)


@pytest.mark.parametrize(
    "selection",
    [{}, {"digest": "bad", "image": PINNED}, {"digest": DIGEST, "image": IMAGE}],
)
def test_invalid_saved_selection_does_not_contact_registry(monkeypatch, selection):
    session, _ = http(monkeypatch)
    with pytest.raises(DeploymentError):
        snapshots.snapshot_image(IMAGE, cloud(), selection=selection)
    session.request.assert_not_called()


class Entry:
    def __init__(self, row=None):
        self.row = copy.deepcopy(row or {})
        self.saves = 0

    async def read(self):
        return copy.deepcopy(self.row)

    async def save(self, row):
        self.row = copy.deepcopy(row)
        self.saves += 1


def profile():
    return Profile(
        region="ap-southeast-1",
        managed=Managed(
            version=1, runtime=Runtime(image=IMAGE), worker=Worker(image=IMAGE)
        ),
        values={"cloud_provider": "byteplus"},
        template=None,
        admin_url="",
        shared_url="",
    )


def test_selection_is_persisted_and_retry_does_not_resolve_latest(monkeypatch):
    calls = []

    def resolve(image, cloud, *, selection=None):
        calls.append(selection)
        return dict(SELECTION) if selection is None else selection

    monkeypatch.setattr(snapshots, "snapshot_image", resolve)
    entry = Entry({"studio_owner": "owner"})
    first = asyncio.run(snapshots.pin_studio_images(profile(), entry, cloud()))
    assert first.managed.runtime.image == PINNED
    assert first.managed.worker.image == PINNED
    assert profile().managed.worker.image == IMAGE
    assert entry.row["studio_owner"] == "owner"
    assert entry.saves == 1
    second = asyncio.run(snapshots.pin_studio_images(profile(), entry, cloud()))
    assert second == first
    assert calls == [None, None, SELECTION, SELECTION]
    assert entry.saves == 1


def test_changed_input_cannot_replace_persisted_choice(monkeypatch):
    monkeypatch.setattr(snapshots, "snapshot_image", lambda *a, **k: dict(SELECTION))
    entry = Entry()
    asyncio.run(snapshots.pin_studio_images(profile(), entry, cloud()))
    changed = profile()
    changed.managed.worker.image = IMAGE.replace("worker", "different")
    with pytest.raises(DeploymentError):
        asyncio.run(snapshots.pin_studio_images(changed, entry, cloud()))
    assert entry.saves == 1


@pytest.mark.parametrize(
    "field", ["worker_id", "worker_hash", "runtime_id", "request_hash", "pending"]
)
def test_old_unfinished_requests_are_not_silently_rewritten(field):
    with pytest.raises(DeploymentError):
        asyncio.run(
            snapshots.pin_studio_images(profile(), Entry({field: "existing"}), cloud())
        )


def test_fixed_tags_do_not_require_registry_permissions(monkeypatch):
    p = profile()
    p.managed.runtime.image = p.managed.worker.image = "registry.example/image:v1"
    resolve = Mock()
    monkeypatch.setattr(snapshots, "snapshot_image", resolve)
    assert asyncio.run(snapshots.pin_studio_images(p, Entry(), cloud())) is p
    resolve.assert_not_called()


def test_failure_and_cancellation_do_not_persist_partial_selection(monkeypatch):
    for error in [DeploymentError("failure"), asyncio.CancelledError()]:

        def resolve(*args, **kwargs):
            raise error

        monkeypatch.setattr(snapshots, "snapshot_image", resolve)
        entry = Entry()
        with pytest.raises(type(error)):
            asyncio.run(snapshots.pin_studio_images(profile(), entry, cloud()))
        assert entry.saves == 0


def test_saved_snapshot_digest_must_still_match(monkeypatch):
    http(monkeypatch, Response(body=b'{"schemaVersion":2,"config":{"changed":true}}'))
    with pytest.raises(DeploymentError):
        snapshots.snapshot_image(IMAGE, cloud(), selection=SELECTION)


def test_failed_token_exchange(monkeypatch):
    http(
        monkeypatch,
        Response(
            401, headers={"WWW-Authenticate": f'Bearer realm="https://{HOST}/token"'}
        ),
        Response(403),
    )
    with pytest.raises(DeploymentError):
        snapshots.snapshot_image(IMAGE, cloud())


@pytest.mark.parametrize(
    "saved",
    [
        "invalid",
        {},
        {"requested": {}, "selected": {}},
        {"requested": {"runtimeImage": IMAGE, "workerImage": IMAGE}, "selected": {}},
    ],
)
def test_corrupt_or_changed_saved_state_is_rejected(saved):
    with pytest.raises(DeploymentError):
        asyncio.run(
            snapshots.pin_studio_images(
                profile(), Entry({"image_snapshots": saved}), cloud()
            )
        )


@pytest.mark.parametrize("latest_key", ["runtimeImage", "workerImage"])
def test_only_latest_selection_is_changed(monkeypatch, latest_key):
    p = profile()
    if latest_key == "runtimeImage":
        p.managed.worker.image = "custom/worker:v1"
    else:
        p.managed.runtime.image = "custom/runtime:v1"
    monkeypatch.setattr(snapshots, "snapshot_image", lambda *a, **kw: dict(SELECTION))
    result = asyncio.run(snapshots.pin_studio_images(p, Entry(), cloud()))
    assert result.image_defaults()[latest_key] == PINNED
    other = "workerImage" if latest_key == "runtimeImage" else "runtimeImage"
    assert result.image_defaults()[other] == p.image_defaults()[other]


def test_domestic_provider_uses_its_own_registry_and_credentials(monkeypatch):
    image = IMAGE.replace("bytepluses.com", "volces.com")
    session, factory = http(monkeypatch, Response(), Response())
    result = snapshots.snapshot_image(image, cloud("volcengine"))
    assert result["image"].startswith(image.removesuffix("latest"))
    assert factory.call_args.kwargs["provider"] == "volcengine"
    assert "bytepluses.com" not in session.request.call_args.args[1]


def test_service_pins_images_under_lock_before_worker_and_runtime(monkeypatch):
    from unittest.mock import AsyncMock

    from tests.integrations.mpa_managed.test_agent_deployment import (
        Cloud,
        Databases,
        Registry,
        template,
    )

    async def run():
        entry = Registry()
        fake_cloud = Cloud(entry)
        p = profile()
        p.region = "cn-beijing"
        p.values = {"cloud_provider": "volcengine"}
        p.template = template()
        p.admin_url = "fake"
        p.shared_url = "postgresql://registry.example/shared"
        monkeypatch.setattr(service, "RuntimeCloud", lambda **kw: fake_cloud)
        monkeypatch.setattr(service, "AgentDeploymentRegistry", lambda url: entry)
        monkeypatch.setattr(
            service, "AgentDatabaseProvisioner", lambda **kw: Databases()
        )
        monkeypatch.setattr(service, "resolve_model_key", AsyncMock(return_value=p))
        monkeypatch.setattr(
            service,
            "ensure_workload_identity",
            AsyncMock(
                return_value=SimpleNamespace(
                    workload_pool_name="pool", workload_identity_name="identity"
                )
            ),
        )
        monkeypatch.setattr(
            snapshots, "snapshot_image", lambda *a, **kw: dict(SELECTION)
        )
        monkeypatch.setattr(
            service,
            "GatewayCloud",
            lambda _: SimpleNamespace(
                available_zones=AsyncMock(return_value=fake_cloud.network.zone_ids)
            ),
        )

        class Gateway:
            def __init__(self, **kw):
                pass

            async def ensure(self, **kw):
                return {"gateway_id": "gw-one"}

        async def worker(locked_entry, cloud, options, **kw):
            assert entry.mutex.locked()
            assert options.image == PINNED
            assert (
                locked_entry.row["image_snapshots"]["selected"]["workerImage"]
                == SELECTION
            )
            return "t-one"

        monkeypatch.setattr(service, "SharedAPIGService", Gateway)
        monkeypatch.setattr(service, "ensure_worker", worker)
        result = await service.provision(
            p,
            agent_id="mi-123456789abc",
            owner="owner-hash",
            studio_runtime_owner="studio-user",
            runtime_name="snapshot-agent",
        )
        assert result["runtime_id"] == "r-agent"
        assert fake_cloud.creates[0]["ArtifactUrl"] == PINNED
        assert fake_cloud.creates[0]["ToolId"] == "t-one"
        assert p.managed.worker.image == IMAGE

    asyncio.run(run())
