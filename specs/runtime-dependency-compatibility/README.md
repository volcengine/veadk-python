# Runtime Dependency Compatibility

[中文版](README.zh.md)

- **Component ID:** `runtime-dependency-compatibility`
- **Status:** draft; implemented changes are governed by the related PRD
- **Revision:** 2026-10-13
- **Related PRD:** [Align package dependency metadata for Google ADK and OpenTelemetry](../../prd-spec/bugfixes/runtime-dependency-compatibility/2026-10-12-google-adk-opentelemetry-baseline.md)
- **Owned code:** `pyproject.toml`, `uv.lock`, package-metadata regression tests, and narrow ADK compatibility patches covered by the related PRD.
- **Dependent upstream:** `google-adk`, `agentkit-sdk-python`, and OpenTelemetry Python packages.

## Responsibility and non-goals

This component owns VeADK's published Python package dependency metadata and the main development lock for the Google ADK, AgentKit SDK, and OpenTelemetry compatibility line.

It does not own Studio, sandbox, generated project, managed sidecar, or Docker dependency declarations in this scoped change. Those surfaces may have their own rollout constraints and should be updated separately if needed.

## Entry points and dependencies

- Package metadata: `pyproject.toml`.
- Development lock: `uv.lock`.
- Regression coverage: tests that assert package metadata, lock metadata, and the ADK 2.7 compatibility paths named in the related PRD.
- External dependency owners: Google ADK, AgentKit SDK, and OpenTelemetry Python.

## Contract

- `CON-1`: VeADK package metadata MUST use a verified Google ADK compatibility window. For the 2026-10-13 baseline, that range is `google-adk>=2.7.0,<2.8.0`.
- `CON-2`: VeADK package metadata MUST NOT exact-pin the OpenTelemetry exporter to `1.37.0`. For the 2026-10-13 baseline, it is `opentelemetry-exporter-otlp>=1.37.0`.
- `CON-3`: VeADK package metadata MUST keep AgentKit flexible enough for fresh installs to resolve to the latest compatible AgentKit SDK. For the 2026-10-13 baseline, it is `agentkit-sdk-python>=0.8.5`.
- `CON-4`: The main `uv.lock` is a development resolver output. It SHOULD be regenerated after package metadata changes when referenced package versions are available.
- `CON-5`: Regression tests MUST check package metadata, lock metadata, and the ADK 2.7 compatibility paths affected by this change.

## Data and configuration

The source of truth for VeADK package dependencies is `pyproject.toml`. `uv.lock` records a concrete development resolution and does not directly constrain normal `pip install veadk-python` consumers.

## Security and isolation

This component must not include credentials, signed URLs, production logs, or personal data in dependency evidence. Dependency resolution may access public package indexes during verification; live cloud/provider operations are outside this contract.

## Compatibility and evolution

Changing dependency lower bounds, upper bounds, or exact pins requires a bugfix or feature PRD, resolver evidence, and affected package metadata tests. ADK `2.8.0` and later are outside the current verified window because targeted tests reproduced incompatibility on ADK `2.11.0`. Generated projects, Studio, sandbox, managed sidecar, and Docker dependency changes are outside this scoped contract and should be handled by their owning surfaces.

## Observability and failures

Failures surface as resolver errors, package metadata regressions, or lock metadata regressions. They should be reported explicitly with the package and constraint that caused the conflict.

## Verification

| Contract | Validation |
| --- | --- |
| `CON-1`, `CON-2`, `CON-3` | Package metadata regression test |
| `CON-4` | `uv lock` |
| `CON-5` | Lock metadata regression test and targeted ADK compatibility tests |

## Change record

- 2026-10-13: Scoped the component to main package metadata, the main development lock, and minimal ADK 2.7 compatibility coverage. Package metadata uses `google-adk>=2.7.0,<2.8.0`, keeps `agentkit-sdk-python>=0.8.5`, and keeps `opentelemetry-exporter-otlp>=1.37.0`.
