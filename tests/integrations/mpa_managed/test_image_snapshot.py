"""Read-only Studio image discovery and trusted registry protocol checks."""

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
BASE = f"https://{HOST}/v2/mpa/worker/"


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


def tags(*names, link="", body=None):
    return Response(
        body=body if body is not None else json.dumps({"tags": list(names)}).encode(),
        headers={"Content-Type": "application/json", "Link": link},
    )


def cloud(provider="byteplus"):
    return SimpleNamespace(
        provider=provider,
        region="ap-southeast-1",
        _credentials=Mock(
            side_effect=AssertionError("Cloud credentials must not be read")
        ),
    )


def http(monkeypatch, *responses):
    session = Mock(headers={})
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    session.request.side_effect = responses
    monkeypatch.setattr(snapshots.requests, "Session", lambda: session)
    return session


def test_anonymous_selection_never_reads_credentials_or_writes(monkeypatch):
    responses = [Response(), tags("release-v1"), Response()]
    session = http(monkeypatch, *responses)
    identity = cloud()
    expected = {"digest": DIGEST, "image": IMAGE.removesuffix("latest") + "release-v1"}
    assert snapshots.snapshot_image(IMAGE, identity) == expected
    identity._credentials.assert_not_called()
    assert session.trust_env is False
    assert session.auth is None
    assert "Authorization" not in session.headers
    assert [c.args[0] for c in session.request.call_args_list] == ["GET"] * 3
    assert all(
        c.kwargs["allow_redirects"] is False for c in session.request.call_args_list
    )
    assert all(
        0 < c.kwargs["timeout"][0] <= 10 and 0 < c.kwargs["timeout"][1] <= 30
        for c in session.request.call_args_list
    )
    assert all(r.closed for r in responses)


def test_prefer_existing_digest_named_tag_without_publication(monkeypatch):
    session = http(
        monkeypatch, Response(), tags("z-release", PINNED.rsplit(":", 1)[1]), Response()
    )
    assert snapshots.snapshot_image(IMAGE, cloud()) == SELECTION
    assert (
        session.request.call_args.args[1]
        == BASE + "manifests/" + PINNED.rsplit(":", 1)[1]
    )
    assert [c.args[0] for c in session.request.call_args_list] == ["GET"] * 3


def test_missing_and_nonmatching_candidates_are_skipped_in_stable_order(monkeypatch):
    session = http(
        monkeypatch,
        Response(),
        tags("release-v1", "y-other", "latest", "z-deleted", "release-v1"),
        Response(404),
        Response(body=b'{"schemaVersion":2,"config":{"other":true}}'),
        Response(),
    )
    result = snapshots.snapshot_image(IMAGE, cloud())
    assert result["image"].endswith(":release-v1")
    assert [
        c.args[1].rsplit("/", 1)[1] for c in session.request.call_args_list[2:]
    ] == ["z-deleted", "y-other", "release-v1"]


def test_all_pages_are_read_before_tag_selection(monkeypatch):
    next_path = "/v2/mpa/worker/tags/list?n=100&last=release-v1"
    session = http(
        monkeypatch,
        Response(),
        tags("release-v1", link=f'<{next_path}>; rel="next"'),
        tags("z-release"),
        Response(),
    )
    result = snapshots.snapshot_image(IMAGE, cloud())
    assert result["image"].endswith(":z-release")
    assert session.request.call_args_list[2].args[1] == "https://" + HOST + next_path


@pytest.mark.parametrize("saved_tag", ["release-v1", PINNED.rsplit(":", 1)[1]])
def test_retry_reads_only_saved_reference(monkeypatch, saved_tag):
    session = http(monkeypatch, Response())
    saved = {"digest": DIGEST, "image": IMAGE.removesuffix("latest") + saved_tag}
    assert snapshots.snapshot_image(IMAGE, cloud(), selection=saved) == saved
    assert len(session.request.call_args_list) == 1
    assert session.request.call_args.args[1] == BASE + "manifests/" + saved_tag


@pytest.mark.parametrize("token_key", ["token", "access_token"])
def test_bearer_challenge_requests_anonymous_pull_only(monkeypatch, token_key):
    challenge = Response(
        401,
        headers={
            "WWW-Authenticate": f'Bearer realm="https://{HOST}/service/token",service="registry"'
        },
    )
    token = Response(body=json.dumps({token_key: "test-bearer"}).encode())
    session = http(
        monkeypatch, challenge, token, Response(), tags("release-v1"), Response()
    )
    assert snapshots.snapshot_image(IMAGE, cloud())["image"].endswith(":release-v1")
    assert session.auth is None
    assert session.headers["Authorization"] == "Bearer test-bearer"
    assert session.request.call_args_list[1].kwargs["params"] == {
        "service": "registry",
        "scope": "repository:mpa/worker:pull",
    }
    assert challenge.closed and token.closed


