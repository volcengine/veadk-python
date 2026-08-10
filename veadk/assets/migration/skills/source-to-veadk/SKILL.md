---
name: source-to-veadk
description: Use when migrating uploaded Dify apps, CodeBuddy skill/gateway projects, existing Python agents, arbitrary source-code agents, or existing VeADK/AgentKit projects into deployable VeADK + AgentKit Runtime projects. Does NOT handle non-AgentKit deployment targets, custom container orchestrators, frameworks without a detectable agent contract, or greenfield agent creation (use veadk-agent-development for that).
---

# Source to VeADK

## Positioning

This skill is the migration orchestrator. Its job is to understand the source project, preserve the user-visible behavior that matters, and generate a deployable VeADK + AgentKit Runtime project.

It coordinates two supporting skills:

- `veadk-agent-development`: VeADK agent structure, `root_agent`, tools, memory/RAG, serving on port 8000, and deployment practices.
- `agentkit-cli`: exact AgentKit CLI behavior, deploy/invoke/log commands, auth assumptions, and troubleshooting.

Read those skills when their knowledge is needed. Do not duplicate their full command/API manuals here.

## First Principles

- Migration is not source-framework imitation. The output must be a clean VeADK + AgentKit project.
- Migration is not behavior loss. The migrated agent should keep or improve the source project's visible behavior: identity, workflow, tools, structured outputs, safety boundaries, and error explanations.
- For `any` migration, do not hard-code a framework or project. Analyze the source, infer the agent contract, then map it to standard VeADK and AgentKit patterns.
- Prefer context over control: deterministic scripts provide skeletons, evidence, safety checks, and deployment contracts; Codex owns source understanding, migration design, and best-effort behavior preservation.
- The input directory is read-only. Write generated files only to the output directory.
- Never write plaintext secrets or fake external-service success.
- Do not install source-project business dependencies in the migration sandbox.
- Use best effort to make the result deploy-ready and invoke-ready, not merely file-complete.
- Observability and guardrails are part of the migration result, not optional decoration. Preserve request/session tracing through AgentKit and agent/tool tracing through VeADK when the required environment is configured.

## Directory Contract

Resolve directories from environment variables:

- `AGENTKIT_MIGRATE_SKILL_PATH`: skills root, usually `/home/gem/.codex/skills`.
- `AGENTKIT_MIGRATE_INPUT_DIR`: uploaded source project. Read only.
- `AGENTKIT_MIGRATE_OUTPUT_DIR`: generated project. Write only here.
- `AGENTKIT_MIGRATE_STATUS_DIR`: status files for the remote job.
- `AGENTKIT_MIGRATE_ASSET_DIR`: this skill directory.
- `AGENTKIT_MIGRATE_SOURCE_CAPABILITIES`: source capability evidence generated before Codex starts.
- `AGENTKIT_MIGRATE_CONTEXT_JSON` / `AGENTKIT_MIGRATE_CONTEXT_MD`: concise runner-generated context for Codex.
- `AGENTKIT_TARGET_PROJECT`: AgentKit project for the generated `.agentkit/agentkit.yaml`; default to `default` only when unset.
- `AGENTKIT_TARGET_CLOUD_PROVIDER`: AgentKit cloud provider for the generated `.agentkit/agentkit.yaml`; preserve it when set (`volcengine` or `byteplus`).
- `AGENTKIT_TARGET_REGION`: AgentKit region for the generated `.agentkit/agentkit.yaml`; preserve it when set.

All `reference/...` paths below are relative to `source-to-veadk`.

## Required Workflow

The migration follows a phase order: `Running` → `Analysing` → `Validating` → `Succeed` / `SucceedWithWarnings` / `Partial` / `Failed`. The CLI runner bootstraps the runtime skeleton, runs the capability detector, and writes migration context before Codex starts. Codex then establishes a behavior baseline from `source_behavior_contract.json`, fills the skeleton with source-specific behavior, generates an eval suite, and validates deterministically. The runner may package a `Partial` artifact only after repair attempts are exhausted and no fatal safety/deployability/source-protection finding remains. For the full workflow, read **`reference/workflow.md`**.

