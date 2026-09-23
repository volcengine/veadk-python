# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Re-package a migration delivery whose Sandbox CLI never finished.

The AgentKit CLI settles an agentic delivery in three steps: it reads the terminal
state the agent wrote (``work/agentic/state/status.json``), turns the validation
findings into a verification record, and packages ``output/veadk`` into
``delivery/migration-result.zip`` plus ``delivery/migration-result.json``.  Only the
first third of that chain needs the model: once the Codex turn ends in a successful
terminal state, the rest is a pure function of the files on disk.

A run whose launch shell disappears between those two points therefore leaves a
finished project and no artifact at all: the delivery driver lease keeps beating, the
CLI never writes ``process-exit.json``, and Studio has nothing to publish.  This module
rebuilds what the CLI would have written, by the CLI's own rules, so the delivery can
still be closed instead of waiting for a task that will never settle.

Two things keep that honest.  The program is a mirror: same file selection, same
archive layout, same verification mapping, same terminal status document, so every
reader downstream — the delivery report, the artifact download, the deploy path — sees
a delivery it already knows how to read.  And it only runs on the narrow window it was
written for: a successful terminal agent state, an existing output directory, and no
delivery the CLI already settled.  Anything else is refused, which leaves the task on
the ordinary "the migration process was interrupted" path.

One field is not a mirror.  The CLI records ``source_sha256`` as a fingerprint of the
source tree it was pointed at, hashed in its own locale-aware file order, which Python
cannot reproduce byte for byte.  The caller therefore hands in the uploaded source
archive's digest instead -- the value Studio already binds the migration confirmation
to -- so the field still names the source the delivery came from, by a measure both
sides agree on.

Studio ships this module's own source into the Sandbox, so the program that runs is the
code the tests exercise.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat as stat_module
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
ARTIFACT_NAME = "migration-result.zip"
RESULT_NAME = "migration-result.json"
STATUS_NAME = "migration-status.json"
REPORT_NAME = "convert_report.md"
FINDINGS_NAME = "validation_findings.json"
CLI_NAME = "agentkit-cli"
DELIVERY_PHASE = "completed"
DELIVERY_MESSAGE = "Migration artifact is ready"
DELIVERY_SCHEMA_VERSION = 1

# The agent's terminal states and the delivery state each one settles into, mirrored
# from the CLI's own projection in `runAgenticMigrationCore`.
DELIVERY_STATE_BY_AGENT_STATE = {
    "Succeed": "succeeded",
    "SucceedWithWarnings": "succeeded_with_warnings",
    "Partial": "partial",
}
_AGENT_STATE_BY_RAW = {
    "running": "Runnning",
    "succeeded": "Succeed",
    "succeeded_with_warnings": "SucceedWithWarnings",
    "partial": "Partial",
    "failed": "Failed",
}
SETTLED_DELIVERY_STATES = frozenset(
    {"succeeded", "succeeded_with_warnings", "partial", "failed"}
)

# File selection, mirrored from the CLI's `collectDeliveryFiles` and `shouldExclude`.
EXCLUDED_PATHS = frozenset(
    {".env", ".codex", ".agentkit/migrate", ".agentkit/artifacts"}
)
EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)
EXCLUDED_FILE_SUFFIXES = (".pyc", ".pyo", ".DS_Store", "~")
SECRET_FILE_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".jks")
ENVIRONMENT_EXAMPLE_NAMES = (".env.example", ".env.sample", ".env.template")
FINDING_SEVERITIES = ("fatal", "repairable", "degraded", "info")
MAX_FILES = 20_000
MAX_BYTES = 512 * 1024 * 1024
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_PATH_BYTES = 4 * 1024
MAX_DEPTH = 64

_PATH_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_ENVIRONMENT_NAME = re.compile(
    r"(?:API_KEY|ACCESS_KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|PRIVATE_KEY)",
    re.IGNORECASE,
)
_SECRET_ENVIRONMENT_REFERENCE = re.compile(
    r"(?:API_KEY|ACCESS_KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|PRIVATE_KEY)_ENV$",
    re.IGNORECASE,
)
_ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ENVIRONMENT_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
_INSECURE_ENVIRONMENT_VALUE = re.compile(
    r"API_KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL",
    re.IGNORECASE,
)