@pytest.mark.parametrize(
    "realm",
    [
        "http://" + HOST,
        "https://evil.test",
        "https://user@" + HOST,
        "https://" + HOST + ":444",
        "https://user:pass@" + HOST,
    ],
)
def test_untrusted_authentication_challenges_are_rejected(monkeypatch, realm):
    session = http(
        monkeypatch,
        Response(401, headers={"WWW-Authenticate": f'Bearer realm="{realm}"'}),
    )
    with pytest.raises(DeploymentError):
        snapshots.snapshot_image(IMAGE, cloud())
    assert len(session.request.call_args_list) == 1


@pytest.mark.parametrize(
    "link",
    [
        '<https://evil.test/v2/mpa/worker/tags/list?n=100>; rel="next"',
        f'<http://{HOST}/v2/mpa/worker/tags/list?n=100>; rel="next"',
        f'<https://user@{HOST}/v2/mpa/worker/tags/list?n=100>; rel="next"',
        f'<https://{HOST}:444/v2/mpa/worker/tags/list?n=100>; rel="next"',
        '</v2/another/worker/tags/list?n=100>; rel="next"',
        '</v2/mpa/worker/tags/list?n=100#token>; rel="next"',
        '</v2/mpa/worker/tags/list?n=100&secret=x>; rel="next"',
        '</v2/mpa/worker/tags/list?n=100&n=1>; rel="next"',
        '</v2/mpa/worker/tags/list?n=0>; rel="next"',
        '</v2/mpa/worker/tags/list?n=101>; rel="next"',
        '</v2/mpa/worker/tags/list?n=bad>; rel="next"',
        '</v2/mpa/worker/tags/list?last=../evil>; rel="next"',
        '</v2/mpa/worker/tags/list?last=>; rel="next"',
        '</v2/mpa/worker/tags/list?n=100>; rel="next"',
        '</v2/mpa/worker/tags/list?n=1>; rel="next", </v2/mpa/worker/tags/list?n=2>; rel="next"',
        "invalid",
    ],
)
def test_unsafe_invalid_and_cyclic_pagination_fail_before_following(monkeypatch, link):
    session = http(monkeypatch, Response(), tags("release-v1", link=link))
    with pytest.raises(DeploymentError):
        snapshots.snapshot_image(IMAGE, cloud())
    assert len(session.request.call_args_list) == 2


@pytest.mark.parametrize("limit", ["_MAX_PAGES", "_MAX_TAGS"])
def test_enumeration_limits_fail_without_partial_selection(monkeypatch, limit):
    monkeypatch.setattr(snapshots, limit, 1)
    session = http(
        monkeypatch,
        Response(),
        tags("v1", "v2", link='</v2/mpa/worker/tags/list?last=v2>; rel="next"'),
    )
    with pytest.raises(DeploymentError):
        snapshots.snapshot_image(IMAGE, cloud())
    assert len(session.request.call_args_list) == 2


@pytest.mark.parametrize(
    "body", [b"{}", b'{"tags":null}', b'{"tags":[]}', b'{"tags":["latest"]}']
)
def test_no_matching_tag_fails_without_writes(monkeypatch, body):
    session = http(monkeypatch, Response(), tags(body=body))
    with pytest.raises(DeploymentError, match="No existing version tag matches latest"):
        snapshots.snapshot_image(IMAGE, cloud())
    assert [c.args[0] for c in session.request.call_args_list] == ["GET", "GET"]


@pytest.mark.parametrize(
    "body",
    [
        b"[]",
        b"not-json",
        b'{"tags":"v1"}',
        b'{"tags":[1]}',
        b'{"tags":["../bad"]}',
        b'{"tags":["bad:tag"]}',
    ],
)
def test_invalid_tag_lists_fail_closed(monkeypatch, body):
    session = http(monkeypatch, Response(), tags(body=body))
    with pytest.raises(DeploymentError):
        snapshots.snapshot_image(IMAGE, cloud())
    assert len(session.request.call_args_list) == 2