When source business skills are present, also read **`reference/adk-skill.md`**. It defines how to identify project-owned skills, convert them into ADK-compatible local skill packages, mount them through `SkillToolset`, and keep script execution disabled unless an explicit safe executor boundary exists.

## Output Contract

The generated project must contain:

```text
assistant/__init__.py
assistant/agent.py
main.py
requirements.txt
Dockerfile
.dockerignore
.agentkit/agentkit.yaml
.env.example
migration_plan.md
source_behavior_contract.json
migration_metadata.json
convert_report.md
eval/cases.json
eval/rubric.md
```

Required shape:

- `assistant/agent.py` exports a VeADK `root_agent`; the agent name must be a valid Python identifier.
- `main.py` exposes `app` through `agentkit.apps.AgentkitAgentServerApp` and serves `0.0.0.0:8000`.
- `requirements.txt` includes `veadk-python>=1.0.3` and `agentkit-sdk-python>=0.7.10`.
- If the source contains business skills (`SKILL.md`, `.codebuddy/skills/*`, `skills/*`, or equivalent project-owned directories), treat them as first-class context. Prefer following `reference/adk-skill.md` and generating ADK-compatible skill packages under `skills/<skill-name>/`; the directory name should match the `name:` frontmatter, and `assistant/agent.py` should load them with `google.adk.skills.load_skill_from_dir` and mount them through `google.adk.tools.skill_toolset.SkillToolset`. Do not merely paste full skill content into the agent instruction. If a skill cannot be safely materialized, preserve the relevant behavior another way and report the limitation explicitly.
- Preserve skill `references/`, `assets/`, `scripts/`, and `config/` as skill resources when they do not contain plaintext secrets. If scripts are present, do not expose `run_skill_script` by default unless an explicit `code_executor` boundary is configured; prefer `tool_filter=["list_skills", "load_skill", "load_skill_resource"]` for read-only migrated skills.
- If `skill-creator` is available, use it only as read-only validation guidance. Running `skill-creator/scripts/quick_validate.py <generated-skill-dir>` is allowed. Do not run `init_skill.py`, `generate_openai_yaml.py`, or any command that rewrites, reinitializes, reformats, or regenerates an existing/generated business skill. Fix only minimal frontmatter/path/resource issues in the generated copy when validation reports them.
- `Dockerfile` is produced by `scripts/bootstrap_runtime.sh` from the selected cloud provider, or normalized from a CLI-managed `agentkit init` Dockerfile. Do not hand-write an unrelated Dockerfile.
- `.dockerignore` excludes migration audit/eval/intermediate files from the runtime image: `source_capabilities.json`, `source_behavior_contract.json`, `migration_metadata.json`, `migration_plan.md`, `convert_report.md`, `eval/`, `.codex/`, `.agentkit/migrate/`, `.agentkit/artifacts/`, caches, and Python bytecode.
- `.agentkit/agentkit.yaml` follows `reference/agentkit.yaml.template`, sets top-level `apmplus: true`, defaults `ENABLE_APMPLUS=true`, and places application runtime switches such as `ENABLE_APMPLUS` under `envs:`.
- Do not generate `OTEL_SERVICE_NAME` or `OTEL_RESOURCE_ATTRIBUTES`; they are not part of the migrated runtime contract.
- `.env.example` documents required env names without real values. Include `ENABLE_APMPLUS` and `ENABLE_LLM_SHIELD`; do not write empty optional APMPlus override envs or empty LLM Shield credential envs.
- All generated code files are English. `convert_report.md` may use Chinese.
- `source_behavior_contract.json` must be valid JSON. Prefer `schema_version: 1`; include source summary, entrypoints, visible behaviors, typical inputs, output contracts, tools/integrations, state/memory, external dependencies, safety boundaries, unsupported/degraded behaviors, migration mapping, and eval coverage. Source evidence arrays may use concise strings or structured JSON objects when fields such as HTTP method/path, CLI command, tool name, credential, or limitation make the contract clearer. `eval_coverage` must remain a string array containing the required behavior dimensions.
- `eval/cases.json` must be directly consumable by `agentkit eval dataset add --file eval/cases.json`; each item must contain only `input` and `reference_output`.
- `eval/rubric.md` must be directly consumable by `agentkit eval evaluator create --prompt-file eval/rubric.md`. It must use AgentKit evaluator variables `{{input}}`, `{{output}}`, and `{{reference_output}}`, and require a parseable numeric score (`1`, `0.5`, or `0`) plus a short reason.
- Do not leave legacy or compatibility shim files in the project root, such as top-level `agentkit.yaml`, `agent.py`, `${AGENTKIT_MIGRATE_APP_NAME}.py`, or `agentkit_migrated.py`. The deployable contract is `main.py` + `assistant/agent.py` + `AgentkitAgentServerApp` + `.agentkit/agentkit.yaml`.
- Do not leave migration-only intermediate files in the generated project, such as `source_capabilities.json`, `.codex/`, `.agentkit/migrate/`, `.agentkit/artifacts/`, `__pycache__/`, or `.pytest_cache/`.