class RecoveryError(RuntimeError):
    """The Sandbox state cannot be turned into the delivery the CLI would have made."""


class LifecycleConfigError(RecoveryError):
    """agentkit.yaml exists but cannot be read as a YAML mapping at all."""


def recovery_source() -> str:
    """The recovery program Studio installs into the Sandbox."""
    return Path(__file__).read_text(encoding="utf-8")


def manifest_digest(files: object) -> str:
    """Fingerprint one delivery file list, independent of the order it was walked in.

    Studio compares this against the digest of the manifest the CLI itself wrote, so a
    recovered delivery can be shown to describe exactly the same bytes.
    """
    if not isinstance(files, list):
        raise RecoveryError("delivery files must be a list")
    lines: list[str] = []
    for item in files:
        if not isinstance(item, dict):
            raise RecoveryError("delivery file must be an object")
        lines.append(
            "\0".join(
                (
                    str(item.get("path") or ""),
                    str(item.get("size") or ""),
                    str(item.get("sha256") or ""),
                    str(item.get("mode") or ""),
                )
            )
        )
    digest = hashlib.sha256()
    digest.update("\n".join(sorted(lines)).encode("utf-8"))
    return digest.hexdigest()


def _now() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
    return f"{stamp[:-3]}Z"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, value: object) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _agent_state(value: object) -> str | None:
    """Mirror the CLI's `processState`: names, plus the short spellings it accepts."""
    if not isinstance(value, str):
        return None
    if value in {"Analysing", "Runnning", "Validating"} | set(
        DELIVERY_STATE_BY_AGENT_STATE
    ) | {"Failed"}:
        return value
    return _AGENT_STATE_BY_RAW.get(value)


def _read_agent_state(path: Path) -> tuple[dict[str, object], str]:
    state = _read_json(path)
    if state is None:
        raise RecoveryError(f"the agent left no readable terminal state at {path}")
    resolved = _agent_state(state.get("state"))
    if resolved is None:
        raise RecoveryError("the agent left no usable terminal state")
    return state, resolved


def _should_exclude(relative: str, name: str, is_directory: bool) -> bool:
    if relative in EXCLUDED_PATHS:
        return True
    if is_directory and name in EXCLUDED_DIRECTORIES:
        return True
    return relative.endswith(EXCLUDED_FILE_SUFFIXES)


def _is_secret_environment_file(relative: str) -> bool:
    name = Path(relative).name.lower()
    return name.startswith(".env") and name not in ENVIRONMENT_EXAMPLE_NAMES


def _configured_secrets() -> list[tuple[str, bytes]]:
    """Environment values that must never leave the Sandbox inside a delivery."""
    secrets: list[tuple[str, bytes]] = []
    for name, value in os.environ.items():
        if not _SECRET_ENVIRONMENT_NAME.search(name) or len(value) < 8:
            continue
        if _SECRET_ENVIRONMENT_REFERENCE.search(name) and _ENVIRONMENT_NAME.fullmatch(
            value
        ):
            continue
        secrets.append((name, value.encode("utf-8")))
    return secrets


def _assert_no_secret(path: Path, secrets: list[tuple[str, bytes]]) -> None:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise RecoveryError(f"cannot read {path.name}: {error}") from error
    for name, value in secrets:
        if value in content:
            raise RecoveryError(f"the project contains a real secret from {name}")


