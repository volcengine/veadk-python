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

import hashlib
import io
import json
import tarfile
from typing import Any

import httpx
import pytest

from veadk.cli.generated_agent_codegen import GeneratedFile
from veadk.cli.generated_agent_skills import CanonicalSkillSnapshot
from veadk.cli.legacy_runtime_recovery import (
    apply_source_preserving_edits,
    build_sidecar_mcp_servers_json,
    mcp_reuse_supplied_credentials,
    mcp_secret_values_for_draft_references,
    retained_mcp_secret_values,
    build_source_preserving_overlay,
    canonicalize_source_preserving_mcp_credentials,
    ImageReference,
    LegacyRecoveryError,
    merge_mcp_recoveries,
    mcp_editor_draft_with_credentials,
    mcp_secret_values_from_runtime_environment,
    mcp_secret_values_from_toolset,
    OciImageInspector,
    pin_source_image,
    RegistryCredential,
    recover_mcp_from_runtime_environment,
    recover_mcp_from_toolset,
    resolve_source_preserving_mcp_owner,
    resolve_source_preserving_mcp_secrets,
)


def _canonical_snapshot(
    name: str,
    files: list[tuple[str, str]],
) -> CanonicalSkillSnapshot:
    return CanonicalSkillSnapshot(
        name=name,
        description="",
        files=tuple(
            GeneratedFile(path=path, content=content) for path, content in files
        ),
        content_digest="a" * 64,
    )


