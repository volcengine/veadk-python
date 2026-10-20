# Lark channel binding and delivery

[中文](2026-10-15-lark-binding.zh.md)

Date: 2026-10-15. Status: implemented; local verification complete; live rollout not performed.
User approval: implement the reviewed Studio/Runtime Lark plan without changing domestic Feishu.

## Background and evidence
Studio exposes Feishu only; Runtime registration starts on Feishu and message clients use Feishu hosts. The IM Channel Gateway design section 3.3.2 explicitly registers Lark with adapter=lark and adapter_config.domain=https://open.larksuite.com. Its tables contradict examples on bot_name and incoming platform; preserve Feishu payload and verify Lark live before claiming release readiness. The old plugin provides domain-aware registration, not proof of deployed Gateway compatibility.

## Goals, scope and non-goals
Enable BytePlus Lark QR/manual binding, durable retries, account management and inbound/reply delivery. Preserve existing Feishu defaults and records. No database migration, Worker protocol change, deployment, cloud resource creation or commit is authorized by this implementation task. Lark CLI user authorization inside Worker is outside the messaging binding contract.

## Requirements and design
FR-1: Studio adds a Lark tab for BytePlus. Runtime must advertise feishuDomains containing lark and multiBotChannels containing feishu before setup is enabled. Old images display the existing upgrade error. Reuse canonical /feishu management APIs with domain=lark on new binding/manual requests; default/missing domain remains feishu. Filter account lists by persisted config.domain (missing means feishu). Always address operations by appId; preserve admin checks, no browser credential persistence, cancellation and late-response protection.
FR-2: Runtime validates domain against feishu/lark, starts and polls the selected registration host, persists domain with the durable session, rejects conflicting tenant brands for Lark authorization (domestic Feishu retains legacy tenant metadata handling) and exposes only safe brand metadata. Same-app cross-brand rebinding is rejected before provider mutations. Existing credential-equivalent registration reuse remains idempotent.
FR-3: Register Lark using adapter=lark with fixed domain=https://open.larksuite.com plus app_id/app_secret. Feishu registration payload is unchanged. Routing uses existing agent_id, Upstream and APIG. Unknown registration results retain existing uncertain/reconcile behavior, never blind retries.
FR-4: Keep storage channel=feishu for compatibility, with domain=lark as account brand. Accept lark and legacy feishu event envelopes for bound Lark bots; validate bot ownership before mapping Lark into shared Feishu execution semantics. Raw envelope/request IDs remain intact for durable dedupe and Gateway replies. Reject lark events addressed to domestic Feishu bots. Account identity, permissions and sessions stay scoped by appId/bot UUID.
FR-5: All direct message client constructors use the trusted account domain, including token, replies, cards, images/media, bot info, history and scheduled delivery. Lark uses only fixed Lark hosts; domestic read-host configuration remains unchanged. Never derive API hosts from user-supplied arbitrary URLs.

## Affected files and tasks
T-1: Runtime schemas, binding/studio/config/messages/delivery services, message/registration clients and account-specific client consumers; regression tests.
T-2: Studio RuntimeChannels, FeishuAccounts, account reader, capabilities types, localized strings, automation provider propagation and UI tests; rebuild web assets.
T-3: Update maintained channel contracts, run affected checks and review both language versions. Runtime CHANGELOG records delivery status.

## Design review
Direct review (review-spec unavailable): additive interfaces and backward defaults; no schema migration; fixed hosts; secrets excluded from public results; existing admin and Gateway auth retained; cross-brand rebinding fails closed; QR expiry/cancellation/uncertainty use existing lifecycle. User-approved plan covers these refinements. No design blockers for local implementation; live Gateway behavior remains an explicit verification prerequisite.

## Tests and acceptance
AC-1/FR-1: UI tests cover BP Lark, domestic tabs, unsupported Runtime, account filtering, request payloads, cancellation and retry.
AC-2/FR-2/FR-3: Mocked registration and real SQLite store tests verify domain persistence after recreation, tenant mismatch, idempotent registration, unchanged Feishu payload and cross-brand protection.
AC-3/FR-4/FR-5: Test Gateway Lark ingress, bot validation, reply addressing, direct-client host selection and domestic regression.
Run frontend tests/build/i18n/assets and real browser simulated flows; Runtime targeted tests then make lint/make test. Record outcomes and any baseline failures. Live QR/private/group/stream/unbind smoke requires a newly deployed Runtime image and authorized test bots; simulated checks cannot prove that deployed Gateway supports Lark.