def collect_delivery_files(output_dir: Path) -> list[dict[str, object]]:
    """Walk the delivered project the way the CLI walks it."""
    root = output_dir.resolve()
    if not root.is_dir():
        raise RecoveryError(f"the migration output directory does not exist: {root}")
    secrets = _configured_secrets()
    files: list[dict[str, object]] = []
    total_bytes = 0

    def walk(directory: Path) -> None:
        nonlocal total_bytes
        try:
            names = sorted(os.listdir(directory))
        except OSError as error:
            raise RecoveryError(f"cannot list {directory}: {error}") from error
        for name in names:
            absolute = directory / name
            relative = absolute.relative_to(root).as_posix()
            info = absolute.lstat()
            if stat_module.S_ISLNK(info.st_mode):
                raise RecoveryError(f"the project contains a symbolic link: {relative}")
            is_directory = stat_module.S_ISDIR(info.st_mode)
            if _should_exclude(relative, name, is_directory):
                continue
            if is_directory:
                walk(absolute)
                continue
            if not stat_module.S_ISREG(info.st_mode):
                raise RecoveryError(
                    f"the project contains a non-regular file: {relative}"
                )
            if (
                _PATH_CONTROL_CHARACTERS.search(relative)
                or relative.startswith("/")
                or ".." in relative.split("/")
                or len(relative.encode("utf-8")) > MAX_PATH_BYTES
                or len(relative.split("/")) > MAX_DEPTH
            ):
                raise RecoveryError(f"the project contains an unsafe path: {relative}")
            if _is_secret_environment_file(relative) or relative.lower().endswith(
                SECRET_FILE_SUFFIXES
            ):
                raise RecoveryError(
                    f"the project contains a secret-bearing file: {relative}"
                )
            if info.st_size > MAX_FILE_BYTES:
                raise RecoveryError(f"{relative} exceeds the delivery file size limit")
            _assert_no_secret(absolute, secrets)
            total_bytes += info.st_size
            if len(files) + 1 > MAX_FILES or total_bytes > MAX_BYTES:
                raise RecoveryError("the project exceeds the delivery size limits")
            files.append(
                {
                    "path": relative,
                    "size": info.st_size,
                    "sha256": _sha256_file(absolute),
                    "mode": f"0{info.st_mode & 0o777:o}",
                }
            )

    walk(root)
    if not files:
        raise RecoveryError("the migration output contains no deliverable files")
    return files


def create_verified_zip(
    output_dir: Path,
    delivery_dir: Path,
    paths: list[str],
) -> dict[str, object]:
    """Write the artifact exactly as the CLI writes it, then verify what it wrote."""
    for executable in ("zip", "unzip"):
        if subprocess.run(
            [executable, "-v"], capture_output=True, check=False
        ).returncode not in (0, 1):
            raise RecoveryError(f"{executable} is required to package a delivery")
    final = delivery_dir / ARTIFACT_NAME
    temporary = (
        delivery_dir / f".migration-result-{os.getpid()}-{int(time.time() * 1000)}.zip"
    )
    try:
        packaged = subprocess.run(
            ["zip", "-q", "-X", str(temporary), "-@"],
            cwd=str(output_dir),
            input="".join(f"{path}\n" for path in paths),
            capture_output=True,
            text=True,
            check=False,
        )
        if packaged.returncode != 0:
            raise RecoveryError(f"packaging failed: {packaged.stderr.strip()}")
        listed = subprocess.run(
            ["unzip", "-Z1", str(temporary)],
            capture_output=True,
            text=True,
            check=False,
        )
        if listed.returncode != 0:
            raise RecoveryError(
                f"verifying the archive failed: {listed.stderr.strip()}"
            )
        entries = sorted(entry for entry in listed.stdout.splitlines() if entry)
        if entries != sorted(paths):
            raise RecoveryError("the archive does not match the delivery file list")
        os.replace(temporary, final)
    finally:
        if temporary.exists():
            temporary.unlink()
    info = final.lstat()
    if not stat_module.S_ISREG(info.st_mode):
        raise RecoveryError("the artifact was not written as a regular file")
    return {
        "path": ARTIFACT_NAME,
        "size": info.st_size,
        "sha256": _sha256_file(final),
    }


def _read_findings(output_dir: Path) -> dict[str, list[dict[str, str]]] | None:
    """Read the validation findings the way the CLI reads them.

    The CLI parses this file whole or not at all: when it cannot be parsed the run has
    no findings, so the delivery carries no check and no warning for any severity.
    Entries are normalized rather than rejected, so a finding that is not even an object
    still reaches the verification record instead of voiding the rest of the file.
    """
    path = output_dir / FINDINGS_NAME
    try:
        if not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    findings: dict[str, list[dict[str, str]]] = {}
    for severity in FINDING_SEVERITIES:
        entries = raw.get(severity)
        findings[severity] = [
            _normalized_finding(entry, severity)
            for entry in (entries if isinstance(entries, list) else [])
        ]
    return findings


