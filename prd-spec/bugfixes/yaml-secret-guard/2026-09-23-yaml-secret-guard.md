# YAML Secret Guard Hotfix

[中文版](2026-09-23-yaml-secret-guard.zh.md)

## Metadata

- Change ID: `yaml-secret-guard`
- Created: 2026-09-23
- Revised: 2026-09-23
- Status: `implemented`
- Related component specs: no component contract change

## Background and Evidence

`examples/piagent_with_mcp/piagent-mcp-agentkit.yaml` was tracked as an AgentKit launch configuration. The file contained account-specific runtime metadata and a concrete `runtime_apikey` value. Filled launch YAML files are local runtime artifacts and must not be committed.

The repository already ignores local AgentKit launch configs through `agentkit.yaml` and `agentkit*.yaml`, but that does not protect files that were previously tracked. The existing secret scanners also did not provide a deterministic repo-local YAML rule that rejects concrete values assigned to sensitive YAML keys while allowing documented placeholders.

## Goals

- Remove the tracked PiAgent AgentKit launch YAML.
- Keep the example runnable by documenting how to create a local ignored config.
- Add a repo-local pre-commit YAML scanner that rejects concrete secret values.
- Allow safe placeholders and GitHub Actions secret references.

## Non-Goals

- No history rewrite or credential rotation.
- No change to AgentKit runtime behavior, MPA creation behavior, or public CLI contracts.
- No broad rewrite of unrelated YAML examples.

## Requirements

| ID | Requirement |
| --- | --- |
| `FR-1` | Filled AgentKit launch YAML with runtime IDs, endpoints, and API keys must not be tracked. |
| `FR-2` | YAML files with concrete values for sensitive keys such as `password`, `secret`, `token`, `api-key`, `access-key`, `credential`, or `runtime_apikey` must fail pre-commit. |
| `FR-3` | `.example.yaml` placeholders, environment references, and GitHub Actions `${{ secrets.* }}` references must remain allowed. |
| `FR-4` | The scanner must report only path, line, and key name, never the secret value. |

## Design

Delete `examples/piagent_with_mcp/piagent-mcp-agentkit.yaml`. Update the example README so operators generate a local config with `veadk agentkit config`, optionally rename it, and keep it out of Git. Existing `.gitignore` already ignores `agentkit.yaml` and `agentkit*.yaml`.

Add `scripts/scan_yaml_secrets.py` and run it from a local pre-commit hook. The script scans tracked YAML by default, or hook-provided YAML files when pre-commit passes paths. It uses key-name matching plus value-shape checks so placeholders stay valid while long concrete credential values fail.

## Affected Files

- `.pre-commit-config.yaml`
- `scripts/scan_yaml_secrets.py`
- `examples/piagent_with_mcp/README.md`
- `examples/piagent_with_mcp/piagent-mcp-agentkit.yaml`
- `prd-spec/bugfixes/yaml-secret-guard/2026-09-23-yaml-secret-guard.md`
- `prd-spec/bugfixes/yaml-secret-guard/2026-09-23-yaml-secret-guard.zh.md`

## Verification and Acceptance

| Requirement | Acceptance criterion | Command | Result |
| --- | --- | --- | --- |
| `FR-1` | The tracked launch YAML is deleted and README points to local ignored config generation. | `git status --short` and README review | `pass`: YAML is deleted; README now instructs generating a local config and keeping it out of Git. |
| `FR-2`, `FR-4` | A temporary YAML with `runtime_apikey` and a concrete value fails without printing the value. | `python3 scripts/scan_yaml_secrets.py <tmp-file>` | `pass`: scanner exits 1, reports path/line/key only, and the concrete value is absent from output. |
| `FR-3` | Placeholder and environment-reference YAML passes. | `python3 scripts/scan_yaml_secrets.py <tmp-file>` | `pass`: placeholder and `${MPA_MODEL_API_KEY}` references pass. |
| all | Pre-commit runs the new YAML hook. | `uv run --extra dev pre-commit run --all-files` | `pass`: Ruff, Ruff format, gitleaks, and YAML secret scan pass. |

## Risks and Open Questions

- This removes the tracked leaked-looking YAML from current Git state but does not rewrite repository history.
- Credential rotation, if the value was real, is an operator follow-up outside this code hotfix.

## Review and Delivery Record

- 2026-09-23: Implemented scoped deletion and YAML guard. Targeted unit tests, full YAML scan, and pre-commit passed.