Before declaring the migration complete, run deterministic validation, inspect `validation_findings.json` when present, and repair fatal or repairable findings as far as possible. Do not hide remaining degraded/repairable findings; record them in metadata and the report. `Succeed` requires no fatal/repairable findings. `SucceedWithWarnings` may contain degraded findings. `Partial` is a runner-level fallback after best-effort repair attempts, not an excuse to stop early.

## Model and Secret Rules

- Runtime model name may default from `AGENTKIT_TARGET_MODEL_ID`, `MODEL_NAME`, `codex_model`, or a deploy-time env default.
- The target model key env name comes from `AGENTKIT_TARGET_MODEL_API_KEY_ENV`; if unset, use `MODEL_AGENT_API_KEY`.
- `.agentkit/agentkit.yaml` must contain env references such as `${MODEL_AGENT_API_KEY:?set MODEL_AGENT_API_KEY before deploy}`. Never write the actual key.
- The generated agent code must read the same model key env name. If `AGENTKIT_TARGET_MODEL_API_KEY_ENV=ARK_API_KEY`, `assistant/agent.py` must read `ARK_API_KEY`; do not add an empty `MODEL_AGENT_API_KEY` alias.
- Never write real values of `MODEL_AGENT_API_KEY`, `ARK_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `codex_api_key`, or similar secrets into generated files.
- CLI-provided target deployment settings are part of the user contract:
  - If `AGENTKIT_MIGRATE_APP_NAME` is set, preserve it as `.agentkit/agentkit.yaml` `name:` after the same filename-safe normalization used by bootstrap. Source identity belongs in the agent instruction/description, not by overriding the deployment name.
  - Preserve `AGENTKIT_TARGET_PROJECT` as `.agentkit/agentkit.yaml` `project:`; do not infer it from the source project name.
  - Preserve `AGENTKIT_TARGET_CLOUD_PROVIDER` as `.agentkit/agentkit.yaml` `cloud_provider:` and `AGENTKIT_TARGET_REGION` as `.agentkit/agentkit.yaml` `region:`; do not hard-code `cn-beijing` for BytePlus migrations.
  - Preserve `AGENTKIT_TARGET_MODEL_ID` as the generated model default.
  - Preserve `AGENTKIT_TARGET_MODEL_BASE_URL` as the generated model base URL default through the canonical VeADK env `MODEL_AGENT_API_BASE`; do not write legacy `MODEL_BASE_URL` into `.agentkit/agentkit.yaml` or `.env.example`.
  - Preserve `AGENTKIT_TARGET_MODEL_API_KEY_ENV` as the deploy-time API key env name in `.agentkit/agentkit.yaml` and `.env.example`.

## Observability and Guardrails

The migrated project must support two observability layers without making observability a hard startup dependency:

- `AgentkitAgentServerApp` remains the serving boundary. It provides AgentKit request/session level OpenTelemetry spans, metrics, A2A/session visibility, and platform log correlation when runtime OTEL/APM env is configured.
- `assistant/agent.py` should preserve the bootstrap `_build_tracers()` pattern or an equivalent env-gated implementation. It must include `ENABLE_APMPLUS` and default it to `true`; users can manually turn agent tracing off after migration.
- APMPlus is an AgentKit migration runtime capability, not a source-project inference. Always default `envs.ENABLE_APMPLUS` to `true` in `.agentkit/agentkit.yaml`, set top-level `apmplus: true`, default `ENABLE_APMPLUS=true` in `.env.example`, and default the agent-side `_env_flag("ENABLE_APMPLUS", "true")`. Still record source OTEL/APM signals as evidence in metadata/report.
- Enable VeADK APMPlus tracing only when `ENABLE_APMPLUS=true` and credentials are available through one of:
  - `OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY`
  - `VOLCENGINE_ACCESS_KEY` + `VOLCENGINE_SECRET_KEY`
  - VeFaaS IAM credential file at `/var/run/secrets/iam/credential`
- `OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY`, `OBSERVABILITY_OPENTELEMETRY_APMPLUS_ENDPOINT`, and `OBSERVABILITY_OPENTELEMETRY_APMPLUS_SERVICE_NAME` are optional overrides. Do not write them to `.agentkit/agentkit.yaml` or `.env.example` when they would be empty; VeADK can use defaults and platform credentials.
- Missing observability envs must not break local validation, deploy, or invoke. If the source-detected default is enabled but envs are incomplete, log a warning and skip exporter setup.
- Record source detection signals, migrated default enabled state, and manual override envs in `migration_metadata.json` and `convert_report.md`.

Safety guardrails must be explicit and source-derived:

- `assistant/agent.py` must keep an env-gated VeADK LLM Shield callback setup. It must include `ENABLE_LLM_SHIELD` so users can manually turn guardrails on or off after migration.
- If `source_capabilities.json` reports explicit source safety runtime signals such as LLM Shield, Guardrails, moderation, PII, or prompt-injection protection, record the signal. Default `ENABLE_LLM_SHIELD` to `true` only when `TOOL_LLM_SHIELD_APP_ID` and `TOOL_LLM_SHIELD_API_KEY` are intentionally configured; otherwise default it to `false`. Weak text-only mentions must be recorded but must not enable runtime guardrails by themselves.
- Enable LLM Shield callbacks only when `ENABLE_LLM_SHIELD=true` and both `TOOL_LLM_SHIELD_APP_ID` and `TOOL_LLM_SHIELD_API_KEY` are configured. Missing guardrail envs must not break local validation, deploy, or invoke.
- Do not write empty `TOOL_LLM_SHIELD_APP_ID` or `TOOL_LLM_SHIELD_API_KEY` entries to `.agentkit/agentkit.yaml` or `.env.example`. If both credentials are configured, write them together as required deploy-time env references; `TOOL_LLM_SHIELD_REGION` may be included with a default region.
- Preserve the source project's read/write boundary. If the source is read-only, generated tools must not mutate files, databases, cloud resources, or remote services.
- For external systems without credentials/configuration, expose an honest limitation or no-op adapter; do not claim the action succeeded.
- Validate tool inputs and file paths at tool boundaries. Do not create open shell, arbitrary network, or credential-forwarding tools unless they existed in the source and have explicit safety constraints.
- Include at least one eval case or rubric dimension that checks safety-boundary behavior and honest limitation reporting.

## Behavior Report

`migration_metadata.json` and `convert_report.md` must describe:

- `behavior_contract`: source summary, entrypoints, visible behaviors, output contracts, degraded behaviors, and eval coverage from `source_behavior_contract.json`.
- `analysis_evidence`: files/directories/commands inspected.
- `source_entrypoints`: original HTTP/API/CLI/agent entrypoints.
- `visible_behaviors`: user-visible capabilities and typical inputs/outputs.
- `skills_detected`: skills, knowledge files, prompts, rules, assets, scripts, and config files found; record whether each source skill was converted to an ADK skill package and mounted through `SkillToolset`.
- `tools_detected`: scripts, SDK calls, MCP, HTTP, database, cloud, or local tools found.
- `preserved_behaviors`: what the migrated agent keeps or improves.
- `degraded_behaviors`: what cannot run without credentials, network, dependencies, or external systems, plus exact configuration needed.
- `eval_suite`: case count, behavior dimensions covered, and deploy-time eval commands.
- `post_step_validation`: deterministic validation status and checks.
- `observability`: server trace and agent trace support, source detection signals, default enabled state, manual override env vars, and whether setup is env-gated.
- `safety_guardrails`: preserved source safety boundaries, source detection signals, default enabled state, manual override env vars, LLM Shield runtime callback wiring, unsupported external-system behavior, and eval coverage.

## Runtime Instruction Safety

ADK/VeADK treats `{name}` in `instruction` as a context variable. Source docs often contain placeholders like `{id}`, `{business_id}`, `${ENV_VAR_NAME}`, SQL templates, or API path parameters.

- Do not paste raw source docs into `instruction`.
- If small source snippets must be included, escape braces with `text.replace("{", "{{").replace("}", "}}")`; for example `${ENV_VAR_NAME}` must become `${{ENV_VAR_NAME}}` or be rewritten as plain text such as `ENV_VAR_NAME`.
- Put large docs, source skills, SQL examples, and troubleshooting manuals under ADK-compatible `skills/<skill-name>/references|assets|scripts`. Mount local skills through `SkillToolset`; prompt text should only explain when to use the skill and the safety boundary.
- Keep `instruction` as control-plane context: identity, workflow, safety boundaries, tool-use rules, and key terms.

## Validation

Default post-step validation is deterministic. It checks mandatory files, Python compilation, `assistant.agent:root_agent`, `main:app`, platform dependencies in `requirements.txt`, absence of bootstrap placeholders, CLI contract preservation (`--name`, target project, target model id/base URL/API key env), absence of legacy root files or root `agent.py` shims, observability env/tracer wiring, source-detected default enable switches, behavior contract schema, eval-suite structure including behavior dimensions, safety, and honest-limitation dimensions, generated skill loadability, and read-only `skill-creator` quick validation when available. It writes `validation_findings.json` with severities:

- `fatal`: safety, deployability, source-protection, or CLI contract failures that must block packaging.
- `repairable`: behavior/report/eval/skill-quality issues Codex should fix best-effort; after attempts are exhausted they may yield `Partial` if no fatal remains.
- `degraded`: non-blocking limitations or missing optional validators.
- `info`: passed checks.

The script updates `migration_metadata.json` / `convert_report.md`.

`veadk` and `agentkit` are platform runtime dependencies. Production CodeEnv images should provide them. If the verification sandbox is missing only these platform packages, you may temporarily bootstrap:

```bash
"$PYTHON" -m pip install -U veadk-python agentkit-sdk-python
```

This exception is limited to `veadk-python`, `agentkit-sdk-python`, and their resolver-selected transitive dependencies. Record the bootstrap in `migration_metadata.json`. Never write this temporary bootstrap into generated `Dockerfile`, `requirements.txt`, `.agentkit/agentkit.yaml`, or user-facing deploy instructions.

Do not run real model calls or cloud `agentkit release` / `agentkit invoke` during default post-step validation. Cloud deploy/invoke is handled by the CLI or user workflow when explicitly requested and credentials are available.

## Final Gate

Before finishing:

- The generated project is deploy-ready with `agentkit release`.
- The generated project is invoke-ready through AgentKit server routes when dependencies and credentials are configured.
- The output keeps the source project's visible behavior as far as configuration allows.
- The source input directory was not modified.
- No plaintext secrets or environment-specific credentials were written.
- Unsupported external services are reported clearly instead of faked.
- Time, identity, and safety-boundary wording does not add facts or capabilities absent from the source.
- The implementation stays simple, readable, and aligned with VeADK and AgentKit standard usage.
