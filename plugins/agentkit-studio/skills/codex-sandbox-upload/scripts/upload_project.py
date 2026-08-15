#!/usr/bin/env python3
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

"""Hand off a local Git project and continue its task in Studio."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.client
import io
import json
import mimetypes
import os
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit, urlunsplit

EXCLUDED_DIRS = {
    ".git",
    ".cache",
    ".mypy_cache",
    ".nox",
    ".nuxt",
    ".parcel-cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svelte-kit",
    ".tox",
    ".turbo",
    ".vite",
    "__pycache__",
    "coverage",
    "node_modules/.cache",
}
EXCLUDED_FILES = {".DS_Store", ".coverage"}
EXCLUDED_SUFFIXES = {".log", ".pyc", ".pyo"}
HIGH_RISK_NAMES = {
    ".env",
    ".npmrc",
    ".pypirc",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "service-account.json",
}
HIGH_RISK_SUFFIXES = {".key", ".p12", ".pfx", ".pem"}
SECRET_ASSIGNMENT = re.compile(
    rb"(?i)(?:api[_-]?key|access[_-]?key|secret[_-]?key|auth[_-]?token|password)"
    rb"\s*[:=]\s*['\"]?[A-Za-z0-9/+_.-]{12,}"
)
MAX_SCAN_BYTES = 1024 * 1024
MAX_BUNDLE_BYTES = 512 * 1024 * 1024
UPLOAD_CONNECT_ATTEMPTS = 24
UPLOAD_RETRY_DELAY_SECONDS = 5.0
SESSION_CREATE_ATTEMPTS = 6
SESSION_CREATE_RETRY_DELAY_SECONDS = 2.0
AGENT_NAME_MAX_CHARACTERS = 12
MAX_HISTORY_MESSAGES = 100
MAX_HISTORY_MESSAGE_CHARACTERS = 20_000
MAX_HISTORY_CHARACTERS = 100_000
MAX_CONTINUATION_MESSAGE_CHARACTERS = 20_000
MAX_EVENT_STREAM_LINE_BYTES = 1024 * 1024
MAX_EVENT_STREAM_DATA_BYTES = 4 * 1024 * 1024
PAIRING_CODE_PATTERN = re.compile(r"[2-9A-HJ-KM-NP-Z]{4}-?[2-9A-HJ-KM-NP-Z]{4}")
AMBIENT_BROWSER_CONTEXT = re.compile(
    r"<in-app-browser-context\b[^>]*>.*?</in-app-browser-context>",
    re.DOTALL,
)


class HandoffError(RuntimeError):
    """A user-safe project handoff failure."""


class RetryableHandoffError(HandoffError):
    """A transient request failure that is safe to retry with an idempotency key."""


def report_progress(message: str) -> None:
    """Emit a flush-safe progress line for the invoking Codex task."""
    print(f"[handoff] progress: {message}", flush=True)


@dataclass(frozen=True)
class ProjectState:
    repo: Path
    files: tuple[Path, ...]
    approximate_bytes: int
    git: bool
    branch: str
    head: str
    remote: str
    github_remote: bool
    status: str
    sensitive_paths: tuple[str, ...]
    content_warnings: tuple[str, ...]


def run_git(
    repo: Path, *args: str, check: bool = False
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
    )


def git_text(repo: Path, *args: str) -> str:
    result = run_git(repo, *args)
    if result.returncode != 0:
        return ""
    return result.stdout.decode("utf-8", errors="replace").strip()


def excluded(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    if not parts or parts[0] == ".git":
        return True
    if any(part in EXCLUDED_DIRS for part in parts):
        return True
    if any(
        "/".join(parts[index : index + 2]) in EXCLUDED_DIRS
        for index in range(len(parts) - 1)
    ):
        return True
    name = parts[-1]
    return (
        name in EXCLUDED_FILES
        or name.startswith("._")
        or any(name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES)
    )


def project_files(repo: Path, is_git: bool) -> tuple[Path, ...]:
    tracked_paths: set[str] = set()
    untracked_paths: set[str] = set()
    if is_git:
        try:
            tracked = run_git(
                repo,
                "ls-files",
                "-z",
                "--cached",
                check=True,
            )
            untracked = run_git(
                repo,
                "ls-files",
                "-z",
                "--others",
                "--exclude-standard",
                check=True,
            )
        except subprocess.CalledProcessError as error:
            raise HandoffError("cannot enumerate the Git working tree") from error
        for raw in tracked.stdout.split(b"\0"):
            if raw:
                tracked_paths.add(os.fsdecode(raw))
        for raw in untracked.stdout.split(b"\0"):
            if raw:
                untracked_paths.add(os.fsdecode(raw))
    else:
        for root, dirnames, filenames in os.walk(repo):
            root_path = Path(root)
            dirnames[:] = [
                name
                for name in dirnames
                if not excluded((root_path / name).relative_to(repo).as_posix())
            ]
            for name in filenames:
                untracked_paths.add((root_path / name).relative_to(repo).as_posix())

    output: list[Path] = []
    for relative in sorted(tracked_paths | untracked_paths):
        if relative not in tracked_paths and excluded(relative):
            continue
        candidate = repo / relative
        if candidate.exists() or candidate.is_symlink():
            output.append(candidate)
    return tuple(output)


def is_high_risk(relative: str) -> bool:
    name = PurePosixPath(relative).name.lower()
    if name in HIGH_RISK_NAMES or any(
        name.endswith(suffix) for suffix in HIGH_RISK_SUFFIXES
    ):
        return True
    return name.startswith(".env.") and name not in {
        ".env.example",
        ".env.sample",
        ".env.template",
    }


def content_has_secret(path: Path) -> bool:
    try:
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > MAX_SCAN_BYTES
        ):
            return False
        data = path.read_bytes()
    except OSError:
        return False
    if b"\0" in data[:8192]:
        return False
    return SECRET_ASSIGNMENT.search(data) is not None


def sanitize_remote(value: str) -> str:
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        host = parsed.hostname
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    return value


def is_github_remote(value: str) -> bool:
    lowered = value.lower()
    if lowered.startswith(("git@github.com:", "ssh://git@github.com/")):
        return True
    parsed = urlsplit(value)
    return parsed.hostname == "github.com"


def github_https_remote(value: str) -> str:
    if value.startswith("git@github.com:"):
        return "https://github.com/" + value.split(":", 1)[1]
    if value.startswith("ssh://git@github.com/"):
        return "https://github.com/" + value.split("ssh://git@github.com/", 1)[1]
    return value


def github_token() -> str:
    if shutil.which("gh") is None:
        raise HandoffError(
            "GitHub remote requires the gh CLI and an authenticated account"
        )
    result = subprocess.run(
        ["gh", "auth", "token", "--hostname", "github.com"],
        check=False,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if result.returncode != 0 or not token:
        raise HandoffError(
            "GitHub remote requires local authentication; run gh auth login first"
        )
    return token


def inspect_project(repo: Path) -> ProjectState:
    repo = repo.expanduser().resolve()
    if not repo.is_dir():
        raise HandoffError(f"repository directory does not exist: {repo}")
    is_git = run_git(repo, "rev-parse", "--is-inside-work-tree").returncode == 0
    files = project_files(repo, is_git)
    approximate_bytes = 0
    sensitive: list[str] = []
    content_warnings: list[str] = []
    for path in files:
        relative = path.relative_to(repo).as_posix()
        try:
            approximate_bytes += path.lstat().st_size
        except OSError:
            pass
        if is_high_risk(relative):
            sensitive.append(relative)
        elif content_has_secret(path):
            content_warnings.append(relative)
    status = (
        git_text(repo, "status", "--short", "--branch")
        if is_git
        else "not a Git repository"
    )
    remote = (
        sanitize_remote(git_text(repo, "config", "--get", "remote.origin.url"))
        if is_git
        else ""
    )
    return ProjectState(
        repo=repo,
        files=files,
        approximate_bytes=approximate_bytes,
        git=is_git,
        branch=git_text(repo, "branch", "--show-current") if is_git else "",
        head=git_text(repo, "rev-parse", "HEAD") if is_git else "",
        remote=remote,
        github_remote=is_github_remote(remote),
        status=status,
        sensitive_paths=tuple(sensitive),
        content_warnings=tuple(content_warnings),
    )


def generated_handoff(state: ProjectState, supplied: Path | None) -> bytes:
    existing = b""
    source = supplied
    if source is None:
        candidate = state.repo / "HANDOFF.md"
        source = candidate if candidate.is_file() else None
    if source is not None:
        try:
            existing = source.expanduser().read_bytes().rstrip() + b"\n\n"
        except OSError as error:
            raise HandoffError(f"cannot read handoff file: {source}") from error
    timestamp = (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    status = state.status or "clean"
    text = f"""# Studio Project Handoff

