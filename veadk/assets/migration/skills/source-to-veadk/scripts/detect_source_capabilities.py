#!/usr/bin/env python3
"""Detect source observability and guardrail signals for AgentKit migration."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".env",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
SKIP_DIRS = {
    ".agentkit",
    ".cache",
    ".codex",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "site-packages",
    "venv",
}
MAX_FILE_BYTES = 256 * 1024
MAX_SIGNALS_PER_KIND = 40
MAX_SKILLS = 40
MAX_SKILL_RESOURCE_NAMES = 80
MAX_CONTEXT_ITEMS = 80


OBSERVABILITY_PATTERNS = {
    "opentelemetry": [
        "opentelemetry",
        "opentelemetry-sdk",
        "opentelemetry-api",
        "opentelemetry-instrumentation",
        "trace.set_tracer_provider",
        "tracerprovider(",
    ],
    "otel_exporter": [
        "otel_exporter_otlp_endpoint",
        "otel_exporter_otlp_headers",
        "otel_service_name",
        "otlp_span_exporter",
        "otlpspanexporter",
        "otlpmetricexporter",
    ],
    "apmplus": [
        "apmplus",
        "x-byteapm-appkey",
        "byteapm",
        "observability_opentelemetry_apmplus",
    ],
}

GUARDRAIL_PATTERNS = {
    "llm_shield": [
        "llm_shield",
        "llm-shield",
        "tool_llm_shield_app_id",
        "content_safety",
        "enable_llm_shield",
        "omini-shield",
    ],
    "guardrails": [
        "guardrails-ai",
        "import guardrails",
        "from guardrails",
        "guardrails.hub",
    ],
    "moderation": [
        "moderation",
        "content moderation",
        "input_moderation",
        "output_moderation",
        "sensitive_word_avoidance",
        "prompt_injection",
        "prompt injection",
        "pii",
        "presidio",
    ],
    "guardrail_text": [
        "guardrail",
    ],
}

GUARDRAIL_DEFAULT_ENABLE_CATEGORIES = {
    "guardrails",
    "llm_shield",
    "moderation",
}

EXTERNAL_SYSTEM_PATTERNS = {
    "http": ["requests.", "httpx.", "aiohttp", "fetch(", "axios.", "urllib3", "curl "],
    "database": ["sqlite3", "psycopg", "postgres", "mysql", "pymongo", "sqlalchemy", "redis"],
    "queue_or_scheduler": ["celery", "rq.", "apscheduler", "schedule.", "kafka", "rabbitmq", "pulsar"],
    "cloud": ["boto3", "volcengine", "tos", "oss2", "s3", "azure.", "google.cloud"],
    "mcp_or_tools": ["mcp", "tool_call", "function_call", "langchain.tools", "crewai", "autogen"],
}


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def iter_source_files(root: Path, excluded_roots: tuple[Path, ...] = ()):
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        if any(is_relative_to(current_path, excluded) for excluded in excluded_roots):
            dirs[:] = []
            continue
        dirs[:] = [
            dirname
            for dirname in sorted(dirs)
            if dirname not in SKIP_DIRS
            and not any(is_relative_to((current_path / dirname).resolve(), excluded) for excluded in excluded_roots)
        ]
        for filename in sorted(files):
            path = current_path / filename
            if not path.is_file():
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
                "Dockerfile",
                "requirements.txt",
                "Pipfile",
                "poetry.lock",
            }:
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path


def read_lower(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return ""


def scan_kind(root: Path, patterns: dict[str, list[str]], excluded_roots: tuple[Path, ...] = ()) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    for path in iter_source_files(root, excluded_roots):
        text = read_lower(path)
        if not text:
            continue
        for category, tokens in patterns.items():
            for token in tokens:
                if token in text:
                    try:
                        rel = path.relative_to(root).as_posix()
                    except ValueError:
                        rel = str(path)
                    signals.append({"category": category, "token": token, "file": rel})
                    break
            if len(signals) >= MAX_SIGNALS_PER_KIND:
                return signals
    return signals


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def detect_entrypoints(root: Path, excluded_roots: tuple[Path, ...] = ()) -> list[dict[str, str]]:
    entrypoints: list[dict[str, str]] = []
    for path in iter_source_files(root, excluded_roots):
        rel = rel_path(root, path)
        text = read_text(path)
        lower = text.lower()
        if path.name in {"main.py", "app.py", "server.py", "agent.py"}:
            entrypoints.append({"file": rel, "kind": "conventional_python_entrypoint", "evidence": path.name})
        if "fastapi(" in lower or "flask(" in lower or "agentkitagentserverapp" in lower:
            entrypoints.append({"file": rel, "kind": "python_web_app", "evidence": "framework app construction"})
        for match in re.finditer(r"@\w+\.(get|post|put|delete|patch|route)\(([^)]*)\)", text):
            entrypoints.append({"file": rel, "kind": "http_route", "evidence": match.group(0)[:120]})
        if 'if __name__ == "__main__"' in text or "if __name__ == '__main__'" in text:
            entrypoints.append({"file": rel, "kind": "python_main_guard", "evidence": "__main__"})
        if path.name == "package.json":
            try:
                package = json.loads(text)
            except Exception:
                package = {}
            scripts = package.get("scripts") if isinstance(package, dict) else {}
            if isinstance(scripts, dict):
                for name, command in list(scripts.items())[:12]:
                    entrypoints.append({"file": rel, "kind": "npm_script", "evidence": f"{name}: {command}"})
        if len(entrypoints) >= MAX_CONTEXT_ITEMS:
            break
    return entrypoints[:MAX_CONTEXT_ITEMS]


def detect_dependencies(root: Path) -> dict[str, object]:
    dependencies: dict[str, object] = {"python": [], "node": [], "files": []}
    requirements = root / "requirements.txt"
    if requirements.is_file():
        lines = [
            line.strip()
            for line in read_text(requirements).splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        dependencies["python"] = lines[:MAX_CONTEXT_ITEMS]
        dependencies["files"].append("requirements.txt")
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = read_text(pyproject)
        deps = re.findall(r'["\']([A-Za-z0-9_.-]+(?:[<>=!~]=?[^"\']*)?)["\']', text)
        if deps:
            existing = list(dependencies.get("python", []))
            dependencies["python"] = (existing + deps)[:MAX_CONTEXT_ITEMS]
        dependencies["files"].append("pyproject.toml")
    package_json = root / "package.json"
    if package_json.is_file():
        try:
            package = json.loads(read_text(package_json))
        except Exception:
            package = {}
        node_deps: list[str] = []
        if isinstance(package, dict):
            for key in ("dependencies", "devDependencies"):
                values = package.get(key)
                if isinstance(values, dict):
                    node_deps.extend(f"{name}@{version}" for name, version in values.items())
        dependencies["node"] = node_deps[:MAX_CONTEXT_ITEMS]
        dependencies["files"].append("package.json")
    return dependencies


def detect_env_requirements(root: Path, excluded_roots: tuple[Path, ...] = ()) -> list[dict[str, str]]:
    envs: dict[str, dict[str, str]] = {}
    patterns = [
        re.compile(r"os\.environ\[['\"]([A-Z][A-Z0-9_]{2,})['\"]\]"),
        re.compile(r"os\.environ\.get\(['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
        re.compile(r"os\.getenv\(['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
        re.compile(r"process\.env\.([A-Z][A-Z0-9_]{2,})"),
        re.compile(r"\$\{([A-Z][A-Z0-9_]{2,})(?::-[^}]*)?\}"),
    ]
    for path in iter_source_files(root, excluded_roots):
        text = read_text(path)
        for pattern in patterns:
            for match in pattern.finditer(text):
                name = match.group(1)
                envs.setdefault(name, {"name": name, "file": rel_path(root, path), "evidence": match.group(0)[:120]})
                if len(envs) >= MAX_CONTEXT_ITEMS:
                    return sorted(envs.values(), key=lambda item: item["name"])
    env_example = root / ".env.example"
    if env_example.is_file():
        for line in read_text(env_example).splitlines():
            match = re.match(r"\s*([A-Z][A-Z0-9_]{2,})=", line)
            if match:
                name = match.group(1)
                envs.setdefault(name, {"name": name, "file": ".env.example", "evidence": line[:120]})
    return sorted(envs.values(), key=lambda item: item["name"])[:MAX_CONTEXT_ITEMS]


def detect_external_systems(root: Path, excluded_roots: tuple[Path, ...] = ()) -> list[dict[str, str]]:
    systems: list[dict[str, str]] = []
    for path in iter_source_files(root, excluded_roots):
        text = read_lower(path)
        if not text:
            continue
        for category, tokens in EXTERNAL_SYSTEM_PATTERNS.items():
            for token in tokens:
                if token in text:
                    systems.append({"category": category, "token": token, "file": rel_path(root, path)})
                    break
        if len(systems) >= MAX_CONTEXT_ITEMS:
            break
    return systems[:MAX_CONTEXT_ITEMS]


def detect_skipped_files(root: Path, excluded_roots: tuple[Path, ...] = ()) -> dict[str, object]:
    skipped = {"large_files": 0, "unsupported_suffix": 0, "examples": []}
    examples: list[str] = []
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        if any(is_relative_to(current_path, excluded) for excluded in excluded_roots):
            dirs[:] = []
            continue
        dirs[:] = [dirname for dirname in sorted(dirs) if dirname not in SKIP_DIRS]
        for filename in sorted(files):
            path = current_path / filename
            if not path.is_file():
                continue
            reason = ""
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    reason = "large_files"
            except OSError:
                continue
            if not reason and path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile", "requirements.txt", "Pipfile", "poetry.lock"}:
                reason = "unsupported_suffix"
            if reason:
                skipped[reason] = int(skipped[reason]) + 1
                if len(examples) < 20:
                    examples.append(f"{rel_path(root, path)} ({reason})")
    skipped["examples"] = examples
    return skipped


def parse_skill_frontmatter(skill_md: Path) -> tuple[str, str]:
    try:
        text = skill_md.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return "", ""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return "", ""
    name = ""
    description = ""
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        normalized_key = key.strip().lower()
        normalized_value = value.strip().strip("'\"")
        if normalized_key == "name":
            name = normalized_value
        elif normalized_key == "description":
            description = normalized_value
    return name, description


def list_relative_files(path: Path, limit: int = MAX_SKILL_RESOURCE_NAMES) -> list[str]:
    if not path.is_dir():
        return []
    result: list[str] = []
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        result.append(item.relative_to(path).as_posix())
        if len(result) >= limit:
            break
    return result


def detect_source_skills(root: Path, excluded_roots: tuple[Path, ...] = ()) -> list[dict[str, object]]:
    skills: list[dict[str, object]] = []
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        if any(is_relative_to(current_path, excluded) for excluded in excluded_roots):
            dirs[:] = []
            continue
        dirs[:] = [
            dirname
            for dirname in sorted(dirs)
            if dirname not in SKIP_DIRS
            and not any(is_relative_to((current_path / dirname).resolve(), excluded) for excluded in excluded_roots)
        ]
        if "SKILL.md" not in files:
            continue
        skill_dir = current_path
        skill_md = skill_dir / "SKILL.md"
        name, description = parse_skill_frontmatter(skill_md)
        rel_dir = skill_dir.relative_to(root).as_posix()
        references = list_relative_files(skill_dir / "references")
        assets = list_relative_files(skill_dir / "assets")
        scripts = list_relative_files(skill_dir / "scripts")
        config = list_relative_files(skill_dir / "config")
        path_parts = set(Path(rel_dir).parts)
        if ".codebuddy" in path_parts:
            source_type = "codebuddy"
        else:
            source_type = "generic"
        skills.append(
            {
                "name": name or skill_dir.name,
                "description": description,
                "path": rel_dir,
                "source_type": source_type,
                "directory_name_matches": not name or name == skill_dir.name,
                "has_references": bool(references),
                "has_assets": bool(assets),
                "has_scripts": bool(scripts),
                "has_config": bool(config),
                "references": references,
                "assets": assets,
                "scripts": scripts,
                "config": config,
            }
        )
        if len(skills) >= MAX_SKILLS:
            break
    return skills


def detect(root: Path, excluded_roots: tuple[Path, ...] = ()) -> dict:
    observability_signals = scan_kind(root, OBSERVABILITY_PATTERNS, excluded_roots)
    guardrail_signals = scan_kind(root, GUARDRAIL_PATTERNS, excluded_roots)
    source_skills = detect_source_skills(root, excluded_roots)
    entrypoints = detect_entrypoints(root, excluded_roots)
    dependencies = detect_dependencies(root)
    env_requirements = detect_env_requirements(root, excluded_roots)
    external_systems = detect_external_systems(root, excluded_roots)
    skipped_files = detect_skipped_files(root, excluded_roots)
    default_enable_llm_shield = any(
        signal.get("category") in GUARDRAIL_DEFAULT_ENABLE_CATEGORIES
        for signal in guardrail_signals
    )
    return {
        "schema_version": 1,
        "source_dir": str(root),
        "observability": {
            "detected": bool(observability_signals),
            "default_enable_apmplus": True,
            "signals": observability_signals,
        },
        "guardrails": {
            "detected": bool(guardrail_signals),
            "default_enable_llm_shield": default_enable_llm_shield,
            "signals": guardrail_signals,
        },
        "skills": {
            "detected": bool(source_skills),
            "items": source_skills,
        },
        "source_context": {
            "entrypoints": entrypoints,
            "dependencies": dependencies,
            "env_requirements": env_requirements,
            "external_systems": external_systems,
            "skipped_files": skipped_files,
        },
    }


def main(argv: list[str]) -> int:
    if len(argv) not in {2, 3}:
        print("usage: detect_source_capabilities.py <source-dir> [output-json]", file=sys.stderr)
        return 2
    root = Path(argv[1]).resolve()
    if not root.is_dir():
        print(f"source directory does not exist: {root}", file=sys.stderr)
        return 2
    excluded_roots: list[Path] = []
    output_dir = os.environ.get("AGENTKIT_MIGRATE_OUTPUT_DIR")
    if output_dir:
        resolved_output_dir = Path(output_dir).resolve()
        if is_relative_to(resolved_output_dir, root):
            excluded_roots.append(resolved_output_dir)
    result = detect(root, tuple(excluded_roots))
    if excluded_roots:
        result["excluded_dirs"] = [str(path) for path in excluded_roots]
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if len(argv) == 3:
        output = Path(argv[2])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
