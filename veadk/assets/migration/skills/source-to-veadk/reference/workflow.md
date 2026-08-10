# Required Workflow

Write `AGENTKIT_MIGRATE_STATUS_DIR/status.json` before each phase. Valid phases are `Running`, `Analysing`, `Validating`, `Succeed`, `SucceedWithWarnings`, `Partial`, and `Failed`.

1. `Running`: the CLI runner runs deterministic preflight before Codex starts:

   ```bash
   bash "$AGENTKIT_MIGRATE_ASSET_DIR/scripts/bootstrap_runtime.sh"
   python "$AGENTKIT_MIGRATE_ASSET_DIR/scripts/detect_source_capabilities.py" \
     "$AGENTKIT_MIGRATE_INPUT_DIR" \
     "$AGENTKIT_MIGRATE_SOURCE_CAPABILITIES"
   ```

   This creates a durable AgentKit Runtime skeleton and writes source capability evidence plus migration context. Codex should read `$AGENTKIT_MIGRATE_CONTEXT_MD`, `$AGENTKIT_MIGRATE_CONTEXT_JSON`, and `$AGENTKIT_MIGRATE_SOURCE_CAPABILITIES` before editing generated files.

2. `Analysing`: inspect the source deeply:
   - README and docs.
   - entrypoints, server files, CLI commands, framework config.
   - dependency files.
   - source directories, prompts, skills, knowledge assets, rules.
   - tools/scripts/MCP/HTTP/database/cloud calls.
   - request/response schemas, sessions/state, auth, logging, error handling.

   Use the deterministic capability detector output as hard evidence. Do not leave source capability evidence in `AGENTKIT_MIGRATE_OUTPUT_DIR`; summarize its result in `migration_metadata.json` and `convert_report.md`.
   If `skills.detected=true`, read `reference/adk-skill.md` before generating or editing local skill packages.

3. Establish a behavior baseline:
   - what the source agent is,
   - how users call it,
   - what it can answer or do,
   - what outputs look like,
   - what requires external systems or credentials.
   Then dynamically generate `source_behavior_contract.json` from the source evidence. Bootstrap only provides a placeholder schema; never treat it as real content and never hard-code a generic contract. This file is both Codex's migration control-plane contract and the user's validation evidence. Codex must read it back before editing `assistant/agent.py`, tools, eval cases, or reports, and every later implementation choice must map back to this contract.
   Preserve this contract conservatively:
   - Do not introduce unrelated assistant names, product names, personas, report authors, or legacy template labels that were not part of the source-visible contract.
   - Do not turn relative user times such as "昨天/今天/下午 3 点" into invented absolute dates. Ask for or carry through the user-provided time expression unless the source/user gives an exact date.
   - If the source safety contract is read-only or no-write, the migrated agent must refuse direct execution of code/config/database/service changes. It may give analysis and user-executable recommendations, but must not imply it can perform prohibited changes after "user confirmation".

4. Create and maintain `migration_plan.md` in the output directory. Keep it current while working. It must cover:
   - analysis evidence,
   - source entrypoints,
   - visible behaviors,
   - the `source_behavior_contract.json` decisions,
   - migration mapping,
   - eval cases that prove behavior preservation,
   - validation commands,
   - remaining risks.

5. Fill the bootstrapped skeleton:
   - read `source_behavior_contract.json` first,
   - replace placeholder agent behavior with source-specific behavior,
   - preserve safe deterministic source logic as VeADK tools,
   - preserve docs/prompts/runbooks as generated skills, references, or assets,
   - prefer converting source business skills using the ADK-compatible layout and `SkillToolset` wiring from `reference/adk-skill.md`; if a skill cannot be safely materialized, preserve the relevant behavior another way and report the limitation explicitly,
   - preserve unsupported external integrations as explicit tool interfaces or limitation records with exact env/config requirements.

6. Generate an eval suite:
   - `eval/cases.json`: at least 3 source-specific cases with only the AgentKit dataset fields `input` and `reference_output`.
   - `eval/rubric.md`: concise AgentKit evaluator rubric for behavior preservation, safety, and honest limitation reporting.
   - Cases must be generated from `source_behavior_contract.json` and collectively exercise the `eval_coverage` dimensions `normal_behavior`, `tool_or_capability`, and `unsupported_external_or_safety_boundary`. Keep those dimension labels in `source_behavior_contract.json` / `migration_metadata.json`, not in `eval/cases.json`.
   - The rubric must reference `{{input}}`, `{{output}}`, and `{{reference_output}}`, and must tell the judge to return a numeric score only from `1`, `0.5`, or `0` plus one short reason. Do not use PASS/PARTIAL/FAIL as the primary output.
   - Do not include real secrets or environment-specific values.

7. `Validating`: run deterministic post-step checks:

   ```bash
   bash "$AGENTKIT_MIGRATE_ASSET_DIR/scripts/validate_runtime.sh"
   ```

   If it fails, read the failure output and `validation_findings.json`, fix fatal findings first, then repairable findings best-effort, and rerun validation. Degraded findings may remain only when documented honestly. Do not call a model from the deterministic validation step.

8. Terminal states:
   - `Succeed`: no fatal or repairable findings remain.
   - `SucceedWithWarnings`: no fatal or repairable findings remain, but degraded non-blocking limitations are recorded.
   - `Partial`: runner-level best-effort fallback after repair attempts are exhausted and no fatal finding remains. Do not choose this early; keep repairing while safe progress is possible.
   - `Failed`: fatal safety, deployability, source-protection, secret, or CLI contract findings remain.