def _normalized_finding(value: object, severity: str) -> dict[str, str]:
    """One finding, in the shape the CLI's own parser produces."""
    if not isinstance(value, dict):
        return {
            "name": "(invalid)",
            "status": "invalid",
            "severity": severity,
            "detail": "validation finding is not an object",
        }
    name = value.get("name")
    status = value.get("status")
    detail = value.get("detail")
    return {
        "name": (
            name.strip() if isinstance(name, str) and name.strip() else "(unnamed)"
        ),
        "status": (
            status.strip() if isinstance(status, str) and status.strip() else severity
        ),
        "severity": severity,
        "detail": detail if isinstance(detail, str) else "",
    }


def _verification(state: str, output_dir: Path) -> dict[str, object]:
    findings = _read_findings(output_dir)
    checks: list[dict[str, object]] = []
    if findings is not None:
        for severity in FINDING_SEVERITIES:
            for finding in findings[severity]:
                check: dict[str, object] = {
                    "name": finding["name"],
                    "status": (
                        "failed"
                        if finding["severity"] in {"fatal", "repairable"}
                        else "passed"
                    ),
                }
                if finding["detail"]:
                    check["detail"] = finding["detail"]
                checks.append(check)
    return {
        "status": (
            "passed"
            if state == "Succeed"
            else "degraded"
            if state in {"SucceedWithWarnings", "Partial"}
            else "failed"
        ),
        "checks": checks,
        "warnings": _findings_warnings(findings),
    }


def _findings_warnings(findings: dict[str, list[dict[str, str]]] | None) -> list[str]:
    if not findings:
        return []
    return [
        f"{finding['name']}: {finding['detail'] or finding['status']}"
        for severity in ("repairable", "degraded")
        for finding in findings[severity]
    ]


def _yaml_body(line: str) -> str:
    """The content of one YAML line, with any trailing comment cut off."""
    quote = ""
    for index, character in enumerate(line):
        if quote:
            if character == quote:
                quote = ""
            continue
        if character in "\"'":
            quote = character
            continue
        if character == "#" and (index == 0 or line[index - 1] in " \t"):
            return line[:index].rstrip()
    return line.rstrip()


def _yaml_scalar(value: str) -> str:
    """One plain or quoted scalar, without the quotes that carried it."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        if value[0] == '"':
            return inner.replace('""', '"')
        return inner.replace("''", "'")
    return value


def _lifecycle_entry_point(config_path: Path) -> str | None:
    """Read ``common.entry_point`` out of agentkit.yaml.

    The Sandbox interpreter carries no YAML library, and the CLI writes this file from
    its own template, so this reader understands exactly what that template emits: a
    block mapping under a top-level ``common:`` key.  Anything else reports "no usable
    entry point", which is how the CLI itself treats a lifecycle config that does not
    declare one -- the delivery still comes out, marked a non-deployable partial result.
    Since the reader is deliberately narrower than YAML, a file it cannot follow is
    reported as undeclared rather than as invalid.
    """
    try:
        text = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise LifecycleConfigError(f"{error}") from error
    common_indent: int | None = None
    child_indent: int | None = None
    for line in re.split(r"\r?\n", text):
        body = _yaml_body(line)
        if not body:
            continue
        indentation = line[: len(line) - len(line.lstrip(" \t"))]
        if "\t" in indentation:
            # YAML forbids a tab where indentation belongs, and so does the CLI's parser.
            raise LifecycleConfigError("tab characters must not be used in indentation")
        indent = len(indentation)
        key, separator, value = body.partition(":")
        if not separator:
            continue
        key = key.strip()
        value = value.strip()
        if common_indent is None:
            if indent or key != "common":
                continue
            if value:
                return None
            common_indent = indent
            continue
        if indent <= common_indent:
            return None
        if child_indent is None:
            child_indent = indent
        if key != "entry_point" or indent != child_indent:
            continue
        if not value or value[0] in "{[":
            return None
        return _yaml_scalar(value).strip() or None
    return None


def _deliverable_module(output_dir: Path, module: str) -> str | None:
    """Return the module's path inside the project, or None when it is not there."""
    if not module:
        return None
    candidate = (output_dir / module).resolve()
    root = output_dir.resolve()
    if candidate == root or not candidate.is_relative_to(root):
        return None
    try:
        info = candidate.lstat()
    except OSError:
        return None
    if not stat_module.S_ISREG(info.st_mode) or stat_module.S_ISLNK(info.st_mode):
        return None
    return candidate.relative_to(root).as_posix()


