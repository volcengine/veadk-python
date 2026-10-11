# Integrate MPA Studio changes into main

User-approved scope: bring all PolarisCzh Studio/MPA provisioning changes into superops-team main, including trace pagination added after PR #1. Base: f497cc6. Source: c17297c. Native MPA and live Runtime deployment are excluded.

The final source delta from ba781d3 to c17297c is applied to main; generated assets are rebuilt. Preserve main's channel management, user management, component library and channel encryption settings. Resolve overlapping imports and API additions additively; apply authenticated session identity before channel-specific identity handling. Documentation removes obsolete all-user cron and Agent-ID input descriptions. Existing component contracts accompany the imported features.

Self-review: all feature source files and tests are included, unrelated upstream changes retained. The download test uses FileReader for the jsdom Blob implementation. Refresh missing optional esbuild lock entries so clean installation works.

Verification: production build passed; 1214 frontend tests, 136 affected Python tests, 6 channel policy tests, 26 download tests, 6 A2A tests passed. Cron coverage: 99.71% lines and 97.18% branches. Asset check: 104 files and 248 references. Ruff/format/secrets checks passed before final staging and are rerun for delivery. No new cloud E2E or local service replacement performed for this PR. Generated vendor bundle whitespace is retained from the build output. Prior feature coverage reports remain scoped to their tests; broad client/Markdown coverage is not claimed as 95%.
