# Default database instrumentation exclusion

User-approved scope: branch from upstream feat/mpa-agent-oneclick-provision and inject the database instrumentation setting when creating MPA Runtime. Native MPA code and existing deployments are unchanged.

The shared build_runtime_env builder adds OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=sqlalchemy,asyncpg,psycopg,psycopg2,dbapi. Existing extra_env merge remains last-wins, including empty strings. Preview and deployment use the same builder; phase-two environment updates retain the value. No dependencies or authentication changes. Business tracing remains enabled.

Self-review: additive default, explicit override preserved, no secrets or live deployment. Update the MPA provisioning contract in both languages. Regression: verify the default and custom/empty override, run environment, CLI and Runtime tests, measure incremental coverage, then commit/push to the user's fork.

Verification: 34 environment/Runtime/CLI tests passed; modified environment builder coverage 17/17 executable lines (100%). The additive dictionary entry is verified explicitly. Pre-commit (Ruff check/format and secret scan) and Pyright passed. No cloud resource was changed.