Generated: {timestamp}

## Source state

- Project: {state.repo.name}
- Branch: {state.branch or "detached or unavailable"}
- HEAD: {state.head or "unavailable"}
- Remote: {state.remote or "unavailable"}

```text
{status}
```

## Transfer boundary

This snapshot contains tracked and non-ignored project files plus working-tree changes. Repository `AGENTS.md` files are ordinary project files and remain in place. Codex system or developer prompts, reasoning, tool logs, databases, global configuration, Skills, and SSH keys were not transferred. Sanitized user-visible conversation history and GitHub authentication, when enabled, travel through separate ephemeral payloads and are not embedded in this snapshot.
"""
    return existing + text.encode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_symlink(path: Path, repo: Path) -> bool:
    if not path.is_symlink():
        return True
    target = Path(os.readlink(path))
    if target.is_absolute():
        return False
    resolved = (path.parent / target).resolve(strict=False)
    return resolved == repo or repo in resolved.parents


def add_project_archive(state: ProjectState, destination: Path, handoff: bytes) -> None:
    with tarfile.open(destination, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path in state.files:
            relative = path.relative_to(state.repo).as_posix()
            if relative == "HANDOFF.md":
                continue
            if not safe_symlink(path, state.repo):
                raise HandoffError(f"refusing to archive external symlink: {relative}")
            archive.add(path, arcname=relative, recursive=False)
        info = tarfile.TarInfo("HANDOFF.md")
        info.size = len(handoff)
        info.mode = 0o644
        info.mtime = int(dt.datetime.now(dt.timezone.utc).timestamp())
        archive.addfile(info, io.BytesIO(handoff))


RESTORE_SCRIPT = r"""#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

