from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from frontend.server.knowledge.gateways import (
    DOCUMENT_FORMAT_UNSUPPORTED,
    DOCUMENT_NOT_FOUND,
    PROVIDER_ASSOCIATION_INVALID,
    SdkAgentKitKnowledgeGateway,
    VikingDocumentGateway,
    VikingKnowledgeBaseProvisioner,
    _connection_credentials,
    _viking_host,
    build_viking_document_gateway_factory,
)
from frontend.server.knowledge.models import (
    CreateDocumentBody,
    CreateKnowledgeBaseBody,
    UpdateKnowledgeBaseBody,
)
from frontend.server.knowledge.routes import mount_knowledge_routes
from frontend.server.knowledge.service import (
    KnowledgeAccessError,
    KnowledgeIdentity,
    KnowledgeRecord,
    KnowledgeService,
    ProviderConnection,
    ProvisionedKnowledgeBase,
    decode_owned_description,
)

SIGNING_KEY = b"test-only-knowledge-signing-key"


class FakeAgentKitGateway:
    def __init__(self, records: list[KnowledgeRecord]) -> None:
        self.records = {item.id: item for item in records}
        self.added_description = ""
        self.updated_description = ""
        self.connection_calls: list[tuple[str, str]] = []
        self.add_calls: list[dict[str, str]] = []

    def list(self, *, region, project_name, next_token, max_results):
        del region, project_name, next_token
        return list(self.records.values())[:max_results], ""

    def get(self, knowledge_id: str, *, region: str) -> KnowledgeRecord:
        del region
        try:
            return self.records[knowledge_id]
        except KeyError as error:
            raise KnowledgeAccessError("知识库不存在。", status_code=404) from error

    def add(
        self,
        body,
        *,
        description: str,
        region: str,
        provider_knowledge_id: str | None = None,
        project_name: str | None = None,
    ) -> str:
        resolved_provider_id = provider_knowledge_id or getattr(
            body,
            "provider_knowledge_id",
            "",
        )
        resolved_project_name = (
            project_name
            or getattr(
                body,
                "project_name",
                "",
            )
            or "default"
        )
        self.add_calls.append(
            {
                "provider_knowledge_id": resolved_provider_id,
                "project_name": resolved_project_name,
                "region": region,
            }
        )
        self.added_description = description
        item = KnowledgeRecord(
            id="kb-new",
            name=body.name,
            description=description,
            provider_type="VIKINGDB_KNOWLEDGE",
            provider_knowledge_id=resolved_provider_id,
            project_name=resolved_project_name,
            region=region,
        )
        self.records[item.id] = item
        return item.id

    def update_description(
        self, knowledge_id: str, *, description: str, region: str
    ) -> None:
        del region
        self.updated_description = description
        self.records[knowledge_id] = replace(
            self.records[knowledge_id], description=description
        )

    def delete(self, knowledge_id: str, *, region: str) -> None:
        del region
        self.records.pop(knowledge_id)

    def connection(self, knowledge_id: str, *, region: str) -> ProviderConnection:
        self.connection_calls.append((knowledge_id, region))
        return ProviderConnection(
            provider_type="VIKINGDB_KNOWLEDGE",
            provider_knowledge_id=self.records[knowledge_id].provider_knowledge_id,
            base_url="https://knowledge.example.com",
            region=region,
        )


class FakeKnowledgeProvisioner:
    def __init__(self) -> None:
        self.created: list[dict[str, str]] = []
        self.deleted: list[dict[str, str]] = []
        self.fail_regions: set[str] = set()

    def create(
        self,
        *,
        name: str,
        description: str,
        project_name: str,
        region: str,
    ) -> ProvisionedKnowledgeBase:
        self.created.append(
            {
                "name": name,
                "description": description,
                "project_name": project_name,
                "region": region,
            }
        )
        if region in self.fail_regions:
            raise RuntimeError(f"provision failed in {region}")
        return ProvisionedKnowledgeBase(
            provider_knowledge_id=f"provider-{region}",
            name=name,
        )

    def delete(
        self,
        *,
        name: str,
        provider_knowledge_id: str,
        project_name: str,
        region: str,
    ) -> None:
        self.deleted.append(
            {
                "name": name,
                "provider_knowledge_id": provider_knowledge_id,
                "project_name": project_name,
                "region": region,
            }
        )


class FakeDocumentGateway:
    def __init__(self) -> None:
        self.created: list[CreateDocumentBody] = []
        self.previewed: list[tuple[str, int, int]] = []

    def list(self, *, offset: int, limit: int, document_type: str | None):
        del offset, limit, document_type
        return [], False

    def get(self, document_id: str):
        return {"id": document_id, "name": "guide.pdf", "type": "pdf"}

    def preview(self, document_id: str, *, offset: int, limit: int):
        self.previewed.append((document_id, offset, limit))
        return [
            {
                "id": "point-1",
                "title": "Overview",
                "content": "Hello",
                "attachmentUrl": "",
                "attachmentType": "",
                "attachment": None,
                "tableFields": None,
            }
        ], True

    def create(self, body: CreateDocumentBody):
        self.created.append(body)
        return {"id": "doc-1"}

    def update_metadata(self, document_id: str, metadata):
        return {"id": document_id, "metadata": metadata}

    def delete(self, document_id: str) -> None:
        del document_id