def _layer(entries: dict[str, bytes | tuple[str, str]]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for path, value in entries.items():
            info = tarfile.TarInfo(path)
            if isinstance(value, tuple):
                kind, target = value
                assert kind == "symlink"
                info.type = tarfile.SYMTYPE
                info.linkname = target
                archive.addfile(info)
                continue
            info.size = len(value)
            archive.addfile(info, io.BytesIO(value))
    return output.getvalue()


def _inspector(
    manifest: dict[str, Any],
    layers: dict[str, bytes],
) -> OciImageInspector:
    digest = "sha256:" + "a" * 64

    def handler(request: httpx.Request) -> httpx.Response:
        if "/manifests/" in request.url.path:
            return httpx.Response(
                200,
                json=manifest,
                headers={"Docker-Content-Digest": digest},
            )
        layer_digest = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, content=layers[layer_digest])

    return OciImageInspector(
        lambda _image: RegistryCredential("server-user", "server-secret"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_image_reference_accepts_only_volcengine_cr() -> None:
    image = ImageReference.parse(
        "example-registry-cn-shanghai.cr.volces.com/agentkit/demo:v37"
    )

    assert image.registry_name == "example-registry"
    assert image.region == "cn-shanghai"
    assert image.repository == "agentkit/demo"
    assert image.reference == "v37"

    with pytest.raises(LegacyRecoveryError, match="registry_unsupported"):
        ImageReference.parse("docker.io/library/python:3.12")
    with pytest.raises(LegacyRecoveryError, match="reference_invalid"):
        ImageReference.parse(
            "https://example-registry-cn-shanghai.cr.volces.com/agentkit/demo:v37"
        )


def test_pin_source_image_uses_a_validated_control_plane_digest() -> None:
    image = ImageReference.parse(
        "example-registry-cn-shanghai.cr.volces.com/agentkit/demo:v37"
    )
    digest = "sha256:" + "d" * 64
    calls: list[ImageReference] = []

    assert pin_source_image(
        image,
        lambda value: calls.append(value) or digest,
    ) == image.pinned(digest)
    assert calls == [image]

    with pytest.raises(LegacyRecoveryError, match="digest_invalid"):
        pin_source_image(image, lambda _value: "mutable-tag")
    with pytest.raises(LegacyRecoveryError, match="reference_invalid"):
        ImageReference.parse(
            "example-registry-cn-shanghai.cr.volces.com/agentkit/demo?scope=all:v37"
        )


def test_oci_inspector_rejects_external_bearer_realm_without_sending_credentials() -> (
    None
):
    requested_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(str(request.url.host))
        return httpx.Response(
            401,
            headers={
                "www-authenticate": (
                    'Bearer realm="https://credentials.example.com/token",'
                    'service="cr",scope="repository:agentkit/demo:pull"'
                )
            },
        )

    inspector = OciImageInspector(
        lambda _image: RegistryCredential("server-user", "server-secret"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(LegacyRecoveryError, match="registry_auth_failed"):
        inspector.resolve_manifest(
            ImageReference.parse(
                "example-registry-cn-shanghai.cr.volces.com/agentkit/demo:v37"
            )
        )

    assert requested_hosts == ["example-registry-cn-shanghai.cr.volces.com"]


def test_oci_inspector_reports_registry_pull_denied_after_bearer_exchange() -> None:
    requests: list[tuple[str, bool]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        has_bearer = request.headers.get("authorization", "").startswith("Bearer ")
        requests.append((request.url.path, has_bearer))
        if request.url.path == "/token":
            return httpx.Response(200, json={"token": "opaque-registry-token"})
        if has_bearer:
            return httpx.Response(401, json={"errors": [{"code": "UNAUTHORIZED"}]})
        return httpx.Response(
            401,
            headers={
                "www-authenticate": (
                    'Bearer realm="https://auth.volces.com/token",'
                    'service="cr",scope="repository:agentkit/demo:pull"'
                )
            },
        )

    inspector = OciImageInspector(
        lambda _image: RegistryCredential("server-user", "server-secret"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(LegacyRecoveryError, match="registry_pull_denied"):
        inspector.resolve_manifest(
            ImageReference.parse(
                "example-registry-cn-shanghai.cr.volces.com/agentkit/demo:v37"
            )
        )

    assert requests == [
        ("/v2/agentkit/demo/manifests/v37", False),
        ("/token", False),
        ("/v2/agentkit/demo/manifests/v37", True),
    ]


def test_oci_inspector_requires_registry_manifest_digest() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "layers": [],
            },
        )

    inspector = OciImageInspector(
        lambda _image: RegistryCredential("server-user", "server-secret"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(LegacyRecoveryError, match="manifest_digest_missing"):
        inspector.resolve_manifest(
            ImageReference.parse(
                "example-registry-cn-shanghai.cr.volces.com/agentkit/demo:v37"
            )
        )


def test_oci_inspector_rejects_layer_digest_mismatch() -> None:
    layer = _layer({"workspace/skills/demo/SKILL.md": b"---\nname: demo\n---\n"})
    claimed_digest = "sha256:" + "f" * 64
    inspector = _inspector(
        {
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "layers": [
                {
                    "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                    "digest": claimed_digest,
                    "size": len(layer),
                }
            ],
        },
        {claimed_digest: layer},
    )

    with pytest.raises(LegacyRecoveryError, match="layer_digest_mismatch"):
        inspector.extract_skills(
            ImageReference.parse(
                "example-registry-cn-shanghai.cr.volces.com/agentkit/demo:v1"
            ),
            [("demo", "")],
        )


def test_mcp_servers_json_recovers_public_shape_without_headers() -> None:
    raw_secret = "must-never-leave-server"
    recovery = recover_mcp_from_runtime_environment(
        {
            "MCP_SERVERS_JSON": json.dumps(
                [
                    {
                        "name": "inventory",
                        "url": "https://mcp.example.com/inventory",
                        "headers": {"Authorization": f"Bearer {raw_secret}"},
                    }
                ]
            )
        }
    )

    assert recovery.format == "servers-json"
    assert len(recovery.configured_reference_keys) == 1
    reference = recovery.configured_reference_keys[0]
    assert reference.startswith("VEADK_STUDIO_LEGACY_MCP_")
    assert recovery.tools == (
        {
            "name": "inventory",
            "transport": "http",
            "url": "https://mcp.example.com/inventory",
            "authTokenEnv": reference,
        },
    )
    assert raw_secret not in json.dumps(recovery.tools)
    assert mcp_secret_values_from_runtime_environment(
        {
            "MCP_SERVERS_JSON": json.dumps(
                [
                    {
                        "name": "inventory",
                        "url": "https://mcp.example.com/inventory",
                        "headers": {"Authorization": f"Bearer {raw_secret}"},
                    }
                ]
            )
        }
    ) == {reference: raw_secret}

    editor_draft = mcp_editor_draft_with_credentials(
        {
            "name": "root-agent",
            "mcpTools": [dict(recovery.tools[0])],
            "subAgents": [],
        },
        {reference: raw_secret, "UNREFERENCED_SECRET": "must-not-be-returned"},
    )
    assert editor_draft["mcpTools"][0]["authToken"] == raw_secret
    assert "UNREFERENCED_SECRET" not in json.dumps(editor_draft)


def test_structured_mcp_servers_allow_shared_url_with_distinct_names() -> None:
    raw = build_sidecar_mcp_servers_json(
        draft={
            "name": "root-agent",
            "mcpTools": [
                {
                    "name": "orders",
                    "transport": "http",
                    "url": "https://mcp.example.com/shared",
                },
                {
                    "name": "inventory",
                    "transport": "http",
                    "url": "https://mcp.example.com/shared",
                },
            ],
            "subAgents": [],
        },
        secret_values={},
    )
    assert [item["name"] for item in json.loads(raw)] == ["orders", "inventory"]
    recovered = recover_mcp_from_runtime_environment({"MCP_SERVERS_JSON": raw})
    assert [item["name"] for item in recovered.tools] == ["orders", "inventory"]


def test_mcp_urls_reuses_opaque_api_key_marker() -> None:
    recovery = recover_mcp_from_runtime_environment(
        {
            "MCP_URLS": "https://mcp.example.com/catalog,https://mcp.example.com/order",
            "MCP_API_KEY": "secret",
        }
    )

    assert [item["name"] for item in recovery.tools] == ["catalog", "order"]
    assert all(
        str(item["authTokenEnv"]).startswith("VEADK_STUDIO_LEGACY_MCP_")
        for item in recovery.tools
    )
    assert len(recovery.configured_reference_keys) == 2
    assert mcp_secret_values_from_runtime_environment(
        {
            "MCP_URLS": (
                "https://mcp.example.com/catalog,https://mcp.example.com/order"
            ),
            "MCP_API_KEY": "secret",
        }
    ) == {key: "secret" for key in recovery.configured_reference_keys}


def test_managed_toolset_recovers_endpoint_without_exposing_api_key() -> None:
    raw_secret = "toolset-secret-must-stay-server-side"
    toolset = {
        "name": "yumc-tools",
        "path": "/mcp",
        "network_configurations": [
            {
                "network_type": "public",
                "endpoint": "https://toolset.example.com",
            }
        ],
        "authorizer_configuration": {
            "authorizer_type": "KeyAuth",
            "authorizer": {
                "key_auth": {"api_keys": [{"name": "runtime", "key": raw_secret}]}
            },
        },
    }

    recovery = recover_mcp_from_toolset(toolset)
    reference = recovery.configured_reference_keys[0]

    assert recovery.format == "agentkit-toolset"
    assert recovery.tools == (
        {
            "name": "yumc-tools",
            "transport": "http",
            "url": "https://toolset.example.com/mcp",
            "authTokenEnv": reference,
        },
    )
    assert raw_secret not in json.dumps(recovery.tools)
    assert mcp_secret_values_from_toolset(toolset) == {reference: raw_secret}


def test_mcp_recovery_merges_environment_and_managed_toolset() -> None:
    environment = recover_mcp_from_runtime_environment(
        {"MCP_URLS": "https://mcp.example.com/orders"}
    )
    toolset = recover_mcp_from_toolset(
        {
            "name": "inventory",
            "path": "/mcp",
            "network_configurations": [
                {
                    "network_type": "public",
                    "endpoint": "https://toolset.example.com",
                }
            ],
        }
    )

    merged = merge_mcp_recoveries(environment, toolset)

    assert [item["name"] for item in merged.tools] == ["orders", "inventory"]
    assert merged.format == "urls+agentkit-toolset"


def test_mcp_recovery_rejects_ambiguous_name_or_endpoint() -> None:
    primary = recover_mcp_from_runtime_environment(
        {"MCP_URLS": "https://mcp.example.com/orders"}
    )
    duplicate_endpoint = recover_mcp_from_toolset(
        {
            "name": "other-name",
            "path": "/orders",
            "network_configurations": [
                {
                    "network_type": "public",
                    "endpoint": "https://mcp.example.com",
                }
            ],
        }
    )

    with pytest.raises(LegacyRecoveryError, match="legacy_mcp_recovery_duplicate"):
        merge_mcp_recoveries(primary, duplicate_endpoint)


def test_source_preserving_edits_only_copy_skills_and_mcp() -> None:
    published = {
        "name": "root-agent",
        "instruction": "Published instruction",
        "deployment": {"envValues": {"MODEL_AGENT_NAME": "published-model"}},
        "selectedSkills": [],
        "mcpTools": [],
        "subAgents": [
            {
                "name": "worker",
                "instruction": "Published worker",
                "mcpTools": [],
                "subAgents": [],
            }
        ],
    }
    requested = {
        "name": "root-agent",
        "instruction": "Browser must not replace source",
        "deployment": {"envValues": {"MODEL_AGENT_NAME": "published-model"}},
        "selectedSkills": [
            {
                "source": "local",
                "folder": "runbook",
                "name": "runbook",
                "localFiles": [
                    {
                        "path": "skills/runbook/SKILL.md",
                        "content": "# Runbook\n",
                    }
                ],
            }
        ],
        "mcpTools": [
            {
                "name": "inventory",
                "transport": "http",
                "url": "https://mcp.example.com/inventory",
            }
        ],
        "subAgents": [
            {
                "name": "worker",
                "instruction": "Browser must not replace worker source",
                "mcpTools": [
                    {
                        "name": "orders",
                        "transport": "http",
                        "url": "https://mcp.example.com/orders",
                    }
                ],
                "subAgents": [],
            }
        ],
    }

    edited = apply_source_preserving_edits(published, requested)

    assert edited["instruction"] == "Published instruction"
    assert edited["deployment"]["envValues"] == {"MODEL_AGENT_NAME": "published-model"}
    assert edited["subAgents"][0]["instruction"] == "Published worker"
    assert edited["selectedSkills"][0]["name"] == "runbook"
    assert edited["mcpTools"][0]["name"] == "inventory"
    assert edited["subAgents"][0]["mcpTools"][0]["name"] == "orders"


def test_source_preserving_edits_reject_plaintext_draft_secret_and_graph_change() -> (
    None
):
    published = {"name": "root", "subAgents": []}

    with pytest.raises(LegacyRecoveryError, match="mcp_secret_forbidden"):
        apply_source_preserving_edits(
            published,
            {
                "name": "root",
                "subAgents": [],
                "mcpTools": [
                    {
                        "name": "inventory",
                        "transport": "http",
                        "url": "https://mcp.example.com/inventory",
                        "authToken": "must-not-enter-draft",
                    }
                ],
            },
        )

    with pytest.raises(LegacyRecoveryError, match="agent_graph_changed"):
        apply_source_preserving_edits(
            published,
            {"name": "root", "subAgents": [{"name": "new-child"}]},
        )

    with pytest.raises(LegacyRecoveryError, match="draft_env_forbidden"):
        apply_source_preserving_edits(
            {
                "name": "root",
                "subAgents": [],
                "deployment": {"envValues": {"MODEL_AGENT_NAME": "published"}},
            },
            {
                "name": "root",
                "subAgents": [],
                "deployment": {"envValues": {"MODEL_AGENT_NAME": "changed"}},
            },
        )


def test_source_preserving_mcp_secret_retains_replaces_and_removes() -> None:
    published = {
        "name": "root",
        "mcpTools": [
            {
                "name": "orders",
                "transport": "http",
                "url": "https://mcp.example.com/orders",
                "authTokenEnv": "OLD_ORDERS_REF",
            },
            {
                "name": "inventory",
                "transport": "http",
                "url": "https://mcp.example.com/inventory",
                "authTokenEnv": "OLD_INVENTORY_REF",
            },
        ],
        "subAgents": [],
    }
    edited = {
        "name": "root",
        "mcpTools": [
            {
                "name": "orders",
                "transport": "http",
                "url": "https://mcp.example.com/orders",
                "authTokenEnv": "OLD_ORDERS_REF",
            },
            {
                "name": "inventory",
                "transport": "http",
                "url": "https://mcp.example.com/inventory",
            },
            {
                "name": "catalog",
                "transport": "http",
                "url": "https://mcp.example.com/catalog",
                "authTokenEnv": "NEW_CATALOG_REF",
            },
        ],
        "subAgents": [],
    }

    resolved = resolve_source_preserving_mcp_secrets(
        published_draft=published,
        edited_draft=edited,
        recovered_values={
            "OLD_ORDERS_REF": "old-orders-secret",
            "OLD_INVENTORY_REF": "old-inventory-secret",
        },
        supplied_values={"NEW_CATALOG_REF": "new-catalog-secret"},
    )

    assert resolved == {
        "OLD_ORDERS_REF": "old-orders-secret",
        "NEW_CATALOG_REF": "new-catalog-secret",
    }


def test_source_preserving_mcp_secret_cannot_reuse_old_secret_for_new_endpoint() -> (
    None
):
    published = {
        "name": "root",
        "mcpTools": [
            {
                "name": "orders",
                "transport": "http",
                "url": "https://mcp.example.com/orders",
                "authTokenEnv": "OLD_REF",
            }
        ],
    }
    edited = {
        "name": "root",
        "mcpTools": [
            {
                "name": "orders",
                "transport": "http",
                "url": "https://attacker.example.com/mcp",
                "authTokenEnv": "OLD_REF",
            }
        ],
    }

    with pytest.raises(LegacyRecoveryError, match="credential_identity_changed"):
        resolve_source_preserving_mcp_secrets(
            published_draft=published,
            edited_draft=edited,
            recovered_values={"OLD_REF": "server-only-secret"},
            supplied_values={},
        )


def test_source_preserving_mcp_credentials_use_server_generated_reference() -> None:
    canonical, resolved = canonicalize_source_preserving_mcp_credentials(
        published_draft={"name": "root", "mcpTools": []},
        edited_draft={
            "name": "root",
            "mcpTools": [
                {
                    "name": "catalog",
                    "transport": "http",
                    "url": "https://mcp.example.com/catalog",
                    "authTokenEnv": "BROWSER_CHOSEN_REFERENCE",
                }
            ],
        },
        recovered_values={},
        supplied_credentials=[
            {
                "agentName": "root",
                "name": "catalog",
                "url": "https://mcp.example.com/catalog",
                "value": "new-catalog-secret",
            }
        ],
    )

    reference = canonical["mcpTools"][0]["authTokenEnv"]
    assert reference.startswith("VEADK_STUDIO_LEGACY_MCP_")
    assert reference != "BROWSER_CHOSEN_REFERENCE"
    assert resolved == {reference: "new-catalog-secret"}


def test_source_preserving_mcp_credentials_retain_exact_published_identity() -> None:
    published = {
        "name": "root",
        "mcpTools": [
            {
                "name": "orders",
                "transport": "http",
                "url": "https://mcp.example.com/orders",
                "authTokenEnv": "PUBLISHED_ORDERS_REF",
            }
        ],
    }

    canonical, resolved = canonicalize_source_preserving_mcp_credentials(
        published_draft=published,
        edited_draft=published,
        recovered_values={"PUBLISHED_ORDERS_REF": "retained-secret"},
        supplied_credentials=[],
    )

    assert canonical["mcpTools"][0]["authTokenEnv"] == "PUBLISHED_ORDERS_REF"
    assert resolved == {"PUBLISHED_ORDERS_REF": "retained-secret"}


def test_source_preserving_mcp_credentials_canonicalize_legacy_display_name() -> None:
    published = {
        "name": "root",
        "mcpTools": [
            {
                "name": "订单 MCP 工具",
                "transport": "http",
                "url": "https://mcp.example.com/orders",
                "authTokenEnv": "PUBLISHED_ORDERS_REF",
            }
        ],
    }

    canonical, resolved = canonicalize_source_preserving_mcp_credentials(
        published_draft=published,
        edited_draft=published,
        recovered_values={},
        supplied_credentials=[
            {
                "agentName": "root",
                "name": "订单 MCP 工具",
                "url": "https://mcp.example.com/orders",
                "value": "replacement-secret",
            }
        ],
    )

    assert canonical["mcpTools"][0]["name"] == "MCP"
    assert canonical["mcpTools"][0]["authTokenEnv"] == "PUBLISHED_ORDERS_REF"
    assert resolved == {"PUBLISHED_ORDERS_REF": "replacement-secret"}


def test_source_preserving_mcp_credentials_generate_missing_legacy_name() -> None:
    published = {
        "name": "root",
        "mcpTools": [
            {
                "name": "",
                "transport": "http",
                "url": "https://mcp.example.com/orders",
                "authTokenEnv": "PUBLISHED_ORDERS_REF",
            }
        ],
    }

    canonical, resolved = canonicalize_source_preserving_mcp_credentials(
        published_draft=published,
        edited_draft=published,
        recovered_values={},
        supplied_credentials=[
            {
                "agentName": "root",
                "name": "",
                "url": "https://mcp.example.com/orders",
                "value": "replacement-secret",
            }
        ],
    )

    assert canonical["mcpTools"][0]["name"] == "orders"
    assert canonical["mcpTools"][0]["authTokenEnv"] == "PUBLISHED_ORDERS_REF"
    assert resolved == {"PUBLISHED_ORDERS_REF": "replacement-secret"}


def test_source_preserving_mcp_credentials_reject_unmatched_invalid_name() -> None:
    with pytest.raises(LegacyRecoveryError, match="credential_input_invalid"):
        canonicalize_source_preserving_mcp_credentials(
            published_draft={"name": "root", "mcpTools": []},
            edited_draft={
                "name": "root",
                "mcpTools": [
                    {
                        "name": "orders",
                        "transport": "http",
                        "url": "https://mcp.example.com/orders",
                    }
                ],
            },
            recovered_values={},
            supplied_credentials=[
                {
                    "agentName": "root",
                    "name": "伪造 MCP 名称",
                    "url": "https://mcp.example.com/orders",
                    "value": "attacker-supplied-secret",
                }
            ],
        )


def test_source_preserving_mcp_credentials_reject_unsafe_legacy_display_name() -> None:
    draft = {
        "name": "root",
        "mcpTools": [
            {
                "name": "orders\nunsafe",
                "transport": "http",
                "url": "https://mcp.example.com/orders",
            }
        ],
    }

    with pytest.raises(LegacyRecoveryError, match="credential_input_invalid"):
        canonicalize_source_preserving_mcp_credentials(
            published_draft={"name": "root", "mcpTools": []},
            edited_draft=draft,
            recovered_values={},
            supplied_credentials=[
                {
                    "agentName": "root",
                    "name": "orders\nunsafe",
                    "url": "https://mcp.example.com/orders",
                    "value": "attacker-supplied-secret",
                }
            ],
        )


def test_source_preserving_mcp_credentials_reject_stdio() -> None:
    with pytest.raises(LegacyRecoveryError, match="stdio_unsupported"):
        canonicalize_source_preserving_mcp_credentials(
            published_draft={"name": "root"},
            edited_draft={
                "name": "root",
                "mcpTools": [
                    {
                        "name": "local-command",
                        "transport": "stdio",
                        "command": "npx",
                        "args": ["server"],
                    }
                ],
            },
            recovered_values={},
            supplied_credentials=[],
        )


def test_sidecar_mcp_servers_json_uses_server_secret_values() -> None:
    value = build_sidecar_mcp_servers_json(
        draft={
            "name": "root",
            "mcpTools": [
                {
                    "name": "orders",
                    "transport": "http",
                    "url": "https://mcp.example.com/orders",
                    "authTokenEnv": "ORDERS_REF",
                }
            ],
        },
        secret_values={"ORDERS_REF": "server-only-secret"},
    )

    assert json.loads(value) == [
        {
            "name": "orders",
            "url": "https://mcp.example.com/orders",
            "headers": {"Authorization": "Bearer server-only-secret"},
        }
    ]


def test_unchanged_mcp_reference_resolves_from_structured_runtime_secret() -> None:
    published = {
        "name": "root",
        "mcpTools": [
            {
                "name": "orders",
                "transport": "http",
                "url": "https://mcp.example.com/orders",
                "authTokenEnv": "ORDERS_REF",
            }
        ],
    }
    runtime_environment = {
        "MCP_SERVERS_JSON": json.dumps(
            [
                {
                    "name": "orders",
                    "url": "https://mcp.example.com/orders",
                    "headers": {"Authorization": "Bearer retained-secret"},
                }
            ]
        )
    }
    recovery = recover_mcp_from_runtime_environment(runtime_environment)
    recovered = mcp_secret_values_from_runtime_environment(runtime_environment)
    reference_values = mcp_secret_values_for_draft_references(
        draft=published,
        recovery=recovery,
        recovered_values=recovered,
    )

    assert reference_values == {"ORDERS_REF": "retained-secret"}
    assert retained_mcp_secret_values(
        published_draft=published,
        edited_draft=published,
        published_reference_values=reference_values,
    ) == {"ORDERS_REF": "retained-secret"}


def test_changed_mcp_url_requires_explicit_server_validated_reuse() -> None:
    published = {
        "name": "root",
        "mcpTools": [
            {
                "name": "orders",
                "transport": "http",
                "url": "https://mcp.example.com/orders",
                "authTokenEnv": "ORDERS_REF",
            }
        ],
    }
    edited = {
        "name": "root",
        "mcpTools": [
            {
                "name": "orders",
                "transport": "http",
                "url": "https://new-mcp.example.com/orders",
                "authTokenEnv": "ORDERS_REF",
            }
        ],
    }
    reference_values = {"ORDERS_REF": "retained-secret"}

    assert (
        retained_mcp_secret_values(
            published_draft=published,
            edited_draft=edited,
            published_reference_values=reference_values,
        )
        == {}
    )
    with pytest.raises(LegacyRecoveryError, match="credential_missing"):
        build_sidecar_mcp_servers_json(
            draft=edited,
            secret_values={},
        )

    reuse = mcp_reuse_supplied_credentials(
        published_draft=published,
        edited_draft=edited,
        published_reference_values=reference_values,
        reuse_requests=[
            {
                "agentName": "root",
                "name": "orders",
                "url": "https://new-mcp.example.com/orders",
                "sourceAuthTokenEnv": "ORDERS_REF",
            }
        ],
    )
    assert reuse == (
        {
            "agentName": "root",
            "name": "orders",
            "url": "https://new-mcp.example.com/orders",
            "value": "retained-secret",
        },
    )
    assert json.loads(
        build_sidecar_mcp_servers_json(
            draft=edited,
            secret_values={},
            supplied_credentials=reuse,
        )
    )[0]["headers"] == {"Authorization": "Bearer retained-secret"}


def test_mcp_reuse_rejects_a_different_published_tool() -> None:
    published = {
        "name": "root",
        "mcpTools": [
            {
                "name": "orders",
                "transport": "http",
                "url": "https://mcp.example.com/orders",
                "authTokenEnv": "ORDERS_REF",
            },
            {
                "name": "inventory",
                "transport": "http",
                "url": "https://mcp.example.com/inventory",
                "authTokenEnv": "INVENTORY_REF",
            },
        ],
    }
    edited = {
        "name": "root",
        "mcpTools": [
            {
                "name": "orders",
                "transport": "http",
                "url": "https://new-mcp.example.com/orders",
                "authTokenEnv": "ORDERS_REF",
            }
        ],
    }

    with pytest.raises(LegacyRecoveryError, match="reuse_source_missing"):
        mcp_reuse_supplied_credentials(
            published_draft=published,
            edited_draft=edited,
            published_reference_values={
                "ORDERS_REF": "orders-secret",
                "INVENTORY_REF": "inventory-secret",
            },
            reuse_requests=[
                {
                    "agentName": "root",
                    "name": "orders",
                    "url": "https://new-mcp.example.com/orders",
                    "sourceAuthTokenEnv": "INVENTORY_REF",
                }
            ],
        )


def test_sidecar_mcp_servers_json_supports_no_auth_and_distinct_credentials() -> None:
    value = build_sidecar_mcp_servers_json(
        draft={
            "name": "root",
            "mcpTools": [
                {
                    "name": "public",
                    "transport": "http",
                    "url": "https://mcp.example.com/public",
                },
                {
                    "name": "orders",
                    "transport": "http",
                    "url": "https://mcp.example.com/orders",
                    "authTokenEnv": "ORDERS_REF",
                },
                {
                    "name": "inventory",
                    "transport": "http",
                    "url": "https://mcp.example.com/inventory",
                    "authTokenEnv": "INVENTORY_REF",
                },
                {
                    "name": "local",
                    "transport": "stdio",
                    "command": "example",
                },
            ],
        },
        secret_values={"ORDERS_REF": "retained-orders-secret"},
        supplied_credentials=[
            {
                "agentName": "root",
                "name": "inventory",
                "url": "https://mcp.example.com/inventory",
                "value": "replacement-inventory-secret",
            }
        ],
    )

    assert json.loads(value) == [
        {
            "name": "public",
            "url": "https://mcp.example.com/public",
        },
        {
            "name": "orders",
            "url": "https://mcp.example.com/orders",
            "headers": {"Authorization": "Bearer retained-orders-secret"},
        },
        {
            "name": "inventory",
            "url": "https://mcp.example.com/inventory",
            "headers": {"Authorization": "Bearer replacement-inventory-secret"},
        },
    ]


def test_sidecar_mcp_servers_json_canonicalizes_legacy_display_name() -> None:
    value = build_sidecar_mcp_servers_json(
        draft={
            "name": "root",
            "mcpTools": [
                {
                    "name": "订单 MCP 工具",
                    "transport": "http",
                    "url": "https://mcp.example.com/orders",
                    "authTokenEnv": "ORDERS_REF",
                }
            ],
        },
        secret_values={},
        supplied_credentials=[
            {
                "agentName": "root",
                "name": "订单 MCP 工具",
                "url": "https://mcp.example.com/orders",
                "value": "replacement-secret",
            }
        ],
    )

    assert json.loads(value) == [
        {
            "name": "MCP",
            "url": "https://mcp.example.com/orders",
            "headers": {"Authorization": "Bearer replacement-secret"},
        }
    ]


@pytest.mark.parametrize(
    "environment,code",
    [
        ({"MCP_SERVERS_JSON": "not-json"}, "servers_json_invalid"),
        (
            {
                "MCP_SERVERS_JSON": json.dumps(
                    [
                        {
                            "name": "unsafe",
                            "url": (
                                "https://"
                                + "fixture-user"
                                + ":"
                                + "fixture-password"
                                + "@mcp.example.com/unsafe"
                            ),
                            "headers": {},
                        }
                    ]
                )
            },
            "url_invalid",
        ),
        (
            {
                "MCP_SERVERS_JSON": json.dumps(
                    [
                        {
                            "name": "unsafe",
                            "url": "https://mcp.example.com/unsafe",
                            "headers": {"Authorization": "bad\r\nInjected: true"},
                        }
                    ]
                )
            },
            "headers_invalid",
        ),
        (
            {
                "MCP_SERVERS_JSON": json.dumps(
                    [
                        {
                            "name": "unsupported",
                            "url": "https://mcp.example.com/unsupported",
                            "headers": {"X-API-Key": "secret"},
                        }
                    ]
                )
            },
            "headers_unsupported",
        ),
    ],
)
def test_mcp_recovery_rejects_unsafe_runtime_values(
    environment: dict[str, str], code: str
) -> None:
    with pytest.raises(LegacyRecoveryError, match=code):
        recover_mcp_from_runtime_environment(environment)


def test_oci_inspector_recovers_complete_skill_from_image_layers() -> None:
    first = _layer(
        {
            "workspace/app/skills/serial-inspector/SKILL.md": (
                b"---\nname: serial-inspector\ndescription: old\n---\n"
            ),
            "workspace/app/skills/serial-inspector/references/rules.md": b"old",
        }
    )
    second = _layer(
        {
            "workspace/app/skills/serial-inspector/SKILL.md": (
                b"---\nname: serial-inspector\ndescription: current\n---\n"
            ),
            "workspace/app/skills/serial-inspector/references/rules.md": b"current",
        }
    )
    first_digest = "sha256:" + hashlib.sha256(first).hexdigest()
    second_digest = "sha256:" + hashlib.sha256(second).hexdigest()
    manifest = {
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "layers": [
            {
                "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                "digest": first_digest,
                "size": len(first),
            },
            {
                "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                "digest": second_digest,
                "size": len(second),
            },
        ],
    }
    inspector = _inspector(manifest, {first_digest: first, second_digest: second})

    pinned, recovered = inspector.extract_skills(
        ImageReference.parse(
            "example-registry-cn-shanghai.cr.volces.com/agentkit/demo:v37"
        ),
        [("serial-inspector", "Serial diagnosis")],
    )

    assert pinned.endswith("@sha256:" + "a" * 64)
    assert len(recovered) == 1
    assert recovered[0].image_root == "workspace/app/skills/serial-inspector"
    assert recovered[0].files == (
        {
            "path": "skills/serial-inspector/SKILL.md",
            "content": "---\nname: serial-inspector\ndescription: current\n---\n",
        },
        {
            "path": "skills/serial-inspector/references/rules.md",
            "content": "current",
        },
    )
    expected_digest = hashlib.sha256()
    for item in recovered[0].files:
        expected_digest.update(
            item["path"].encode() + b"\0" + item["content"].encode() + b"\0"
        )
    assert recovered[0].digest == expected_digest.hexdigest()


def test_oci_inspector_rejects_skill_symlinks() -> None:
    layer = _layer(
        {
            "workspace/skills/demo/SKILL.md": b"---\nname: demo\n---\n",
            "workspace/skills/demo/references/leak.md": (
                "symlink",
                "/etc/passwd",
            ),
        }
    )
    layer_digest = "sha256:" + hashlib.sha256(layer).hexdigest()
    inspector = _inspector(
        {
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "layers": [
                {
                    "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                    "digest": layer_digest,
                    "size": len(layer),
                }
            ],
        },
        {layer_digest: layer},
    )

    with pytest.raises(LegacyRecoveryError, match="symlink_forbidden"):
        inspector.extract_skills(
            ImageReference.parse(
                "example-registry-cn-shanghai.cr.volces.com/agentkit/demo:v1"
            ),
            [("demo", "")],
        )


def test_oci_inspector_rejects_ambiguous_skill_roots() -> None:
    layer = _layer(
        {
            "workspace/a/skills/demo/SKILL.md": b"---\nname: demo\n---\n",
            "workspace/b/skills/demo/SKILL.md": b"---\nname: demo\n---\n",
        }
    )
    layer_digest = "sha256:" + hashlib.sha256(layer).hexdigest()
    inspector = _inspector(
        {
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "layers": [
                {
                    "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                    "digest": layer_digest,
                    "size": len(layer),
                }
            ],
        },
        {layer_digest: layer},
    )

    with pytest.raises(LegacyRecoveryError, match="root_ambiguous"):
        inspector.extract_skills(
            ImageReference.parse(
                "example-registry-cn-shanghai.cr.volces.com/agentkit/demo:v1"
            ),
            [("demo", "")],
        )


def test_source_preserving_overlay_uses_exact_image_and_only_resource_delta() -> None:
    source_image = (
        "example-registry-cn-shanghai.cr.volces.com/agentkit/demo@sha256:" + "a" * 64
    )
    published = {
        "name": "legacy-agent",
        "selectedSkills": [
            {
                "source": "local",
                "folder": "old-skill",
                "name": "old-skill",
                "localFiles": [
                    {
                        "path": "skills/old-skill/SKILL.md",
                        "content": "# Old\n",
                    }
                ],
            }
        ],
    }
    edited = {
        "name": "legacy-agent",
        "selectedSkills": [
            {
                "source": "local",
                "folder": "new-skill",
                "name": "new-skill",
                "localFiles": [
                    {
                        "path": "skills/new-skill/SKILL.md",
                        "content": "# New\n",
                    },
                    {
                        "path": "skills/new-skill/references/runbook.md",
                        "content": "steps\n",
                    },
                ],
            }
        ],
        "mcpTools": [
            {
                "name": "inventory",
                "transport": "http",
                "url": "https://mcp.example.com/inventory/mcp",
                "authTokenEnv": "VEADK_STUDIO_LEGACY_MCP_TEST_AUTH_TOKEN",
            }
        ],
    }

    files = {
        item["path"]: item["content"]
        for item in build_source_preserving_overlay(
            source_image=source_image,
            published_draft=published,
            edited_draft=edited,
            canonical_skills=(
                _canonical_snapshot(
                    "new-skill",
                    [
                        ("skills/new-skill/SKILL.md", "# New\n"),
                        (
                            "skills/new-skill/references/runbook.md",
                            "steps\n",
                        ),
                    ],
                ),
            ),
            application_mcp=True,
        )
    }

    assert files["Dockerfile"].splitlines()[0] == f"FROM {source_image}"
    assert "COPY agents" not in files["Dockerfile"]
    assert json.loads(files[".veadk-studio-overlay/managed.json"]) == ["old-skill"]
    assert json.loads(files[".veadk-studio-overlay/selected.json"]) == ["new-skill"]
    assert json.loads(files[".veadk-studio-overlay/mcp.json"]) == {
        "legacy-agent": [
            {
                "authTokenEnv": "VEADK_STUDIO_LEGACY_MCP_TEST_AUTH_TOKEN",
                "name": "inventory",
                "transport": "http",
                "url": "https://mcp.example.com/inventory/mcp",
            }
        ]
    }
    assert "# New" in files[".veadk-studio-overlay/skills/new-skill/SKILL.md"]
    assert ".veadk-studio-python/sitecustomize.py" in files


def test_source_preserving_overlay_keeps_or_replaces_runtime_skills_explicitly() -> (
    None
):
    source_image = (
        "example-registry-cn-shanghai.cr.volces.com/agentkit/demo@sha256:" + "e" * 64
    )
    published = {
        "name": "legacy-agent",
        "selectedSkills": [
            {
                "source": "runtime",
                "folder": "runbook",
                "name": "runbook",
                "description": "Deployed runbook",
            }
        ],
    }

    kept = {
        item["path"]: item["content"]
        for item in build_source_preserving_overlay(
            source_image=source_image,
            published_draft=published,
            edited_draft=published,
            canonical_skills=(),
            application_mcp=True,
        )
    }
    assert json.loads(kept[".veadk-studio-overlay/managed.json"]) == []
    assert json.loads(kept[".veadk-studio-overlay/selected.json"]) == []
    assert not any(path.startswith(".veadk-studio-overlay/skills/") for path in kept)

    replaced = {
        item["path"]: item["content"]
        for item in build_source_preserving_overlay(
            source_image=source_image,
            published_draft=published,
            edited_draft={
                "name": "legacy-agent",
                "selectedSkills": [
                    {
                        "source": "local",
                        "folder": "runbook",
                        "name": "runbook",
                        "localFiles": [
                            {
                                "path": "skills/runbook/SKILL.md",
                                "content": "# Replacement\n",
                            }
                        ],
                    }
                ],
            },
            canonical_skills=(
                _canonical_snapshot(
                    "runbook",
                    [("skills/runbook/SKILL.md", "# Replacement\n")],
                ),
            ),
            application_mcp=True,
        )
    }
    assert json.loads(replaced[".veadk-studio-overlay/managed.json"]) == ["runbook"]
    assert json.loads(replaced[".veadk-studio-overlay/selected.json"]) == ["runbook"]
    assert "# Replacement" in replaced[".veadk-studio-overlay/skills/runbook/SKILL.md"]

    removed = {
        item["path"]: item["content"]
        for item in build_source_preserving_overlay(
            source_image=source_image,
            published_draft=published,
            edited_draft={"name": "legacy-agent", "selectedSkills": []},
            canonical_skills=(),
            application_mcp=True,
        )
    }
    assert json.loads(removed[".veadk-studio-overlay/managed.json"]) == ["runbook"]
    assert json.loads(removed[".veadk-studio-overlay/selected.json"]) == []

    with pytest.raises(LegacyRecoveryError, match="runtime_skill_untrusted"):
        build_source_preserving_overlay(
            source_image=source_image,
            published_draft=published,
            edited_draft={
                "name": "legacy-agent",
                "selectedSkills": [
                    {
                        "source": "runtime",
                        "folder": "invented",
                        "name": "invented",
                    }
                ],
            },
            canonical_skills=(),
            application_mcp=True,
        )


def test_source_preserving_overlay_disables_mcp_replacement_for_sidecar() -> None:
    source_image = (
        "example-registry-cn-shanghai.cr.volces.com/agentkit/demo@sha256:" + "b" * 64
    )
    files = {
        item["path"]: item["content"]
        for item in build_source_preserving_overlay(
            source_image=source_image,
            published_draft={
                "name": "harness-app",
                "harnessSidecar": {"enabled": True},
            },
            edited_draft={"name": "harness-app", "mcpTools": []},
            canonical_skills=(),
            application_mcp=False,
        )
    }

    assert files[".veadk-studio-overlay/mcp.json"] == "{}"
    sitecustomize = files[".veadk-studio-python/sitecustomize.py"]
    assert "SkillToolset.__init__ =" not in sitecustomize
    assert "at most one root SkillToolset" in sitecustomize
    assert "VEADK_STUDIO_OVERLAY_READY_FILE" in files["Dockerfile"]


@pytest.mark.parametrize(
    ("sidecar_enabled", "effective_components", "toolset_id", "owner"),
    [
        (False, [], "", "application"),
        (True, ["context_engine"], "", "application"),
        (True, ["mcp_resilience"], "", "sidecar"),
        (False, [], "toolset-1", "platform"),
    ],
)
def test_source_preserving_mcp_owner_is_derived_from_effective_topology(
    sidecar_enabled: bool,
    effective_components: list[str],
    toolset_id: str,
    owner: str,
) -> None:
    assert (
        resolve_source_preserving_mcp_owner(
            sidecar_enabled=sidecar_enabled,
            effective_components=effective_components,
            mcp_toolset_id=toolset_id,
        )
        == owner
    )


def test_source_preserving_mcp_owner_rejects_platform_sidecar_ambiguity() -> None:
    with pytest.raises(LegacyRecoveryError, match="legacy_mcp_ownership_ambiguous"):
        resolve_source_preserving_mcp_owner(
            sidecar_enabled=True,
            effective_components=["mcp_gateway"],
            mcp_toolset_id="toolset-1",
        )