def test_no_candidate_with_matching_digest_fails(monkeypatch):
    session = http(
        monkeypatch,
        Response(),
        tags("v1"),
        Response(body=b'{"schemaVersion":2,"different":true}'),
    )
    with pytest.raises(DeploymentError, match="No existing version tag matches latest"):
        snapshots.snapshot_image(IMAGE, cloud())
    assert len(session.request.call_args_list) == 3


@pytest.mark.parametrize(
    "responses",
    [
        [Response(403)],
        [Response(headers={"Docker-Content-Digest": "sha256:" + "0" * 64})],
        [Response(headers={"Content-Type": "text/html"})],
        [Response(body=b"not-json")],
        [Response(body=b"[]")],
        [Response(body=b'{"schemaVersion":1}')],
        [Response(body=b'{"schemaVersion":2,"mediaType":"wrong"}')],
        [Response(body=b"x" * (1024 * 1024 + 1))],
        [Response(), Response(403)],
        [Response(), tags("v1"), Response(403)],
        [Response(), tags("v1"), Response(404)],
        [requests.Timeout("sensitive-url")],
        [Response(401)],
        [
            Response(
                401,
                headers={"WWW-Authenticate": f'Bearer realm="https://{HOST}/token"'},
            ),
            Response(403),
        ],
        [
            Response(
                401,
                headers={"WWW-Authenticate": f'Bearer realm="https://{HOST}/token"'},
            ),
            Response(body=b"{}"),
        ],
        [
            Response(
                401,
                headers={"WWW-Authenticate": f'Bearer realm="https://{HOST}/token"'},
            ),
            Response(body=b'{"token":" "}'),
        ],
        [
            Response(
                401,
                headers={"WWW-Authenticate": f'Bearer realm="https://{HOST}/token"'},
            ),
            Response(body=b'{"token":"a"}'),
            Response(401),
        ],
    ],
)
def test_invalid_registry_responses_fail_closed_and_redact(monkeypatch, responses):
    session = http(monkeypatch, *responses)
    with pytest.raises(DeploymentError) as error:
        snapshots.snapshot_image(IMAGE, cloud())
    assert "sensitive-url" not in str(error.value)
    assert all(c.args[0] == "GET" for c in session.request.call_args_list)


@pytest.mark.parametrize("times", [[0, 121], [0, 0, 121]])
def test_deadline_is_enforced_before_requests_and_during_response_read(
    monkeypatch, times
):
    monkeypatch.setattr(snapshots.time, "monotonic", Mock(side_effect=times))
    response = Response()
    session = http(monkeypatch, response)
    with pytest.raises(DeploymentError, match="budget"):
        snapshots.snapshot_image(IMAGE, cloud())
    if len(times) == 2:
        session.request.assert_not_called()
    else:
        assert response.closed


@pytest.mark.parametrize(
    "image,provider",
    [
        ("evil.test/mpa:latest", "byteplus"),
        (IMAGE, "volcengine"),
        (IMAGE, "unknown"),
        ("https://" + IMAGE, "byteplus"),
        (IMAGE.replace("/mpa/", "/x/../"), "byteplus"),
    ],
)
def test_untrusted_reference_rejected_before_network(monkeypatch, image, provider):
    session = http(monkeypatch)
    with pytest.raises(DeploymentError):
        snapshots.snapshot_image(image, cloud(provider))
    session.request.assert_not_called()


@pytest.mark.parametrize(
    "selection",
    [
        "bad",
        {},
        {"digest": "bad", "image": PINNED},
        {"digest": DIGEST, "image": IMAGE},
        {"digest": DIGEST, "image": IMAGE.removesuffix("latest") + "../bad"},
        {"digest": DIGEST, "image": PINNED.replace(HOST, "evil.test")},
        {"digest": DIGEST, "image": 1},
        {"digest": None, "image": PINNED},
    ],
)
def test_invalid_saved_selection_does_not_contact_registry(monkeypatch, selection):
    session = http(monkeypatch)
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


def test_domestic_provider_uses_anonymous_registry_reads(monkeypatch):
    image = IMAGE.replace("bytepluses.com", "volces.com")
    session = http(monkeypatch, Response(), tags("release-v1"), Response())
    identity = cloud("volcengine")
    result = snapshots.snapshot_image(image, identity)
    assert result["image"] == image.removesuffix("latest") + "release-v1"
    identity._credentials.assert_not_called()
    assert all(
        "bytepluses.com" not in c.args[1] for c in session.request.call_args_list
    )


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