def owned_record(
    knowledge_id: str,
    owner_id: str,
    owner_label: str,
) -> KnowledgeRecord:
    from frontend.server.knowledge.service import encode_owned_description

    return KnowledgeRecord(
        id=knowledge_id,
        name=knowledge_id,
        description=encode_owned_description(
            "visible description",
            KnowledgeIdentity(owner_id=owner_id, owner_label=owner_label),
            signing_key=SIGNING_KEY,
            knowledge_id=knowledge_id,
            provider_type="VIKINGDB_KNOWLEDGE",
            provider_knowledge_id=f"provider-{knowledge_id}",
            project_name="default",
            region="cn-beijing",
        ),
        provider_type="VIKINGDB_KNOWLEDGE",
        provider_knowledge_id=f"provider-{knowledge_id}",
        project_name="default",
        region="cn-beijing",
    )


def service_for(records: list[KnowledgeRecord]):
    agentkit = FakeAgentKitGateway(records)
    documents = FakeDocumentGateway()

    def document_gateway_factory(
        record: KnowledgeRecord,
        connection: ProviderConnection,
    ) -> FakeDocumentGateway:
        del record, connection
        return documents

    service = KnowledgeService(
        agentkit,
        document_gateway_factory,
        signing_key=SIGNING_KEY,
    )
    return service, agentkit, documents


def auto_create_service(
    agentkit: FakeAgentKitGateway | None = None,
    provisioner: FakeKnowledgeProvisioner | None = None,
) -> tuple[KnowledgeService, FakeAgentKitGateway, FakeKnowledgeProvisioner]:
    resolved_agentkit = agentkit or FakeAgentKitGateway([])
    resolved_provisioner = provisioner or FakeKnowledgeProvisioner()
    service = KnowledgeService(
        resolved_agentkit,
        lambda record, connection: FakeDocumentGateway(),
        signing_key=SIGNING_KEY,
        provisioner=resolved_provisioner,
    )
    return service, resolved_agentkit, resolved_provisioner