def resolve_startup(output_dir: Path) -> tuple[dict[str, object], list[str]]:
    """Resolve the startup module the CLI would package, warnings included."""
    legacy = _deliverable_module(output_dir, "main.py")
    config_path = output_dir / "agentkit.yaml"
    if not config_path.is_file():
        return {"module": legacy or "main.py", "object": "app"}, []
    try:
        entry = _lifecycle_entry_point(config_path) or ""
    except LifecycleConfigError as error:
        if legacy:
            return (
                {"module": legacy, "object": "app"},
                [
                    "Invalid agentkit.yaml; packaged "
                    f"{legacy} as a non-deployable partial result: {error}"
                ],
            )
        raise RecoveryError(f"invalid migration lifecycle config: {error}") from error
    configured_module = _deliverable_module(output_dir, entry) if entry else None
    if configured_module:
        return {"module": configured_module, "object": "app"}, []
    if legacy:
        reason = (
            "agentkit.yaml common.entry_point does not identify a deliverable file; "
            if entry
            else "agentkit.yaml does not declare common.entry_point; "
        )
        return (
            {"module": legacy, "object": "app"},
            [f"{reason}packaged {legacy} as a non-deployable partial result."],
        )
    raise RecoveryError(
        "the lifecycle entry point is not part of the deliverable project: "
        f"{entry or 'agentkit.yaml'}"
    )


def environment_requirements(output_dir: Path) -> dict[str, list[str]]:
    """Mirror the CLI's `.env.example` reading exactly, name classification included."""
    example = output_dir / ".env.example"
    if not example.is_file():
        return {"required": [], "optional": []}
    required: set[str] = set()
    optional: set[str] = set()
    try:
        content = example.read_text(encoding="utf-8")
    except OSError:
        return {"required": [], "optional": []}
    for line in re.split(r"\r?\n", content):
        match = _ENVIRONMENT_LINE.match(line)
        if not match:
            continue
        name, value = match.group(1), match.group(2).strip()
        if not value or _INSECURE_ENVIRONMENT_VALUE.search(name):
            required.add(name)
        else:
            optional.add(name)
    return {
        "required": sorted(required),
        "optional": sorted(name for name in optional if name not in required),
    }


def _settled_status(delivery_dir: Path) -> dict[str, object] | None:
    status = _read_json(delivery_dir / STATUS_NAME)
    if status is None:
        return None
    if status.get("state") in SETTLED_DELIVERY_STATES:
        return status
    return None


