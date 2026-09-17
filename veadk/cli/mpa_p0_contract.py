"""MPA P0 cross-repository compatibility contract checks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping


REQUIRED_FIELDS = {
    "schemaVersion",
    "veadkRevision",
    "runtimeRevision",
    "runtimeImageDigest",
    "mpaProfileSchemaVersion",
    "agentkitSdkVersion",
    "runtimeExecutionCapability",
    "sessionExecutionConfigSchemaVersion",
    "workerProtocol",
    "workerRequiredEndpoints",
}
FORBIDDEN_KEY_PARTS = ("accesskey", "secret", "token", "password", "cookie")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
DEFAULT_COMPATIBILITY_MATRIX = {
    "schemaVersion": 1,
    "rules": [
        {
            "id": "p0-codex-rest-v1",
            "mpaProfileSchemaVersion": 1,
            "agentkitSdkVersion": "0.8.5",
            "runtimeExecutionCapability": "urn:veadk:mpa:execution:v1",
            "sessionExecutionConfigSchemaVersion": 1,
            "workerProtocol": "codex",
            "workerRequiredEndpoints": [
                "/health",
                "/ready",
                "/v1/sessions",
                "/v1/sessions/{session_id}/turns",
                "/v1/sessions/{session_id}/events",
            ],
        }
    ],
}


def default_matrix_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "mpa-p0"
        / "compatibility-matrix.json"
    )


def load_default_matrix() -> dict[str, Any]:
    path = default_matrix_path()
    if path.is_file():
        return load_json_object(path)
    return dict(DEFAULT_COMPATIBILITY_MATRIX)


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("root must be an object")
    return payload


def mpa_p0_manifest_errors(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    unknown = sorted(set(payload) - REQUIRED_FIELDS)
    if unknown:
        errors.append("unknown_or_forbidden_fields")
    missing = sorted(REQUIRED_FIELDS - set(payload))
    if missing:
        errors.append("missing_required_fields")
    if any(
        part in str(key).replace("_", "").lower()
        for key in payload
        for part in FORBIDDEN_KEY_PARTS
    ):
        errors.append("secret_fields_forbidden")
    if not SHA_RE.fullmatch(str(payload.get("veadkRevision", ""))):
        errors.append("invalid_veadk_revision")
    if not SHA_RE.fullmatch(str(payload.get("runtimeRevision", ""))):
        errors.append("invalid_runtime_revision")
    if not DIGEST_RE.fullmatch(str(payload.get("runtimeImageDigest", ""))):
        errors.append("invalid_runtime_image_digest")
    if payload.get("schemaVersion") != 1:
        errors.append("unsupported_manifest_schema")
    endpoints = payload.get("workerRequiredEndpoints")
    if not isinstance(endpoints, list) or not all(
        isinstance(endpoint, str) and endpoint.startswith("/") for endpoint in endpoints
    ):
        errors.append("invalid_worker_endpoints")
    return sorted(set(errors))


def evaluate_mpa_p0_compatibility(
    manifest: Mapping[str, Any],
    matrix: Mapping[str, Any],
) -> dict[str, Any]:
    errors = mpa_p0_manifest_errors(manifest)
    if errors:
        return {"status": "invalid_manifest", "errorCode": errors[0]}

    match_fields = REQUIRED_FIELDS - {
        "schemaVersion",
        "veadkRevision",
        "runtimeRevision",
        "runtimeImageDigest",
    }
    for rule in matrix.get("rules", []):
        if isinstance(rule, Mapping) and all(
            manifest[field] == rule.get(field) for field in match_fields
        ):
            return {"status": "compatible", "matrixRule": rule["id"]}
    return {
        "status": "incompatible",
        "errorCode": "worker_protocol_incompatible",
    }


def default_mpa_p0_manifest(
    *,
    veadk_revision: str = "0" * 40,
    runtime_revision: str = "0" * 40,
    runtime_image_digest: str = "sha256:" + "0" * 64,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "veadkRevision": veadk_revision,
        "runtimeRevision": runtime_revision,
        "runtimeImageDigest": runtime_image_digest,
        "mpaProfileSchemaVersion": 1,
        "agentkitSdkVersion": "0.8.5",
        "runtimeExecutionCapability": "urn:veadk:mpa:execution:v1",
        "sessionExecutionConfigSchemaVersion": 1,
        "workerProtocol": "codex",
        "workerRequiredEndpoints": [
            "/health",
            "/ready",
            "/v1/sessions",
            "/v1/sessions/{session_id}/turns",
            "/v1/sessions/{session_id}/events",
        ],
    }
