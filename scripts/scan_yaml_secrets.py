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

"""Reject committed YAML files that contain concrete secret values."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SENSITIVE_KEY_RE = re.compile(
    r"(?:^|[_.-])("
    r"password|passwd|pwd|secret|token|api[-_]?key|apikey|"
    r"access[-_]?key|credential|runtime[-_]?apikey"
    r")(?:$|[_.-])",
    re.IGNORECASE,
)
PLACEHOLDER_RE = re.compile(
    r"^(?:"
    r"|null|none|smoke|example|placeholder|changeme|change-me|"
    r"<[^>\r\n]+>|\$\{[A-Z0-9_]+\}|\$[A-Z0-9_]+|\{\{[^}\r\n]+\}\}|"
    r"\$\{\{\s*(?:secrets|matrix|env|github|inputs|vars)\.[^}\r\n]+\}\}"
    r")$",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(r"^[A-Za-z0-9_./+=:@%~-]{16,}$")
YAML_EXTENSIONS = {".yaml", ".yml"}
SKIP_PARTS = {".git", "node_modules", ".venv", ".ruff_cache"}
SKIP_FILE_NAMES = {"pnpm-lock.yaml"}
SAFE_KEYS = {
    "id-token",
    "persist-credentials",
    "imagePullSecrets",
    "secretKeyRef",
    "url_secret",
    "key_secret",
}


def tracked_yaml_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [
        Path(line)
        for line in result.stdout.splitlines()
        if Path(line).suffix.lower() in YAML_EXTENSIONS
    ]


def discover_yaml_files(paths: list[str]) -> list[Path]:
    if not paths:
        return tracked_yaml_files()
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(
                child
                for child in path.rglob("*")
                if child.is_file() and child.suffix.lower() in YAML_EXTENSIONS
            )
        elif path.suffix.lower() in YAML_EXTENSIONS:
            files.append(path)
    return files


def should_skip(path: Path) -> bool:
    return (
        not path.exists()
        or path.name in SKIP_FILE_NAMES
        or any(part in SKIP_PARTS for part in path.parts)
    )


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def is_safe_value(path: Path, key: str, value: str) -> bool:
    normalized = unquote(value)
    if key in SAFE_KEYS:
        return True
    if PLACEHOLDER_RE.fullmatch(normalized):
        return True
    if (
        path.name.endswith(".example.yaml")
        and normalized.startswith("<")
        and normalized.endswith(">")
    ):
        return True
    if normalized.startswith("${{") and normalized.endswith("}}"):
        return True
    return not SECRET_VALUE_RE.fullmatch(normalized)


def scan_file(path: Path) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return findings
    for line_no, line in enumerate(lines, start=1):
        match = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*:\s*(.*?)\s*(?:#.*)?$", line)
        if not match:
            continue
        key, raw_value = match.groups()
        if not SENSITIVE_KEY_RE.search(key):
            continue
        if is_safe_value(path, key, raw_value):
            continue
        findings.append((line_no, key))
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="YAML files or directories to scan")
    args = parser.parse_args(argv)

    files = sorted(
        {path for path in discover_yaml_files(args.paths) if not should_skip(path)}
    )
    failures: list[str] = []
    for path in files:
        for line_no, key in scan_file(path):
            failures.append(
                f"{path}:{line_no}: concrete value for sensitive YAML key `{key}`"
            )

    if failures:
        print(
            "YAML secret scan failed. Move real credentials to a local ignored file or env var."
        )
        for failure in failures:
            print(failure)
        return 1
    print(f"YAML secret scan passed for {len(files)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