def test_create_route_accepts_name_and_description_only() -> None:
    service, agentkit, provisioner = auto_create_service()
    app = FastAPI()
    mount_knowledge_routes(
        app,
        service=service,
        identity_resolver=lambda request: KnowledgeIdentity(
            "user-1",
            "Alice",
            can_bind_provider=True,
        ),
        region_resolver=lambda value: value or "cn-beijing",
        region_candidates_resolver=lambda: ("cn-beijing", "cn-shanghai"),
    )

    response = TestClient(app).post(
        "/web/knowledge-bases",
        json={"name": "support", "description": "Team docs"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "support"
    assert provisioner.created == [
        {
            "name": "support",
            "description": "Team docs",
            "project_name": "default",
            "region": "cn-beijing",
        }
    ]
    assert agentkit.add_calls[0]["provider_knowledge_id"] == ("provider-cn-beijing")


def test_create_passes_provisioned_provider_id_to_agentkit() -> None:
    service, agentkit, provisioner = auto_create_service()
    body = CreateKnowledgeBaseBody.model_validate(
        {"name": "support", "description": "Team docs"}
    )

    result = service.create(
        body,
        identity=KnowledgeIdentity(
            "user-1",
            "Alice",
            can_bind_provider=True,
        ),
        region="cn-beijing",
    )

    assert provisioner.created[0]["region"] == "cn-beijing"
    assert agentkit.add_calls == [
        {
            "provider_knowledge_id": "provider-cn-beijing",
            "project_name": "default",
            "region": "cn-beijing",
        }
    ]
    assert result.provider_knowledge_id == "provider-cn-beijing"


@pytest.mark.parametrize("failure_stage", ["add", "get", "update"])
def test_create_cleans_up_new_provider_when_agentkit_step_fails(
    failure_stage: str,
) -> None:
    class FailingAgentKitGateway(FakeAgentKitGateway):
        def add(self, body, **kwargs) -> str:
            if failure_stage == "add":
                raise RuntimeError("AgentKit add failed")
            return super().add(body, **kwargs)

        def get(self, knowledge_id: str, *, region: str) -> KnowledgeRecord:
            if failure_stage == "get":
                raise RuntimeError("AgentKit get failed")
            return super().get(knowledge_id, region=region)

        def update_description(
            self,
            knowledge_id: str,
            *,
            description: str,
            region: str,
        ) -> None:
            if failure_stage == "update":
                raise RuntimeError("AgentKit update failed")
            super().update_description(
                knowledge_id,
                description=description,
                region=region,
            )

    agentkit = FailingAgentKitGateway([])
    service, _, provisioner = auto_create_service(agentkit=agentkit)
    body = CreateKnowledgeBaseBody.model_validate(
        {"name": "support", "description": "Team docs"}
    )

    with pytest.raises(RuntimeError, match=f"AgentKit {failure_stage} failed"):
        service.create(
            body,
            identity=KnowledgeIdentity(
                "user-1",
                "Alice",
                can_bind_provider=True,
            ),
            region="cn-beijing",
        )

    assert provisioner.deleted == [
        {
            "name": "support",
            "provider_knowledge_id": "provider-cn-beijing",
            "project_name": "default",
            "region": "cn-beijing",
        }
    ]
    if failure_stage in {"get", "update"}:
        assert agentkit.records == {}


def test_auto_create_tries_second_region_when_first_provision_fails() -> None:
    provisioner = FakeKnowledgeProvisioner()
    provisioner.fail_regions.add("cn-beijing")
    service, agentkit, _ = auto_create_service(provisioner=provisioner)
    app = FastAPI()
    mount_knowledge_routes(
        app,
        service=service,
        identity_resolver=lambda request: KnowledgeIdentity(
            "user-1",
            "Alice",
            can_bind_provider=True,
        ),
        region_resolver=lambda value: value or "cn-beijing",
        region_candidates_resolver=lambda: ("cn-beijing", "cn-shanghai"),
    )

    response = TestClient(app).post(
        "/web/knowledge-bases",
        json={"name": "support", "description": "Team docs"},
    )

    assert response.status_code == 201
    assert [item["region"] for item in provisioner.created] == [
        "cn-beijing",
        "cn-shanghai",
    ]
    assert agentkit.add_calls == [
        {
            "provider_knowledge_id": "provider-cn-shanghai",
            "project_name": "default",
            "region": "cn-shanghai",
        }
    ]
    assert response.json()["region"] == "cn-shanghai"


def test_create_injects_owner_envelope_and_ignores_client_owner_fields() -> None:
    service, agentkit, _ = auto_create_service()
    identity = KnowledgeIdentity(
        owner_id="user-1",
        owner_label="Alice",
        can_bind_provider=True,
    )
    body = CreateKnowledgeBaseBody.model_validate(
        {
            "name": "support",
            "description": "Team docs",
            "ownerId": "attacker",
            "ownerLabel": "Mallory",
        }
    )

    result = service.create(body, identity=identity, region="cn-beijing")

    record = agentkit.records["kb-new"]
    visible, metadata = decode_owned_description(
        agentkit.updated_description,
        signing_key=SIGNING_KEY,
        knowledge_id=record.id,
        provider_type=record.provider_type,
        provider_knowledge_id=record.provider_knowledge_id,
        project_name=record.project_name,
        region=record.region,
    )
    assert visible == "Team docs"
    assert metadata == {
        "veadk:author": "user-1",
        "veadk:knowledge-id": "kb-new",
        "veadk:managed": "true",
        "veadk:owner": "user-1",
        "veadk:project": "default",
        "veadk:provider-id": "provider-cn-beijing",
        "veadk:provider-managed": "true",
        "veadk:provider-type": "VIKINGDB_KNOWLEDGE",
        "veadk:region": "cn-beijing",
    }
    assert result.owner_id == "user-1"
    assert result.description == "Team docs"


def test_list_filters_regular_users_and_admin_sees_every_owner() -> None:
    service, _, _ = service_for(
        [
            owned_record("kb-a", "user-1", "Alice"),
            owned_record("kb-b", "user-2", "Bob"),
            KnowledgeRecord(
                id="kb-legacy",
                name="legacy",
                description="unowned",
                provider_type="VIKINGDB_KNOWLEDGE",
                provider_knowledge_id="provider-legacy",
                project_name="default",
                region="cn-beijing",
            ),
        ]
    )

    regular = service.list(
        identity=KnowledgeIdentity("user-1", "Alice"),
        region="cn-beijing",
        project_name=None,
        next_token=None,
        page_size=30,
    )
    admin = service.list(
        identity=KnowledgeIdentity("admin", "Admin", is_admin=True),
        region="cn-beijing",
        project_name=None,
        next_token=None,
        page_size=30,
    )

    assert [item.id for item in regular.items] == ["kb-a"]
    assert [item.id for item in admin.items] == ["kb-a", "kb-b", "kb-legacy"]
    assert all(item.can_manage for item in admin.items)


def test_update_preserves_server_owner_envelope() -> None:
    service, agentkit, _ = service_for([owned_record("kb-a", "user-1", "Alice")])

    result = service.update(
        "kb-a",
        UpdateKnowledgeBaseBody.model_validate(
            {"description": "Changed", "ownerId": "user-2"}
        ),
        identity=KnowledgeIdentity("user-1", "Alice Updated"),
        region="cn-beijing",
    )

    record = agentkit.records["kb-a"]
    visible, metadata = decode_owned_description(
        agentkit.updated_description,
        signing_key=SIGNING_KEY,
        knowledge_id=record.id,
        provider_type=record.provider_type,
        provider_knowledge_id=record.provider_knowledge_id,
        project_name=record.project_name,
        region=record.region,
    )
    assert visible == "Changed"
    assert metadata["veadk:owner"] == "user-1"
    assert metadata["veadk:author"] == "user-1"
    assert result.description == "Changed"


@pytest.mark.parametrize("operation", ["get", "update", "delete"])
def test_cross_owner_operations_are_forbidden(operation: str) -> None:
    service, _, _ = service_for([owned_record("kb-a", "user-1", "Alice")])
    identity = KnowledgeIdentity("user-2", "Bob")

    with pytest.raises(KnowledgeAccessError) as captured:
        if operation == "get":
            service.get("kb-a", identity=identity, region="cn-beijing")
        elif operation == "update":
            service.update(
                "kb-a",
                UpdateKnowledgeBaseBody(description="no"),
                identity=identity,
                region="cn-beijing",
            )
        else:
            service.delete("kb-a", identity=identity, region="cn-beijing")

    assert captured.value.status_code == 403


def test_document_operation_fetches_agentkit_connection_before_provider() -> None:
    service, agentkit, documents = service_for(
        [owned_record("kb-a", "user-1", "Alice")]
    )
    body = CreateDocumentBody(
        source_type="url",
        name="Guide",
        document_type="pdf",
        url="https://example.com/guide.pdf",
        metadata={"department": "support"},
    )

    result = service.create_document(
        "kb-a",
        body,
        identity=KnowledgeIdentity("user-1", "Alice"),
        region="cn-beijing",
    )

    assert agentkit.connection_calls == [("kb-a", "cn-beijing")]
    assert documents.created == [body]
    assert result == {"id": "doc-1"}


def test_preview_route_returns_authorized_paginated_chunks() -> None:
    service, agentkit, documents = service_for(
        [owned_record("kb-a", "user-1", "Alice")]
    )
    app = FastAPI()
    mount_knowledge_routes(
        app,
        service=service,
        identity_resolver=lambda request: KnowledgeIdentity("user-1", "Alice"),
        region_resolver=lambda value: value or "cn-beijing",
    )

    response = TestClient(app).get(
        "/web/knowledge-bases/kb-a/documents/doc-1/preview"
        "?region=cn-beijing&offset=10&limit=20"
    )

    assert response.status_code == 200
    assert response.json() == {
        "document": {"id": "doc-1", "name": "guide.pdf", "type": "pdf"},
        "chunks": [
            {
                "id": "point-1",
                "title": "Overview",
                "content": "Hello",
                "attachmentUrl": "",
                "attachmentType": "",
                "attachment": None,
                "tableFields": None,
            }
        ],
        "offset": 10,
        "limit": 20,
        "hasMore": True,
    }
    assert agentkit.connection_calls == [("kb-a", "cn-beijing")]
    assert documents.previewed == [("doc-1", 10, 20)]


def test_preview_route_rejects_cross_owner_before_provider() -> None:
    service, agentkit, documents = service_for(
        [owned_record("kb-a", "user-1", "Alice")]
    )
    app = FastAPI()
    mount_knowledge_routes(
        app,
        service=service,
        identity_resolver=lambda request: KnowledgeIdentity("user-2", "Mallory"),
        region_resolver=lambda value: value or "cn-beijing",
    )

    response = TestClient(app).get("/web/knowledge-bases/kb-a/documents/doc-1/preview")

    assert response.status_code == 403
    assert agentkit.connection_calls == []
    assert documents.previewed == []


def test_routes_return_camel_case_and_distinguish_forbidden_from_missing() -> None:
    service, _, _ = service_for([owned_record("kb-a", "user-1", "Alice")])
    app = FastAPI()

    def identity(request: Request) -> KnowledgeIdentity:
        return KnowledgeIdentity(
            owner_id=request.headers.get("x-owner", "user-1"),
            owner_label="User",
        )

    mount_knowledge_routes(
        app,
        service=service,
        identity_resolver=identity,
        region_resolver=lambda value: value or "cn-beijing",
    )
    client = TestClient(app)

    listed = client.get("/web/knowledge-bases", headers={"x-owner": "user-1"})
    forbidden = client.delete(
        "/web/knowledge-bases/kb-a",
        headers={"x-owner": "user-2"},
    )
    missing = client.delete(
        "/web/knowledge-bases/kb-missing",
        headers={"x-owner": "user-1"},
    )

    assert listed.status_code == 200
    assert listed.json()["items"][0]["ownerId"] == "user-1"
    assert "owner_id" not in listed.json()["items"][0]
    assert forbidden.status_code == 403
    assert missing.status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "request_kwargs"),
    [
        ("GET", "/web/knowledge-bases", {}),
        (
            "POST",
            "/web/knowledge-bases",
            {
                "json": {
                    "name": "support",
                    "providerKnowledgeId": "provider-1",
                }
            },
        ),
        ("GET", "/web/knowledge-bases/kb-a", {}),
        (
            "PATCH",
            "/web/knowledge-bases/kb-a",
            {"json": {"description": "updated"}},
        ),
        ("DELETE", "/web/knowledge-bases/kb-a", {}),
        ("GET", "/web/knowledge-bases/kb-a/documents", {}),
        (
            "POST",
            "/web/knowledge-bases/kb-a/documents",
            {
                "json": {
                    "sourceType": "url",
                    "url": "https://example.com/docs",
                }
            },
        ),
        ("GET", "/web/knowledge-bases/kb-a/documents/doc-1", {}),
        (
            "PATCH",
            "/web/knowledge-bases/kb-a/documents/doc-1",
            {"json": {"metadata": {"team": "support"}}},
        ),
        ("DELETE", "/web/knowledge-bases/kb-a/documents/doc-1", {}),
        ("GET", "/web/knowledge-bases/kb-a/documents/doc-1/preview", {}),
        (
            "POST",
            "/web/knowledge-bases/kb-a/documents/upload",
            {"files": {"file": ("guide.pdf", b"%PDF-test", "application/pdf")}},
        ),
    ],
)
def test_all_knowledge_upstream_errors_use_structured_redacted_contract(
    method: str,
    path: str,
    request_kwargs: dict[str, object],
) -> None:
    class UpstreamError(RuntimeError):
        def __init__(self) -> None:
            super().__init__(
                "upstream quota exceeded; token=top-secret-token; "
                "AK=message-ak-secret; SK=message-sk-secret; retry later"
            )
            self.status_code = 429
            self.error_code = "QuotaExceeded"
            self.request_id = "req-upstream-123"
            self.region = "cn-beijing"
            self.retry_after = 3
            self.access_key = "ak-sensitive-value"
            self.secret_key = "sk-sensitive-value"
            self.authorization = "Bearer auth-sensitive-value"
            self.cookie = "session=cookie-sensitive-value"
            self.details = {
                "retryAfter": 3,
                "session_token": "session-sensitive-value",
                "nested": {"clientSecret": "client-sensitive-value"},
            }

    class FailingService:
        max_upload_bytes = 10 * 1024 * 1024

        def __getattr__(self, name: str):
            del name

            def fail(*args, **kwargs):
                del args, kwargs
                raise UpstreamError

            return fail

    app = FastAPI()
    mount_knowledge_routes(
        app,
        service=FailingService(),
        identity_resolver=lambda request: KnowledgeIdentity("user-1", "Alice"),
        region_resolver=lambda value: value or "cn-beijing",
        region_candidates_resolver=lambda: ("cn-beijing", "cn-shanghai"),
    )

    response = TestClient(app).request(method, path, **request_kwargs)

    assert response.status_code == 429
    detail = response.json()["detail"]
    assert detail["status"] == 429
    assert detail["errorCode"] == "QuotaExceeded"
    assert detail["requestId"] == "req-upstream-123"
    assert detail["message"] == (
        "upstream quota exceeded; token=[REDACTED]; "
        "AK=[REDACTED]; SK=[REDACTED]; retry later"
    )
    assert detail["diagnostics"]["errors"][0]["exceptionType"] == "UpstreamError"
    fields = detail["diagnostics"]["errors"][0]["fields"]
    assert fields["region"] == "cn-beijing"
    assert fields["retry_after"] == 3
    assert fields["access_key"] == "[REDACTED]"
    assert fields["secret_key"] == "[REDACTED]"
    assert fields["authorization"] == "[REDACTED]"
    assert fields["cookie"] == "[REDACTED]"
    assert fields["details"]["retryAfter"] == 3
    assert fields["details"]["session_token"] == "[REDACTED]"
    assert fields["details"]["nested"]["clientSecret"] == "[REDACTED]"
    for secret in (
        "top-secret-token",
        "message-ak-secret",
        "message-sk-secret",
        "ak-sensitive-value",
        "sk-sensitive-value",
        "auth-sensitive-value",
        "cookie-sensitive-value",
        "session-sensitive-value",
        "client-sensitive-value",
    ):
        assert secret not in response.text


