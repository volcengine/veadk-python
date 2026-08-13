#!/usr/bin/env python3
"""Smoke-test Studio code package upload/deploy workflow."""

from __future__ import annotations

import argparse
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from studio_shared_workflows import (
    SmokeError,
    StepLogger,
    StudioClient,
    deep_get,
    default_config_path,
    deploy_connect_chat,
    dry_summary,
    generated_paths,
    load_config,
    print_json,
    truthy,
    validate_config,
    verify_studio_ready,
)


DEFAULT_CONFIG = default_config_path(__file__, "code_package_upload.local.yaml")
SKIP_DIRS = {".git", ".hg", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__", "build", "dist", "node_modules", "venv"}


def extract_if_needed(path: Path) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    source = path.expanduser().resolve()
    if not source.exists():
        raise SmokeError(f"package.path does not exist: {source}")
    if source.is_dir():
        return source, None
    temp = tempfile.TemporaryDirectory(prefix="studio-code-package-")
    target = Path(temp.name) / source.stem
    target.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            archive.extractall(target)
    elif tarfile.is_tarfile(source):
        with tarfile.open(source) as archive:
            archive.extractall(target)
    else:
        temp.cleanup()
        raise SmokeError(f"Unsupported package format: {source}")
    children = [item for item in target.iterdir() if item.name != "__MACOSX"]
    if len(children) == 1 and children[0].is_dir():
        return children[0], temp
    return target, temp


def collect_files(root: Path, max_bytes: int) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        rel = "/".join(rel_parts)
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise SmokeError(f"Code package contains non-text file: {rel}") from exc
        total += len(content.encode("utf-8"))
        if total > max_bytes:
            raise SmokeError(f"Code package exceeds package.max_bytes={max_bytes}")
        files.append({"path": rel, "content": content})
    return files


def load_project(config: dict[str, Any]) -> tuple[dict[str, Any], tempfile.TemporaryDirectory[str] | None]:
    package = deep_get(config, "package", {}) or {}
    path = str(package.get("path") or "").strip()
    if not path:
        raise SmokeError("package.path is required.")
    root, temp = extract_if_needed(Path(path))
    files = collect_files(root, int(package.get("max_bytes") or 2_000_000))
    project = {
        "name": str(package.get("name") or deep_get(config, "agent.name") or root.name),
        "files": files,
    }
    paths = generated_paths(project)
    if "app.py" not in paths:
        raise SmokeError(f"Code package must contain app.py. Paths: {sorted(paths)}")
    return project, temp


def run_workflow(config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    validate_config(config)
    log = StepLogger()
    if dry_run:
        package = deep_get(config, "package", {}) or {}
        return dry_summary(
            "code package upload",
            {
                "projectName": str(package.get("name") or deep_get(config, "agent.name") or ""),
                "path": str(package.get("path") or ""),
            },
        )
    project, temp = load_project(config)
    try:
        client = StudioClient(config)
        verify_studio_ready(client, log)
        log.step("Upload existing Agent code package", "POST /web/deploy-agentkit")
        result = deploy_connect_chat(
            client,
            log,
            config,
            project,
            chat=truthy(deep_get(config, "chat.enabled"), default=True),
        )
        return {
            "success": True,
            "projectName": project["name"],
            "deployment": result["final"],
            "chat": result["chat"],
        }
    finally:
        if temp is not None:
            temp.cleanup()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    result = run_workflow(load_config(Path(args.config).expanduser().resolve()), dry_run=args.dry_run)
    print("\n=== Summary ===")
    print_json("result", result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except SmokeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