def safe_extract(archive_path, destination):
    destination = destination.resolve()
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            target = (destination / member.name).resolve()
            if destination != target and destination not in target.parents:
                raise RuntimeError(f"unsafe archive member: {member.name}")
            if member.isdev():
                raise RuntimeError(f"unsupported archive member: {member.name}")
            if member.issym() or member.islnk():
                link = Path(member.linkname)
                if link.is_absolute():
                    raise RuntimeError(f"unsafe archive link: {member.name}")
                resolved_link = (target.parent / link).resolve()
                if destination != resolved_link and destination not in resolved_link.parents:
                    raise RuntimeError(f"unsafe archive link: {member.name}")
        archive.extractall(destination, members=members)
    return len(members)

def install_github_credentials(source, repo):
    if source is None:
        return False
    source = Path(source)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
        if value.get("host") != "github.com":
            raise RuntimeError("unsupported GitHub credential host")
        username = value.get("username") or "x-access-token"
        token = value.get("token") or ""
        if not token:
            raise RuntimeError("GitHub credential payload is empty")

        helper_dir = Path.home() / ".config" / "agentkit-studio"
        helper_dir.mkdir(parents=True, exist_ok=True)
        token_path = helper_dir / "github-token"
        token_path.write_text(token + "\n", encoding="utf-8")
        token_path.chmod(0o600)
        helper_path = helper_dir / "github-credential-helper.sh"
        helper_path.write_text(
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = get ]; then\n"
            f"  printf '%s\\n' 'username={username}'\n"
            "  printf 'password='\n"
            f"  cat '{token_path}'\n"
            "fi\n",
            encoding="utf-8",
        )
        helper_path.chmod(0o700)

        gh_dir = Path.home() / ".config" / "gh"
        gh_dir.mkdir(parents=True, exist_ok=True)
        hosts = gh_dir / "hosts.yml"
        hosts.write_text(
            "github.com:\n"
            "    git_protocol: https\n"
            "    users:\n"
            f"        {username}:\n"
            f"    user: {username}\n"
            f"    oauth_token: {token}\n",
            encoding="utf-8",
        )
        hosts.chmod(0o600)
        if (repo / ".git").exists():
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "config",
                    "credential.https://github.com.helper",
                    f"!{helper_path}",
                ],
                check=True,
            )
        return True
    finally:
        source.unlink(missing_ok=True)

parser = argparse.ArgumentParser()
parser.add_argument("--stage", required=True)
parser.add_argument("--repo", required=True)
parser.add_argument("--github-credentials")
args = parser.parse_args()
stage = Path(args.stage).resolve()
repo = Path(args.repo).resolve()
if len(repo.parts) < 3 or str(repo) in {"/", "/home", "/home/gem", "/workspace"}:
    raise RuntimeError("refusing unsafe remote repository path")
manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
project_archive = stage / "project.tar.gz"
if digest(project_archive) != manifest["artifacts"]["project_sha256"]:
    raise RuntimeError("project archive checksum mismatch")

bundle = stage / "repo.git.bundle"
if repo.is_symlink():
    repo.unlink()
elif repo.exists():
    shutil.rmtree(repo)