def test_signed_owner_envelope_cannot_be_moved_to_another_knowledge_base() -> None:
    original = owned_record("kb-a", "user-1", "Alice")
    copied = replace(
        original,
        id="kb-copy",
        name="copy",
        provider_knowledge_id="provider-copy",
    )
    service, _, _ = service_for([copied])

    regular = service.list(
        identity=KnowledgeIdentity("user-1", "Alice"),
        region="cn-beijing",
        project_name=None,
        next_token=None,
        page_size=30,
    )
    admin = service.list(
        identity=KnowledgeIdentity("admin", "Admin", is_admin=True),
        region="cn-beijing",
        project_name=None,
        next_token=None,
        page_size=30,
    )

    assert regular.items == []
    assert admin.items[0].owner_id == ""
    assert admin.items[0].description == "visible description"


def test_first_provider_binding_requires_admin_or_developer_capability() -> None:
    service, agentkit, _ = service_for([])
    body = CreateKnowledgeBaseBody(
        name="support",
        region="cn-beijing",
    )

    with pytest.raises(KnowledgeAccessError) as captured:
        service.create(
            body,
            identity=KnowledgeIdentity("user-1", "Alice"),
            region="cn-beijing",
        )

    assert captured.value.status_code == 403
    assert agentkit.records == {}


