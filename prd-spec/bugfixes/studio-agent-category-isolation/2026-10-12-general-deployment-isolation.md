# General deployment and MPA isolation

## Background and scope

At `812faadf`, ProjectPreview treats every AgentDraft as MPA, CustomCreate sends `agentCategory: mpa` and applies Profile after every structured deployment, and MyAgents includes every draft in both category lists. This can mislabel generic Runtime resources and invoke unsupported MPA APIs. Restore the pre-MPA generic build/deploy/publish flow while retaining existing scaling, evaluation and GitHub options. Preserve dedicated MPA creation and explicit MPA editing.

## Requirements, design and acceptance

- R1: New structured/YAML creation defaults to general. Draft presence, names, model, skills, delegation and quick/traditional surface never imply MPA.
- R2: Existing targets persist `agentCategory` from the selected Runtime or explicit MPA entry. Explicit category wins; legacy `mpaProfileOnly: true` remains MPA, otherwise default to general. An instance ID alone is insufficient.
- R3: Pass category into ProjectPreview and gate both CustomCreate deployment paths. Only MPA executes Profile/smoke and reports those phases in initial, success, error and retry task state. Preserve ordinary deployment, cancellation and errors.
- R4: Filter local drafts using the same rules before merging server-filtered Runtime results. Preserve ownership, region and search filtering, including after draft restoration.
- R5: MpaCreateDialog and managed creation APIs remain unchanged. Do not change chat or migrate existing cloud labels automatically.

Generic deployment must send general, complete without Profile/smoke calls, and remain general after failure/retry. Explicit MPA must retain its lifecycle. Untyped old drafts belong to general; legacy Profile-only drafts belong to MPA. No unrelated cleanup or cloud resource mutation.

## Files and tasks

1. Add a category resolver and target persistence in agentDraftStorage/App.
2. Gate CustomCreate and ProjectPreview lifecycle, payload and task flags.
3. Filter MyAgents drafts.
4. Write failing category/storage and deployment regressions before implementation; correct the old test requiring every draft to be MPA.
5. Run frontend tests, build, i18n, asset and isolated browser checks; synchronize release assets and record results.

## Review and risks

See the [component contract](../../../specs/studio-mpa-control-plane/README.md). Direct design review on 2026-10-12 covers boundaries, errors/retry, security, compatibility, testability and bilingual equivalence; review-spec is unavailable. User approved implementation on 2026-10-12, requiring the original generic flow and additive MPA. Reuse existing UI with no visual redesign. No backend API changes.

Previously mislabeled Runtime resources remain mislabeled until separately verified and corrected. Old identifiers cannot reliably recover intent; untyped drafts default to general. Both preview and quick-deploy paths must use identical category rules. Preserve unrelated group permission edits and package-lock changes.

## Verification

Scope: this fix on `812faadf`, 2026-10-12.  Cloud deployment: not_run (no mutation authorized). Python checks: not_applicable (frontend scope). Commit gates: not_run (no commit requested).

### Results and implementation review

- pass: regression-first checks reproduced generic tasks being marked MPA, including failed deployments. The focused category/storage/source suite passed 24 tests after the fix.
- pass: `npm --prefix frontend test`: 1,379 Node tests and 74 component tests; includes real React handlers for ordinary preview deployment, quick creation, update with a legacy instance ID, retry, abort, ambiguous status, explicit MPA Profile failure, list switching and dedicated MPA creation regressions.
- pass: `npm --prefix frontend run build` (TypeScript and both bundles), `npm --prefix frontend run check:i18n`, `npm --prefix frontend run test:webui-assets`, and `git diff --check`. Release assets include the pre-existing group permission changes. Existing Vite warnings are not new failures.
- pass: isolated browser fixture using actual ProjectPreview/MyAgents components and simulated APIs: generic successful deployment has no MPA steps; failure/retry remains general; Escape cancels confirmation; category switching separates drafts; Chinese search and empty results work at 390×844. No cloud credentials or resource mutations used. Temporary fixture/server removed.
- not_run: live cloud deployment, browser slow-network timing and native IME composition; no cloud operation authorized, and input/loading implementation was not changed. Abort/ambiguous-status behavior is covered by component tests.
- not_applicable: Python, harness-sidecar coverage and documentation-site gates; their implementations/contracts did not change.
- not_run: pre-commit/rebase/commit/push; no commit requested.

Final review: category is carried from matching Runtime ID/region, preserved with deployment targets and used in preview, quick creation, task recovery and list filtering. Existing MPA creation APIs remain untouched. No blocking findings in the reviewed diff; existing server mislabels require separate remediation. All implementation tasks completed within the agreed frontend scope.