## Risks and evidence
Gateway design tables disagree with examples; do not change domestic adapter or add undocumented required fields. Canonical storage requires consistent account-domain propagation. Release order: Runtime image then Studio. No real provider mutations; verification results follow.

## Implementation review and verification (2026-10-15)
Scope: uncommitted Lark changes on Studio `d5f9d485` and Runtime `1aa57dc`. T-1/T-2/T-3 are implemented. Direct review checked fixed provider hosts, canonical channel compatibility, per-account identity, durable recovery, cancellation/late responses, secret handling and bilingual equivalence. Only Lark authorization adds tenant-brand rejection; domestic tenant metadata behavior is preserved.

| Check | Outcome | Evidence |
| --- | --- | --- |
| Studio `npm --prefix frontend test` | pass | 1,389 Node tests and 116 React tests; final focused UI/account run: 85 passed. |
| Studio build, `check:i18n`, `test:webui-assets` | pass | Production assets rebuilt; 2 locales/21 namespaces; 113 files/350 asset references checked. |
| Studio proxy policy tests | pass | `uv run --extra dev pytest -q tests/test_mpa_channel_proxy_policy.py`: 6 passed. |
| Real browser with isolated fake API | pass | QR pending/success, manual binding, error/retry, old-image gating, account filtering, loading/cancellation, keyboard and 390-pixel layout; no real Bot requests. |
| Runtime targeted regression | pass | 304 channel/client/media/delivery tests; final domestic binding/service/Lark run: 82 passed. |
| New Lark regression against original Runtime HEAD | pass | Expected red baseline: 13 failures and 1 pass; current new suite: 14 passed. |
| Runtime `make lint` and complete `make test` | pass | 8,846 passed, 188 skipped, 431 warnings, 0 failed (419 seconds). Run through isolated `npm exec --yes --package @openai/codex@0.155.1 -- sh -c 'make lint && make test'`; no global installation/configuration change. |
| Runtime static checks | pass / fail (baseline) | F821/F811/F401 and new-test Ruff pass. Full changed-file Ruff has 39 findings versus baseline 40; Pyright has the same 27 baseline errors, with no new diagnostic categories/locations introduced. Full static gates are not clean. |
| Secret scan and whitespace | pass | Studio pre-commit gitleaks, Runtime working-diff gitleaks, separate untracked-source scan and `git diff --check`; no real credentials added. |
| Live Lark/Gateway E2E, PostgreSQL coverage, formal CI | not_run | Requires authorized test resources/new Runtime deployment or CI infrastructure; SQLite/fake API checks do not prove these. |
| Commit pre-commit/rebase gate | pass | User subsequently authorized local commits. Fetched remotes; Studio rebase on `upstream/main` and Runtime rebase on `origin/master` were already up to date. Studio `uv run --extra dev pre-commit run --all-files` passes all five hooks. Unrelated local lockfile deletions are excluded. No push authorized. |

The initial full Runtime run found three domestic tenant-brand regressions and one local Codex version mismatch. The domestic guard was narrowed and its regressions passed. The repository requires Codex 0.155.1; the app binary is 0.162.0-alpha.17.2, so the final full run uses an isolated pinned tool. Skipped tests are not counted as verified behavior. Frontend-design/ui-ux-pro-max and review-spec skills were unavailable; existing UI patterns and direct design/browser review were used. Remaining release prerequisite: build/deploy the new Runtime image, then verify Lark QR/manual authorization, private/group delivery, streaming and unbind against the actual Gateway. This change does not deploy resources.

### Subsequent live observation
The user reported “link expired” on the Lark authorization page. Runtime capabilities advertise Lark, but no completed Lark binding was observed. The failing authorization URL/session was not available for diagnosis; root cause remains unconfirmed. This local commit does not claim live QR/Gateway acceptance or resolve that report.

Post-sync commit checks: Studio full frontend tests (1,389 Node + 116 React) and 6 proxy policy tests pass; Runtime `make lint` and 372 targeted channel/client/media/delivery tests pass. The earlier 8,846-test full Runtime result applies to the unchanged production diff.
