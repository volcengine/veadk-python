# Managed MPA creation

[中文版](README.zh.md)

VeADK prepares MPA prerequisites and deploys an agent without an `agentkit-mpa-agent` source checkout. Studio and `veadk mpa provision` use the same implementation. The deployed MPA image must support account-shared APIG registration and metadata bootstrap.

## Server setup

1. Copy the [example YAML](../../../../prd-spec/features/mpa-agent-oneclick-provision/mpa-create.config.example.yaml) to a private `mpa-create.config.yaml`. Keep filled-in configuration outside Git.
2. Supply an existing PostgreSQL instance, shared registry database, database login/owner, Runtime/worker IAM roles, images and model access. The deployment administrator needs `CREATEDB` and permission to assign the business database owner. The registry needs schema-write permissions and direct/session pooling; transaction pooling is incompatible with advisory locks.
3. Set `DEPLOYMENT_DATABASE_ADMIN_URL` and `SHARED_APIG_DATABASE_URL` in the CLI/Studio environment. These are PostgreSQL connection URLs; the YAML stores environment variable names. Flat/template secrets support complete `${ENV_NAME}` references. Do not expose these variables in browser configuration.
4. Configure deployment credentials through a rotating `managed.credential-file` or `VOLCENGINE_ACCESS_KEY` / `VOLCENGINE_SECRET_KEY` and optional `VOLCENGINE_SESSION_TOKEN`. Without an explicit file or environment key pair, the mounted `/var/run/secrets/iam/credential` is used. Each cloud call refreshes credentials; Runtime, VPC, worker and APIG use the same verified account.
5. Select a template source: `managed.from-runtime`, a private JSON `managed.template-file`, or the flat image/model/PostgreSQL fields. Reference mode removes agent-specific channel credentials and Skill Space identity. Configure `managed.worker.image` for a dedicated worker (optional `reference-id` for worker environment settings), or use an explicit `existing-id` after verifying compatibility.
6. For a private PostgreSQL host, set the reachable `managed.network.vpc-id` and `subnet-ids`. Automatic network creation does **not** configure database allowlists, peering, or cross-VPC routes. An explicit `managed.apig.adopt-id` requires that VPC ID and a compatible gateway. Otherwise the account's registered gateway is reused or created.
7. Set `VEADK_MPA_CREATE_CONFIG` to the private YAML's absolute path in the Studio process environment and start Studio normally. One profile serves its configured region; other regions display a configuration error. This path supports Volcengine.

The deployment identity needs access to AgentKit Runtime, Skill Space and Tool operations, VPC/subnet operations, APIG/IM Gateway operations and `GetCallerIdentity`. The Runtime/worker roles separately need the permissions and mounted credentials required by their images. IAM policies, PostgreSQL cloud instances, model services and network connectivity are operator prerequisites, not automatically created resources.

## Use in Studio

Choose **Agents → MPA agents → Create MPA agent**. Managers with agent-management permission can set the stable agent ID and description. Review the resource plan and submit. The workflow prepares account network/APIG/IM Gateway, a worker, an isolated business database and Skill Space, then deploys and checks Runtime and application readiness. Successful creation refreshes the directory.

The initial configuration check is local validation, **not** proof of live permissions or connectivity. Cloud identity and database permissions are checked after submission and before resource creation; each later cloud step validates its own response. Close the dialog to leave creation running, or cancel explicitly to stop orchestration. Reopen it in the same browser session to recover progress. The dialog supports keyboard operation, multiline Chinese input, both themes and narrow windows.

## CLI

```bash
veadk mpa provision --config /secure/mpa-create.config.yaml --agent-id customer-service --dry-run
veadk mpa provision --config /secure/mpa-create.config.yaml --agent-id customer-service --description "Customer service"
```

`--dry-run` validates local configuration and prints a safe plan without cloud/database calls. Actual creation can allocate billable cloud resources. Legacy `veadk mpa create` remains unchanged and does not prepare these managed prerequisites.

Managed flat mode reads image, registry name, model provider/base/key/name, PostgreSQL host/port/user/password/SSL settings, Runtime role and project. It derives a separate business database per agent; legacy `pg-database`, Tool selection, channel and OpenViking options are not implicitly applied to this mode. Use a private Runtime template for additional application environment settings, and `managed.worker` for worker selection. Bind channels after creation through Studio's MPA message channels page. An optional flat `account-id` is only an assertion against the authenticated account.

## Recovery and retained resources

Keep the same agent ID, request identity and original configuration when retrying. Shared PostgreSQL tables `mpa_account_network`, `mpa_account_apig` and `mpa_agent_deployment` retain resource identity, ownership, creation intent and client tokens. Another Studio owner cannot claim the same deployment. Native deployments without a Studio owner are not implicitly adopted; use a new agent ID. CLI-created deployments use a distinct CLI owner.

Studio stores nonsecret task state in `.adk/mpa-creation.sqlite3` (override with server-only `VEADK_MPA_TASK_DB`). Keep this file across restarts. It permits one active task per owner and four overall. Dead supervisors are reconciled on lookup/start; failed/cancelled tasks resume with the original request ID. There is no automatic task-history expiration. Browser session storage contains only the request and task identity. Server shutdown, timeout (default 1800 seconds, configurable 60–7200) or cancellation terminates and reaps the child process.

Cancellation is not cloud rollback. APIG/VPC, business database, Skill Space, worker and any Runtime already created remain for recovery; an in-flight cloud request may complete after cancellation. Do not delete shared resources to retry. Unknown create results use persisted intent and client tokens; conflicting unfinished configuration stops with an error. Success requires platform Ready **and** the application's `/readiness`. Task responses contain safe stage/error codes and resource IDs, never raw deployment logs or credentials.

See the [component contract](../../../../specs/studio-mpa-creation/README.md) and [verification record](../../../../prd-spec/features/mpa-agent-oneclick-provision/2026-09-20-studio-mpa-creation.md). Tests simulate cloud operations; live deployment requires separately supplied credentials and an isolated target.

### Runtime display names

New managed Runtime names equal the agent ID entered in Studio or supplied as `--agent-id`, for example `mi-example`. AgentKit still assigns a separate `r-...` Runtime ID. Existing Runtime names stay unchanged; the current update API has no Name parameter. Retrying unfinished legacy creation preserves the original hashed name and request token when its original inputs match. Database, worker and Skill Space naming remain scoped to the account, region and agent identity.