def test_admin_update_of_unmanaged_record_does_not_claim_ownership() -> None:
    unmanaged = KnowledgeRecord(
        id="kb-legacy",
        name="legacy",
        description="unmanaged",
        provider_type="VIKINGDB_KNOWLEDGE",
        provider_knowledge_id="provider-legacy",
        project_name="default",
        region="cn-beijing",
    )
    service, agentkit, _ = service_for([unmanaged])

    result = service.update(
        "kb-legacy",
        UpdateKnowledgeBaseBody(description="changed"),
        identity=KnowledgeIdentity("admin", "Admin", is_admin=True),
        region="cn-beijing",
    )

    assert agentkit.updated_description == "changed"
    assert result.owner_id == ""
    assert result.description == "changed"


def test_connection_credentials_use_supported_temporary_sts_payload() -> None:
    connection = ProviderConnection(
        provider_type="VIKINGDB_KNOWLEDGE",
        provider_knowledge_id="provider-1",
        auth_type="STS",
        auth_key=json.dumps(
            {
                "AccessKeyId": "temporary-ak",
                "SecretAccessKey": "temporary-sk",
                "SessionToken": "temporary-token",
            }
        ),
    )

    resolved = _connection_credentials(
        connection,
        lambda: ("fallback-ak", "fallback-sk", None),
    )

    assert resolved == ("temporary-ak", "temporary-sk", "temporary-token")


def test_connection_extra_config_without_auth_contract_uses_server_credentials() -> (
    None
):
    resolved = _connection_credentials(
        ProviderConnection(
            provider_type="VIKINGDB_KNOWLEDGE",
            provider_knowledge_id="provider-1",
            extra_config='{"collection":"support"}',
        ),
        lambda: ("server-ak", "server-sk", None),
    )

    assert resolved == ("server-ak", "server-sk", None)


def test_aksk_connection_without_embedded_keys_uses_server_credentials() -> None:
    resolved = _connection_credentials(
        ProviderConnection(
            provider_type="VIKINGDB_KNOWLEDGE",
            provider_knowledge_id="provider-1",
            auth_type="AK_SK",
        ),
        lambda: ("server-ak", "server-sk", None),
    )

    assert resolved == ("server-ak", "server-sk", None)