def mirror_delivery(config: dict[str, object]) -> dict[str, object]:
    """Write the delivery the CLI would have written, and report what it wrote."""
    output_dir = Path(str(config.get("output_dir") or ""))
    delivery_dir = Path(str(config.get("delivery_dir") or ""))
    status_path = Path(str(config.get("status_path") or ""))
    run_id = str(config.get("run_id") or "")
    framework = str(config.get("framework") or "")
    source_sha256 = str(config.get("source_sha256") or "")
    provenance_sha256 = str(config.get("provenance_sha256") or "")
    if (
        not run_id
        or not framework
        or len(source_sha256) != 64
        or len(provenance_sha256) != 64
    ):
        raise RecoveryError("the recovery request is incomplete")
    if not output_dir.is_dir():
        raise RecoveryError(
            f"the migration output directory does not exist: {output_dir}"
        )
    if (
        delivery_dir.resolve() == output_dir.resolve()
        or delivery_dir.resolve().is_relative_to(output_dir.resolve())
    ):
        raise RecoveryError("the delivery directory must sit outside the project")
    settled = _settled_status(delivery_dir)
    if settled is not None:
        raise RecoveryError("the migration CLI already settled this delivery")
    _, agent_state = _read_agent_state(status_path)
    delivery_state = DELIVERY_STATE_BY_AGENT_STATE.get(agent_state)
    if delivery_state is None:
        raise RecoveryError(
            f"the agent stopped in {agent_state}, which is not a delivered project"
        )
    files = collect_delivery_files(output_dir)
    known = {str(item["path"]) for item in files}
    if REPORT_NAME not in known:
        raise RecoveryError(
            f"the migration report is not part of the project: {REPORT_NAME}"
        )
    startup, startup_warnings = resolve_startup(output_dir)
    startup_module = str(startup["module"])
    if startup_module not in known:
        raise RecoveryError(
            f"the startup module is not part of the project: {startup_module}"
        )
    verification = _verification(agent_state, output_dir)
    warnings = list(verification["warnings"])  # type: ignore[arg-type]
    if startup_warnings:
        verification["status"] = "degraded"
        verification["checks"].append(  # type: ignore[union-attr]
            *(
                {
                    "name": "startup:lifecycle_config",
                    "status": "failed",
                    "detail": detail,
                }
                for detail in startup_warnings
            )
        )
        warnings.extend(startup_warnings)
    settled_delivery_state = (
        "partial"
        if startup_warnings or agent_state == "Partial"
        else DELIVERY_STATE_BY_AGENT_STATE[agent_state]
    )
    delivery_dir.mkdir(parents=True, exist_ok=True)
    artifact = create_verified_zip(
        output_dir,
        delivery_dir,
        [str(item["path"]) for item in files],
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "cli": {
            "name": CLI_NAME,
            "version": str(config.get("cli_version") or "unknown"),
        },
        "migration": {
            "engine": "agentic",
            "framework": framework,
            "source_sha256": source_sha256,
            "provenance_sha256": provenance_sha256,
        },
        "status": settled_delivery_state,
        "files": files,
        "startup": startup,
        "environment": environment_requirements(output_dir),
        "verification": {
            "status": verification["status"],
            "checks": verification["checks"],
        },
        "warnings": warnings,
        "report": {"path": REPORT_NAME},
        "artifact": artifact,
        "created_at": _now(),
    }
    _atomic_write_json(delivery_dir / RESULT_NAME, result)
    previous = _read_json(delivery_dir / STATUS_NAME) or {}
    sequence = previous.get("sequence")
    sequence = (
        sequence + 1
        if isinstance(sequence, int) and not isinstance(sequence, bool)
        else 1
    )
    _atomic_write_json(
        delivery_dir / STATUS_NAME,
        {
            "schema_version": DELIVERY_SCHEMA_VERSION,
            "run_id": run_id,
            "sequence": sequence,
            "state": settled_delivery_state,
            "phase": DELIVERY_PHASE,
            "message": DELIVERY_MESSAGE,
            "artifact": {
                "state": "ready",
                "preview_ready": True,
                "download_ready": True,
                "deploy_ready": (
                    settled_delivery_state != "partial"
                    and verification["status"] != "failed"
                ),
            },
            "updated_at": _now(),
        },
    )
    return {
        "agent_state": agent_state,
        "status": settled_delivery_state,
        "files": len(files),
        "bytes": sum(int(item["size"]) for item in files),
        "manifest_sha256": manifest_digest(files),
        "artifact": artifact,
    }


def main(argv: list[str] | None = None) -> int:
    """Run one recovery from a JSON request file, and answer in JSON."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print(
            json.dumps({"ok": False, "error": "usage: delivery_recovery.py <config>"})
        )
        return 2
    try:
        config = json.loads(Path(arguments[0]).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as error:
        print(json.dumps({"ok": False, "error": f"unreadable request: {error}"}))
        return 2
    if not isinstance(config, dict):
        print(json.dumps({"ok": False, "error": "the request must be an object"}))
        return 2
    try:
        outcome = mirror_delivery(config)
    except RecoveryError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    except Exception as error:  # noqa: BLE001 - the caller only reads this report
        print(
            json.dumps(
                {"ok": False, "error": f"{type(error).__name__}: {error}"},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"ok": True, **outcome}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