repo.parent.mkdir(parents=True, exist_ok=True)
if bundle.is_file() and shutil.which("git"):
    subprocess.run(["git", "clone", "--quiet", str(bundle), str(repo)], check=True)
    branch = manifest["git"].get("branch") or ""
    head = manifest["git"].get("head") or ""
    if branch:
        checkout = subprocess.run(
            ["git", "-C", str(repo), "checkout", "--quiet", branch],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if checkout.returncode != 0 and head:
            subprocess.run(
                ["git", "-C", str(repo), "checkout", "--quiet", "--detach", head],
                check=True,
            )
    for child in repo.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
else:
    repo.mkdir(parents=True)

file_count = safe_extract(project_archive, repo)
remote = manifest["git"].get("remote") or ""
if remote and (repo / ".git").exists():
    subprocess.run(
        ["git", "-C", str(repo), "remote", "set-url", "origin", remote], check=False
    )
github_auth = install_github_credentials(args.github_credentials, repo)
status = ""
if (repo / ".git").exists():
    result = subprocess.run(
        ["git", "-C", str(repo), "status", "--short", "--branch"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    status = result.stdout.strip()
print(
    json.dumps(
        {
            "restored": True,
            "repo": str(repo),
            "fileCount": file_count,
            "gitStatus": status,
            "githubAuth": github_auth,
        },
        ensure_ascii=False,
    )
)
"""


def create_git_bundle(state: ProjectState, destination: Path) -> bool:
    if not state.git or not state.head:
        return False
    result = run_git(state.repo, "bundle", "create", str(destination), "--all")
    return result.returncode == 0 and destination.is_file()


def write_github_credentials(destination: Path, token: str) -> None:
    destination.write_text(
        json.dumps(
            {"host": "github.com", "username": "x-access-token", "token": token},
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    destination.chmod(0o600)


def build_bundle(
    state: ProjectState,
    project_name: str,
    handoff_file: Path | None,
    work: Path,
    github_credentials: bool,
) -> Path:
    project_archive = work / "project.tar.gz"
    add_project_archive(state, project_archive, generated_handoff(state, handoff_file))
    git_bundle = work / "repo.git.bundle"
    has_git_bundle = create_git_bundle(state, git_bundle)
    file_count = len(state.files) - int((state.repo / "HANDOFF.md") in state.files) + 1
    manifest = {
        "schemaVersion": 1,
        "kind": "studio-project-handoff",
        "projectName": project_name,
        "createdAt": (
            dt.datetime.now(dt.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "git": {
            "branch": state.branch,
            "head": state.head,
            "remote": (
                github_https_remote(state.remote)
                if github_credentials and state.github_remote
                else state.remote
            ),
        },
        "transfer": {
            "fileCount": file_count,
            "approximateSourceBytes": state.approximate_bytes,
            "includes": [
                "tracked files",
                "non-ignored untracked files",
                "working-tree changes",
                "AGENTS.md",
                "HANDOFF.md",
            ],
            "excludes": [
                "ignored files",
                "Codex runtime state",
                "global Skills",
                "SSH keys",
                "global configuration",
            ],
            "githubCredentials": "ephemeral separate payload"
            if github_credentials
            else "not transferred",
        },
        "artifacts": {
            "project_sha256": sha256(project_archive),
            "gitBundle": has_git_bundle,
        },
    }
    (work / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (work / "restore_project.py").write_text(RESTORE_SCRIPT, encoding="utf-8")
    bundle = work / f"{slug(project_name)}-handoff.tar.gz"
    with tarfile.open(bundle, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for name in ("manifest.json", "project.tar.gz", "restore_project.py"):
            archive.add(work / name, arcname=name, recursive=False)
        if has_git_bundle:
            archive.add(git_bundle, arcname="repo.git.bundle", recursive=False)
    if bundle.stat().st_size > MAX_BUNDLE_BYTES:
        raise HandoffError(
            f"handoff bundle exceeds {MAX_BUNDLE_BYTES // (1024 * 1024)} MiB"
        )
    return bundle


def slug(value: str) -> str:
    output = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    return output[:80] or "project"


def agent_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    if not cleaned:
        raise HandoffError(
            "--agent-name is required; let Codex create a concise task description"
        )
    if len(cleaned) > AGENT_NAME_MAX_CHARACTERS:
        raise HandoffError(
            f"--agent-name must be at most {AGENT_NAME_MAX_CHARACTERS} characters"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in cleaned):
        raise HandoffError("--agent-name contains unsupported control characters")
    return cleaned


def visible_message(value: str) -> str:
    cleaned = AMBIENT_BROWSER_CONTEXT.sub("", value).strip()
    marker = "## My request:"
    if marker in cleaned:
        cleaned = cleaned.rsplit(marker, 1)[1].strip()
    return cleaned


def conversation_history(source: Path | None) -> list[dict[str, str]]:
    if source is None:
        raise HandoffError("--history is required for a conversation handoff")
    try:
        raw = source.expanduser().read_text(encoding="utf-8")
    except OSError as error:
        raise HandoffError(f"cannot read conversation history: {source}") from error
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HandoffError("conversation history is not valid JSON") from error
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise HandoffError("conversation history must use schemaVersion 1")
    raw_messages = value.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise HandoffError("conversation history must contain visible messages")
    if len(raw_messages) > MAX_HISTORY_MESSAGES:
        raise HandoffError(
            f"conversation history exceeds {MAX_HISTORY_MESSAGES} messages"
        )
    messages: list[dict[str, str]] = []
    total_characters = 0
    for item in raw_messages:
        if not isinstance(item, dict):
            raise HandoffError("conversation history contains an invalid message")
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            raise HandoffError(
                "conversation history may contain only user and assistant messages"
            )
        content = visible_message(content)
        if not content:
            continue
        if len(content) > MAX_HISTORY_MESSAGE_CHARACTERS:
            raise HandoffError("conversation history contains an oversized message")
        total_characters += len(content)
        if total_characters > MAX_HISTORY_CHARACTERS:
            raise HandoffError("conversation history is too large")
        messages.append({"role": role, "content": content})
    if not messages:
        raise HandoffError("conversation history contains no visible messages")
    return messages


def continuation_message(value: str) -> str:
    message = value.strip() or "继续"
    if len(message) > MAX_CONTINUATION_MESSAGE_CHARACTERS:
        raise HandoffError("--continue-message is too large")
    if "\0" in message:
        raise HandoffError("--continue-message contains unsupported characters")
    return message


def studio_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    try:
        _ = parsed.port
    except ValueError as error:
        raise HandoffError("--studio-url contains an invalid port") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise HandoffError("--studio-url must be an HTTP(S) origin or base path")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def pairing_code(value: str) -> str:
    normalized = value.strip().upper()
    if not PAIRING_CODE_PATTERN.fullmatch(normalized):
        raise HandoffError("the one-time pairing code has an invalid format")
    compact = normalized.replace("-", "")
    return f"{compact[:4]}-{compact[4:]}"


def service_url(endpoint: str, route: str) -> str:
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HandoffError("Studio returned an invalid Sandbox endpoint")
    path = parsed.path.rstrip("/") + route
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def tls_context() -> ssl.SSLContext:
    """Build a verified TLS context that also trusts the macOS keychain."""
    context = ssl.create_default_context()
    if sys.platform != "darwin":
        return context
    security = shutil.which("security")
    if not security:
        return context
    certificate_data = bytearray()
    for keychain in (
        "",
        "/Library/Keychains/System.keychain",
        "/System/Library/Keychains/SystemRootCertificates.keychain",
    ):
        command = [security, "find-certificate", "-a", "-p"]
        if keychain:
            command.append(keychain)
        certificates = subprocess.run(
            command,
            capture_output=True,
            check=False,
        )
        if certificates.returncode == 0:
            certificate_data.extend(certificates.stdout)
    if b"-----BEGIN CERTIFICATE-----" in certificate_data:
        context.load_verify_locations(
            cadata=certificate_data.decode("utf-8", errors="replace")
        )
    return context


def connection(url: str) -> tuple[http.client.HTTPConnection, str]:
    parsed = urlsplit(url)
    host = parsed.hostname
    if not host:
        raise HandoffError("invalid service URL")
    if parsed.scheme == "https":
        client: http.client.HTTPConnection = http.client.HTTPSConnection(
            host,
            parsed.port or 443,
            timeout=330,
            context=tls_context(),
        )
    elif parsed.scheme == "http":
        client = http.client.HTTPConnection(host, parsed.port or 80, timeout=330)
    else:
        raise HandoffError("service URL must use http or https")
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    return client, target


def response_json(response: http.client.HTTPResponse, action: str) -> dict[str, Any]:
    raw = response.read()
    try:
        value = json.loads(raw.decode("utf-8", errors="replace")) if raw else {}
    except json.JSONDecodeError as error:
        raise HandoffError(
            f"{action} returned an invalid response (HTTP {response.status})"
        ) from error
    if response.status < 200 or response.status >= 300:
        detail = value.get("detail") if isinstance(value, dict) else None
        retryable = False
        if isinstance(detail, dict):
            retryable = detail.get("retryable") is True
            detail = detail.get("message") or detail.get("code")
        message = detail if isinstance(detail, str) else f"HTTP {response.status}"
        error_type = RetryableHandoffError if retryable else HandoffError
        raise error_type(f"{action} failed: {message}")
    if not isinstance(value, dict):
        raise HandoffError(f"{action} returned an invalid response")
    return value


def post_json(
    url: str,
    payload: dict[str, Any],
    action: str,
    *,
    attempts: int = 1,
    retry_delay_seconds: float = SESSION_CREATE_RETRY_DELAY_SECONDS,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    last_error: BaseException | None = None
    for attempt in range(1, max(1, attempts) + 1):
        client, target = connection(url)
        try:
            client.request(
                "POST",
                target,
                body=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                },
            )
            return response_json(client.getresponse(), action)
        except ssl.SSLCertVerificationError as error:
            raise HandoffError(
                f"{action} could not verify the service TLS certificate"
            ) from error
        except (OSError, RetryableHandoffError) as error:
            last_error = error
        finally:
            client.close()
        if attempt < attempts:
            time.sleep(retry_delay_seconds)
    if isinstance(last_error, RetryableHandoffError):
        raise last_error
    raise HandoffError(f"{action} could not connect to the service") from last_error


def post_event_stream(url: str, payload: dict[str, Any], action: str) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    client, target = connection(url)
    try:
        client.request(
            "POST",
            target,
            body=body,
            headers={
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        response = client.getresponse()
        if response.status < 200 or response.status >= 300:
            response_json(response, action)
        event_name = ""
        data_lines: list[str] = []
        data_bytes = 0
        saw_done = False
        while raw_line := response.readline():
            if len(raw_line) > MAX_EVENT_STREAM_LINE_BYTES:
                raise HandoffError(f"{action} returned an oversized event")
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line:
                data_text = "\n".join(data_lines)
                if event_name == "error":
                    try:
                        error_payload = json.loads(data_text) if data_text else {}
                    except json.JSONDecodeError:
                        error_payload = {}
                    detail = error_payload.get("message")
                    if not isinstance(detail, str) or not detail:
                        detail = "the cloud continuation failed"
                    raise HandoffError(f"{action} failed: {detail}")
                if event_name == "progress":
                    try:
                        progress_payload = json.loads(data_text) if data_text else {}
                    except json.JSONDecodeError:
                        progress_payload = {}
                    progress_message = progress_payload.get("message")
                    if isinstance(progress_message, str) and progress_message.strip():
                        report_progress(progress_message.strip())
                if event_name == "done":
                    try:
                        done_payload = json.loads(data_text) if data_text else {}
                    except json.JSONDecodeError as error:
                        raise HandoffError(
                            f"{action} returned an invalid completion event"
                        ) from error
                    if (
                        isinstance(done_payload, dict)
                        and done_payload.get("reason") == "failed"
                    ):
                        raise HandoffError(f"{action} failed in Studio")
                    saw_done = True
                    break
                event_name = ""
                data_lines = []
                data_bytes = 0
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_line = line[5:].lstrip()
                data_bytes += len(data_line.encode("utf-8"))
                if data_bytes > MAX_EVENT_STREAM_DATA_BYTES:
                    raise HandoffError(f"{action} returned an oversized event")
                data_lines.append(data_line)
        if not saw_done:
            raise HandoffError(f"{action} ended before Studio confirmed completion")
    except OSError as error:
        raise HandoffError(f"{action} could not connect to the service") from error
    finally:
        client.close()


def continue_in_studio(
    studio_url: str,
    session_id: str,
    pairing_code: str,
    history: list[dict[str, str]],
    message: str,
) -> None:
    post_event_stream(
        studio_url.rstrip("/")
        + f"/web/sandbox/codex-project-handoff/sessions/{session_id}/messages",
        {
            "pairingCode": pairing_code,
            "history": history,
            "message": message,
        },
        "Studio cloud continuation",
    )


def upload_file(endpoint: str, source: Path, destination: str) -> dict[str, Any]:
    url = service_url(endpoint, "/v1/file/upload")
    name = source.name.replace('"', "")
    last_error: OSError | None = None
    for attempt in range(1, UPLOAD_CONNECT_ATTEMPTS + 1):
        boundary = "----studio-handoff-" + uuid.uuid4().hex
        preamble = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="path"\r\n\r\n'
            f"{destination}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
            f"Content-Type: "
            f"{mimetypes.guess_type(name)[0] or 'application/octet-stream'}"
            "\r\n\r\n"
        ).encode()
        ending = f"\r\n--{boundary}--\r\n".encode("ascii")
        client, target = connection(url)
        try:
            client.putrequest("POST", target)
            client.putheader("Accept", "application/json")
            client.putheader(
                "Content-Type", f"multipart/form-data; boundary={boundary}"
            )
            client.putheader(
                "Content-Length",
                str(len(preamble) + source.stat().st_size + len(ending)),
            )
            client.endheaders()
            client.send(preamble)
            with source.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    client.send(chunk)
            client.send(ending)
            value = response_json(client.getresponse(), "Sandbox upload")
            if value.get("success") is False:
                raise HandoffError(
                    f"Sandbox upload failed: {value.get('error') or 'unknown error'}"
                )
            return value
        except ssl.SSLCertVerificationError as error:
            raise HandoffError(
                "Sandbox upload could not verify the service TLS certificate"
            ) from error
        except OSError as error:
            last_error = error
        finally:
            client.close()
        if attempt < UPLOAD_CONNECT_ATTEMPTS:
            time.sleep(UPLOAD_RETRY_DELAY_SECONDS)
    raise HandoffError(
        "Sandbox upload could not connect to the service"
    ) from last_error


def nested(value: dict[str, Any], paths: Iterable[tuple[str, ...]]) -> Any:
    for path in paths:
        current: Any = value
        for key in path:
            if not isinstance(current, dict) or key not in current:
                break
            current = current[key]
        else:
            return current
    return None


def remote_restore(
    endpoint: str,
    bundle_path: str,
    stage: str,
    repo: str,
    github_credentials_path: str | None,
) -> dict[str, Any]:
    import shlex

    command = "\n".join(
        [
            "set -eu",
            f"bundle={shlex.quote(bundle_path)}",
            f"stage={shlex.quote(stage)}",
            f"repo={shlex.quote(repo)}",
            f"github_credentials={shlex.quote(github_credentials_path or '')}",
            'cleanup() { [ -z "$github_credentials" ] || rm -f "$github_credentials"; }',
            "trap cleanup EXIT",
            'rm -rf "$stage"',
            'mkdir -p "$stage"',
            'tar -xzf "$bundle" -C "$stage"',
            'restore_output="$stage/restore-output.log"',
            "set +e",
            'if [ -n "$github_credentials" ]; then',
            '  python3 "$stage/restore_project.py" --stage "$stage" --repo "$repo" --github-credentials "$github_credentials" >"$restore_output" 2>&1 &',
            "else",
            '  python3 "$stage/restore_project.py" --stage "$stage" --repo "$repo" >"$restore_output" 2>&1 &',
            "fi",
            "restore_pid=$!",
            'while kill -0 "$restore_pid" 2>/dev/null; do',
            "  echo '[handoff] restore in progress'",
            "  sleep 5",
            "done",
            'wait "$restore_pid"',
            "restore_status=$?",
            "set -e",
            'cat "$restore_output"',
            'if [ "$restore_status" -ne 0 ]; then exit "$restore_status"; fi',
            'rm -f "$bundle"',
            'rm -rf "$stage"',
        ]
    )
    value = post_json(
        service_url(endpoint, "/v1/shell/exec"),
        {"id": "", "exec_dir": "/", "command": command},
        "Sandbox restore",
    )
    status = nested(
        value,
        (
            ("data", "status"),
            ("data", "Status"),
            ("status",),
            ("Status",),
            ("Result", "data", "status"),
            ("Result", "status"),
        ),
    )
    exit_code = nested(
        value,
        (
            ("data", "exit_code"),
            ("data", "ExitCode"),
            ("exit_code",),
            ("ExitCode",),
            ("Result", "data", "exit_code"),
            ("Result", "exit_code"),
        ),
    )
    output = nested(
        value,
        (
            ("data", "output"),
            ("data", "Output"),
            ("output",),
            ("Output",),
            ("Result", "data", "output"),
            ("Result", "output"),
        ),
    )
    if (
        value.get("success") is False
        or status in {"failed", "error"}
        or exit_code not in (None, 0, "0")
    ):
        raise HandoffError(
            f"Sandbox restore failed: {str(output or status or exit_code)[:500]}"
        )
    if not isinstance(output, str):
        output = ""
    restored: dict[str, Any] = {}
    for line in reversed(output.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and candidate.get("restored") is True:
            restored = candidate
            break
    if not restored:
        raise HandoffError("Sandbox restore completed without verification output")
    return restored


def cleanup_remote_file(endpoint: str, path: str) -> None:
    import shlex

    post_json(
        service_url(endpoint, "/v1/shell/exec"),
        {
            "id": "",
            "exec_dir": "/",
            "command": f"rm -f -- {shlex.quote(path)}",
        },
        "Sandbox credential cleanup",
    )


def cleanup_remote_artifacts(endpoint: str, paths: Iterable[str]) -> None:
    import shlex

    safe_paths = [path for path in paths if path.startswith("/") and path != "/"]
    if not safe_paths:
        return
    command = "\n".join(
        [
            "set -eu",
            *(f"rm -rf -- {shlex.quote(path)}" for path in safe_paths),
        ]
    )
    post_json(
        service_url(endpoint, "/v1/shell/exec"),
        {"id": "", "exec_dir": "/", "command": command},
        "Sandbox handoff cleanup",
    )


def preview(state: ProjectState) -> None:
    print(f"[handoff] repo: {state.repo}")
    print(f"[handoff] files: {len(state.files)}")
    print(f"[handoff] approximate bytes: {state.approximate_bytes}")
    print(f"[handoff] branch: {state.branch or 'unavailable'}")
    print(f"[handoff] HEAD: {state.head or 'unavailable'}")
    if state.github_remote:
        try:
            token = github_token()
        except HandoffError:
            print("[handoff] GitHub credentials: missing")
        else:
            print("[handoff] GitHub credentials: available via gh")
            del token
    else:
        print("[handoff] GitHub credentials: not applicable to this remote")
    if state.sensitive_paths:
        print("[handoff] high-risk files:")
        for path in state.sensitive_paths[:20]:
            print(f"  - {path}")
    if state.content_warnings:
        print("[handoff] possible secret assignments (values hidden):")
        for path in state.content_warnings[:20]:
            print(f"  - {path}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo", default=os.getcwd())
    result.add_argument("--studio-url", default=os.getenv("STUDIO_URL", ""))
    result.add_argument(
        "--pairing-code",
        default=os.getenv("AGENTKIT_STUDIO_PAIRING_CODE", ""),
    )
    result.add_argument(
        "--project-name", default=os.getenv("CODEX_PROJECT_UPLOAD_PROJECT_NAME", "")
    )
    result.add_argument(
        "--agent-name",
        default=os.getenv("CODEX_PROJECT_HANDOFF_AGENT_NAME", ""),
    )
    result.add_argument("--remote-home", default="/home/gem")
    result.add_argument("--handoff", type=Path)
    result.add_argument("--history", type=Path)
    result.add_argument(
        "--continue-message",
        default=os.getenv("CODEX_PROJECT_HANDOFF_CONTINUE_MESSAGE", "继续"),
    )
    result.add_argument("--output", type=Path)
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--yes", action="store_true")
    result.add_argument("--allow-sensitive", action="store_true")
    result.add_argument("--no-github-credentials", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    state = inspect_project(Path(args.repo))
    preview(state)
    project_name = args.project_name.strip() or state.repo.name
    display_name = agent_name(args.agent_name)
    studio_base_url = studio_url(args.studio_url) if args.studio_url.strip() else ""
    one_time_code = pairing_code(args.pairing_code) if args.pairing_code.strip() else ""
    history = conversation_history(args.history)
    continue_message = continuation_message(args.continue_message)
    print(f"[handoff] conversation messages: {len(history)}")
    github_credentials_enabled = state.github_remote and not args.no_github_credentials
    if args.dry_run:
        with tempfile.TemporaryDirectory(
            prefix="studio-project-handoff-preview-"
        ) as temporary:
            preview_bundle = build_bundle(
                state,
                project_name,
                args.handoff,
                Path(temporary),
                github_credentials_enabled,
            )
            print(f"[handoff] preview bundle bytes: {preview_bundle.stat().st_size}")
        print("[handoff] dry run only; no session was created and nothing was uploaded")
        return 0
    if not args.yes:
        raise HandoffError("live upload requires --yes after reviewing --dry-run")
    if (state.sensitive_paths or state.content_warnings) and not args.allow_sensitive:
        raise HandoffError(
            "sensitive file warnings require explicit --allow-sensitive approval"
        )
    if not args.studio_url.strip() or not args.pairing_code.strip():
        raise HandoffError("--studio-url and a one-time pairing code are required")

    credential_token = github_token() if github_credentials_enabled else ""

    output = args.output.expanduser().resolve() if args.output else None
    with tempfile.TemporaryDirectory(prefix="studio-project-handoff-") as temporary:
        work = Path(temporary)
        bundle = build_bundle(
            state,
            project_name,
            args.handoff,
            work,
            github_credentials_enabled,
        )
        credentials_file: Path | None = None
        if github_credentials_enabled:
            credentials_file = work / "github-credentials.json"
            write_github_credentials(credentials_file, credential_token)
            credential_token = ""
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundle, output)
            print(f"[handoff] retained local bundle: {output}")
        print(f"[handoff] bundle bytes: {bundle.stat().st_size}")
        handoff_id = uuid.uuid4().hex
        report_progress("正在创建云端 Session")
        session = post_json(
            studio_base_url + "/web/sandbox/codex-project-handoff/sessions",
            {
                "pairingCode": one_time_code,
                "projectName": project_name,
                "agentName": display_name,
                "remoteHome": args.remote_home,
                "handoffId": handoff_id,
            },
            "Studio session creation",
            attempts=SESSION_CREATE_ATTEMPTS,
        )
        endpoint = session.get("endpoint")
        remote_repo = session.get("remoteRepoDir")
        session_id = session.get("sessionId")
        if (
            not isinstance(endpoint, str)
            or not isinstance(remote_repo, str)
            or not isinstance(session_id, str)
        ):
            raise HandoffError("Studio created an incomplete Sandbox session")
        print(
            "[handoff] session created: "
            + json.dumps(
                {
                    "displayName": session.get("displayName") or display_name,
                    "sessionId": session_id,
                    "remoteRepoDir": remote_repo,
                },
                ensure_ascii=False,
            )
        )
        report_progress("云端 Session 已创建")
        remote_root = args.remote_home.rstrip("/")
        remote_bundle = f"{remote_root}/{slug(project_name)}-handoff.tar.gz"
        stage = f"{remote_root}/.studio-project-handoff/{slug(project_name)}-restore"
        remote_credentials: str | None = None
        if credentials_file is not None:
            remote_credentials = (
                f"{remote_root}/.studio-github-credentials-{uuid.uuid4().hex}.json"
            )
        restore_completed = False
        try:
            report_progress("正在上传项目")
            upload_file(endpoint, bundle, remote_bundle)
            if credentials_file is not None and remote_credentials is not None:
                upload_file(endpoint, credentials_file, remote_credentials)
            report_progress("正在恢复项目")
            restored = remote_restore(
                endpoint,
                remote_bundle,
                stage,
                remote_repo,
                remote_credentials,
            )
            restore_completed = True
            report_progress("项目恢复完成")
        finally:
            if not restore_completed:
                report_progress("正在清理临时文件")
                if remote_credentials:
                    try:
                        cleanup_remote_file(endpoint, remote_credentials)
                    except HandoffError:
                        pass
                try:
                    cleanup_remote_artifacts(endpoint, (remote_bundle, stage))
                except HandoffError:
                    pass
        result = {
            "displayName": session.get("displayName") or display_name,
            "sessionId": session_id,
            "remoteRepoDir": remote_repo,
            "fileCount": restored.get("fileCount"),
            "gitStatus": restored.get("gitStatus", ""),
            "githubAuth": restored.get("githubAuth", False),
            "historyMessages": len(history),
            "restored": True,
            "continued": False,
        }
        report_progress("正在发送续跑任务")
        continue_in_studio(
            studio_base_url,
            session_id,
            one_time_code,
            history,
            continue_message,
        )
        result["continued"] = True
        print("[handoff] result: " + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HandoffError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