@pytest.mark.parametrize(
    "connection",
    [
        ProviderConnection(
            provider_type="VIKINGDB_KNOWLEDGE",
            provider_knowledge_id="provider-1",
            auth_type="Bearer",
            auth_key='{"token":"secret"}',
        ),
        ProviderConnection(
            provider_type="VIKINGDB_KNOWLEDGE",
            provider_knowledge_id="provider-1",
            auth_type="STS",
            auth_key="not-json",
        ),
    ],
)
def test_connection_credentials_reject_unsupported_or_malformed_auth(
    connection: ProviderConnection,
) -> None:
    with pytest.raises(KnowledgeAccessError) as captured:
        _connection_credentials(
            connection, lambda: ("fallback-ak", "fallback-sk", None)
        )

    assert captured.value.status_code == 409


def test_provider_connection_rejects_unsupported_base_url_path() -> None:
    build = build_viking_document_gateway_factory(
        provider="volcengine",
        resolve_credentials=lambda: ("ak", "sk", None),
    )
    record = KnowledgeRecord(
        id="kb-1",
        name="support",
        description="",
        provider_type="VIKINGDB_KNOWLEDGE",
        provider_knowledge_id="provider-1",
        project_name="default",
        region="cn-beijing",
    )

    with pytest.raises(KnowledgeAccessError) as captured:
        build(
            record,
            ProviderConnection(
                provider_type="VIKINGDB_KNOWLEDGE",
                provider_knowledge_id="provider-1",
                base_url="https://knowledge.example.com/private/api",
                region="cn-beijing",
            ),
        )

    assert captured.value.status_code == 409


@pytest.mark.parametrize("code", [1000005, "1000005"])
def test_missing_provider_collection_is_reported_as_invalid_association(
    code: int | str,
) -> None:
    class ProviderError(RuntimeError):
        def __init__(self) -> None:
            super().__init__(f"collection not exist, code:{code}")
            self.code = code

    def missing_collection():
        raise ProviderError

    gateway = VikingDocumentGateway(
        missing_collection,
        project_name="default",
        resource_id="kb-missing",
    )

    with pytest.raises(KnowledgeAccessError) as captured:
        gateway.list(offset=0, limit=30, document_type=None)

    assert captured.value.status_code == 409
    assert captured.value.error_code == PROVIDER_ASSOCIATION_INVALID
    assert "底层 Provider 知识库已不存在" in str(captured.value)
    assert "删除这个失效关联" in str(captured.value)


def test_missing_provider_collection_route_exposes_stable_error_code() -> None:
    class InvalidAssociationGateway(FakeDocumentGateway):
        def list(self, *, offset: int, limit: int, document_type: str | None):
            del offset, limit, document_type
            raise KnowledgeAccessError(
                "底层 Provider 知识库已不存在，此 AgentKit 关联已失效。",
                status_code=409,
                error_code=PROVIDER_ASSOCIATION_INVALID,
            )

    agentkit = FakeAgentKitGateway([owned_record("kb-a", "user-1", "Alice")])
    service = KnowledgeService(
        agentkit,
        lambda record, connection: InvalidAssociationGateway(),
        signing_key=SIGNING_KEY,
    )
    app = FastAPI()
    mount_knowledge_routes(
        app,
        service=service,
        identity_resolver=lambda request: KnowledgeIdentity("user-1", "Alice"),
        region_resolver=lambda value: value or "cn-beijing",
    )

    response = TestClient(app).get(
        "/web/knowledge-bases/kb-a/documents?region=cn-beijing"
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["status"] == 409
    assert detail["message"] == (
        "底层 Provider 知识库已不存在，此 AgentKit 关联已失效。"
    )
    assert detail["errorCode"] == PROVIDER_ASSOCIATION_INVALID


def test_document_submission_exposes_safe_actionable_provider_reason() -> None:
    class ProviderError(RuntimeError):
        code = 1000003
        message = (
            "document type mp4 is not supported; "
            "request_id=sensitive-provider-request-id"
        )

    class Collection:
        def list_docs(self, **kwargs):
            del kwargs
            return []

        def add_doc(self, *args, **kwargs):
            del args, kwargs
            raise ProviderError(ProviderError.message)

    agentkit = FakeAgentKitGateway([owned_record("kb-a", "user-1", "Alice")])
    gateway = VikingDocumentGateway(
        Collection,
        project_name="default",
        resource_id="kb-provider",
    )
    service = KnowledgeService(
        agentkit,
        lambda record, connection: gateway,
        signing_key=SIGNING_KEY,
    )
    app = FastAPI()
    mount_knowledge_routes(
        app,
        service=service,
        identity_resolver=lambda request: KnowledgeIdentity("user-1", "Alice"),
        region_resolver=lambda value: value or "cn-beijing",
    )

    response = TestClient(app).post(
        "/web/knowledge-bases/kb-a/documents",
        json={
            "sourceType": "tos",
            "tosPath": "studio-bucket/path/video.mp4",
            "documentType": "mp4",
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["status"] == 422
    assert detail["message"] == (
        "Provider 暂不支持此文件格式或导入方式，请改用受支持的数据后重试。"
    )
    assert detail["errorCode"] == DOCUMENT_FORMAT_UNSUPPORTED
    assert detail["upstreamMessage"].startswith("document type mp4 is not supported")
    assert detail["upstreamErrorCode"] == "1000003"
    assert detail["requestId"] == "sensitive-provider-request-id"


def test_unknown_provider_submission_error_is_structured_and_redacted() -> None:
    class ProviderError(RuntimeError):
        code = 1000003
        message = "internal endpoint=https://private.example; secret=sensitive"

    class Collection:
        def list_docs(self, **kwargs):
            del kwargs
            return []

        def add_doc(self, *args, **kwargs):
            del args, kwargs
            raise ProviderError(ProviderError.message)

    agentkit = FakeAgentKitGateway([owned_record("kb-a", "user-1", "Alice")])
    service = KnowledgeService(
        agentkit,
        lambda record, connection: VikingDocumentGateway(
            Collection,
            project_name="default",
            resource_id="kb-provider",
        ),
        signing_key=SIGNING_KEY,
    )
    app = FastAPI()
    mount_knowledge_routes(
        app,
        service=service,
        identity_resolver=lambda request: KnowledgeIdentity("user-1", "Alice"),
        region_resolver=lambda value: value or "cn-beijing",
    )

    response = TestClient(app).post(
        "/web/knowledge-bases/kb-a/documents",
        json={
            "sourceType": "tos",
            "tosPath": "studio-bucket/path/video.mp4",
            "documentType": "mp4",
        },
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["status"] == 502
    assert detail["errorCode"] == "1000003"
    assert detail["message"] == (
        "internal endpoint=https://private.example; secret=[REDACTED]"
    )
    assert "secret=sensitive" not in response.text


def test_missing_document_remains_a_document_not_found_error() -> None:
    class ProviderError(RuntimeError):
        code = 1001001

    class Collection:
        def get_doc(self, *args, **kwargs):
            del args, kwargs
            raise ProviderError("document not exist")

    gateway = VikingDocumentGateway(
        Collection,
        project_name="default",
        resource_id=None,
    )

    with pytest.raises(KnowledgeAccessError) as captured:
        gateway.get("doc-missing")

    assert captured.value.status_code == 404
    assert captured.value.error_code == DOCUMENT_NOT_FOUND
    assert str(captured.value) == "知识内容不存在或已被删除。"


def test_agentkit_invalid_resource_not_found_maps_to_404() -> None:
    class Client:
        def get_knowledge_base(self, request):
            del request
            raise RuntimeError("InvalidResource.NotFound")

    gateway = SdkAgentKitKnowledgeGateway(lambda region: Client())

    with pytest.raises(KnowledgeAccessError) as captured:
        gateway.get("kb-missing", region="ap-southeast-1")

    assert captured.value.status_code == 404
    assert str(captured.value) == "知识库不存在。"


def test_byteplus_empty_document_page_without_doc_list_is_empty() -> None:
    class Collection:
        def list_docs(self, **kwargs):
            del kwargs
            raise KeyError("doc_list")

    gateway = VikingDocumentGateway(
        Collection,
        project_name="default",
        resource_id="kb-provider",
    )

    documents, has_more = gateway.list(offset=0, limit=30, document_type=None)

    assert documents == []
    assert has_more is False


@pytest.mark.parametrize("name", ["中文知识库", "has-hyphen", "1starts_with_digit"])
def test_knowledge_name_rejects_values_agentkit_cannot_register(name: str) -> None:
    with pytest.raises(ValueError):
        CreateKnowledgeBaseBody(name=name)


def test_knowledge_description_respects_signed_agentkit_limit() -> None:
    with pytest.raises(ValueError):
        CreateKnowledgeBaseBody(name="support", description="x" * 81)


def test_provider_document_exposes_native_file_size_when_available() -> None:
    from frontend.server.knowledge.gateways import _document

    class Document:
        doc_id = "doc-size"
        doc_name = "guide.pdf"
        doc_type = "pdf"
        status = "ready"
        url = ""
        tos_path = "tos://bucket/guide.pdf"
        create_time = ""
        update_time = ""

        def __init__(self) -> None:
            self.fields = []
            self.raw_data = {"file_size": "2048"}

    assert _document(Document())["sizeBytes"] == 2048


def test_provider_document_exposes_uploaded_file_size_from_metadata() -> None:
    from frontend.server.knowledge.gateways import _document

    class Field:
        field_name = "_veadk_file_size_bytes"
        field_val = 4096

    class Document:
        doc_id = "doc-size"
        doc_name = "guide.pdf"
        doc_type = "pdf"
        status = "ready"
        url = ""
        tos_path = "tos://bucket/guide.pdf"
        create_time = ""
        update_time = ""

        def __init__(self) -> None:
            self.fields = [Field()]
            self.raw_data = {}

    assert _document(Document())["sizeBytes"] == 4096


def test_tos_create_resolves_new_document_id_after_submission() -> None:
    created = SimpleNamespace(
        doc_id="doc-tos-1",
        doc_name="archive",
        doc_type="pdf",
        status="processing",
        url="",
        tos_path="tos://bucket/archive.pdf",
        fields=[],
        create_time="",
        update_time="",
    )

    class Collection:
        def __init__(self) -> None:
            self.list_calls = 0

        def list_docs(self, **kwargs):
            del kwargs
            self.list_calls += 1
            return [] if self.list_calls == 1 else [created]

        def add_doc(self, *args, **kwargs):
            del args, kwargs

    collection = Collection()
    gateway = VikingDocumentGateway(
        lambda: collection,
        project_name="default",
        resource_id=None,
    )

    result = gateway.create(
        CreateDocumentBody(
            source_type="tos",
            tos_path="tos://bucket/archive.pdf",
        )
    )

    assert result["id"] == "doc-tos-1"


def test_tos_create_returns_complete_submitted_contract() -> None:
    class Collection:
        def list_docs(self, **kwargs):
            del kwargs
            return []

        def add_doc(self, *args, **kwargs):
            del args, kwargs

    gateway = VikingDocumentGateway(
        Collection,
        project_name="default",
        resource_id=None,
    )

    result = gateway.create(
        CreateDocumentBody(
            source_type="tos",
            tos_path="tos://bucket/pending.pdf",
        )
    )

    assert result == {
        "id": "",
        "name": "",
        "type": "",
        "url": "",
        "tosPath": "tos://bucket/pending.pdf",
        "metadata": {},
        "status": "submitted",
        "createdAt": "",
        "updatedAt": "",
    }


def test_url_create_defaults_missing_document_type_to_html() -> None:
    class Collection:
        def __init__(self) -> None:
            self.added: tuple[tuple[object, ...], dict[str, object]] | None = None

        def add_doc(self, *args, **kwargs):
            self.added = args, kwargs

    collection = Collection()
    gateway = VikingDocumentGateway(
        lambda: collection,
        project_name="default",
        resource_id="kb-provider",
    )

    result = gateway.create(
        CreateDocumentBody(
            source_type="url",
            name="Studio",
            document_type=" ",
            url="https://example.com/docs",
        )
    )

    assert collection.added is not None
    args, kwargs = collection.added
    assert args == ("url",)
    assert kwargs["doc_type"] == "html"
    assert kwargs["url"] == "https://example.com/docs"
    assert result["type"] == "html"


def test_viking_preview_uses_native_points_and_normalizes_attachments() -> None:
    points = [
        SimpleNamespace(
            point_id="point-1",
            chunk_id="chunk-1",
            chunk_title="Image",
            content="caption",
            chunk_attachment={
                "media": {
                    "attachment_url": "https://cdn.example.com/photo.png",
                    "mime_type": "image/png",
                }
            },
            table_chunk_fields=[{"column": "value"}],
        ),
        SimpleNamespace(
            point_id="point-2",
            chunk_id="chunk-2",
            chunk_title="Audio",
            content="transcript",
            chunk_attachment="https://cdn.example.com/voice.mp3?token=1",
            table_chunk_fields=None,
        ),
    ]

    class Collection:
        def __init__(self) -> None:
            self.kwargs = {}

        def list_points(self, **kwargs):
            self.kwargs = kwargs
            return points

    collection = Collection()
    gateway = VikingDocumentGateway(
        lambda: collection,
        project_name="default",
        resource_id="kb-provider",
    )

    chunks, has_more = gateway.preview("doc-1", offset=5, limit=1)

    assert collection.kwargs == {
        "offset": 5,
        "limit": 2,
        "doc_ids": ["doc-1"],
        "get_attachment_link": True,
        "project": "default",
        "resource_id": "kb-provider",
    }
    assert chunks == [
        {
            "id": "point-1",
            "title": "Image",
            "content": "caption",
            "attachmentUrl": "https://cdn.example.com/photo.png",
            "attachmentType": "image/png",
            "attachment": {
                "media": {
                    "attachment_url": "https://cdn.example.com/photo.png",
                    "mime_type": "image/png",
                }
            },
            "tableFields": [{"column": "value"}],
        }
    ]
    assert has_more is True


def test_viking_provisioner_uses_native_resource_id_and_explicit_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Client:
        def __init__(self) -> None:
            self.created: tuple[tuple[object, ...], dict[str, object]] | None = None
            self.deleted: tuple[tuple[object, ...], dict[str, object]] | None = None

        def create_collection(self, *args, **kwargs):
            self.created = (args, kwargs)
            return SimpleNamespace(resource_id="kb-provider")

        def drop_collection(self, *args, **kwargs) -> None:
            self.deleted = (args, kwargs)

    client = Client()
    provisioner = VikingKnowledgeBaseProvisioner(
        provider="volcengine",
        resolve_credentials=lambda: ("ak", "sk", None),
    )
    monkeypatch.setattr(provisioner, "_client", lambda region: client)

    provisioned = provisioner.create(
        name="support",
        description="Support docs",
        project_name="default",
        region="cn-beijing",
    )
    provisioner.delete(
        name=provisioned.name,
        provider_knowledge_id=provisioned.provider_knowledge_id,
        project_name="default",
        region="cn-beijing",
    )

    assert provisioned.provider_knowledge_id == "kb-provider"
    assert provisioned.name == "support"
    assert client.created == (
        (provisioned.name,),
        {"version": 4, "description": "Support docs", "project": "default"},
    )
    assert client.deleted == (
        (provisioned.name,),
        {"project": "default", "resource_id": "kb-provider"},
    )


def test_viking_hosts_cover_volcengine_and_byteplus_regions() -> None:
    assert _viking_host("volcengine", "cn-beijing") == (
        "api-knowledgebase.mlp.cn-beijing.volces.com"
    )
    assert _viking_host("byteplus", "ap-southeast-1") == (
        "api-knowledgebase.mlp.ap-southeast-1.bytepluses.com"
    )


def test_byteplus_provisioner_maps_agentkit_region_to_viking_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    class Client:
        def __init__(self, *, host: str, region: str, **kwargs) -> None:
            del kwargs
            captured.update(host=host, region=region)

    monkeypatch.setattr(
        "volcengine.viking_knowledgebase.VikingKnowledgeBaseService",
        Client,
    )
    provisioner = VikingKnowledgeBaseProvisioner(
        provider="byteplus",
        resolve_credentials=lambda: ("ak", "sk", None),
    )

    provisioner._client("ap-southeast-1")

    assert captured == {
        "host": "api-knowledgebase.mlp.cn-hongkong.bytepluses.com",
        "region": "cn-hongkong",
    }
