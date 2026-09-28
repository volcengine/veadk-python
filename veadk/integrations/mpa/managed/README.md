# Managed MPA creation

[中文版](README.zh.md)

VeADK prepares MPA prerequisites and deploys an agent without an `agentkit-mpa-agent` source checkout. Studio and `veadk mpa provision` use the same implementation. The deployed MPA image must support account-shared APIG registration and metadata bootstrap.

## Automatic PG setup (recommended for new installations)

Studio's built-in Beijing profile uses automatic PostgreSQL preparation; CLI users set `managed.postgres.mode: auto` in their private YAML. No PG host/user/password or PG URL environment variables are needed. Use the deployment account's rotating STS credentials with `GetCallerIdentity`, AIDAP `CreateWorkspace`, `DescribeWorkspaces`, `DescribeWorkspaceDetail`, `DescribeBranches`, `DescribeComputes`, `DescribeWorkspaceEndpoint`, `DescribeDBAccounts`, `DescribeDatabases`, and `DescribeDBAccountConnection` permissions, in addition to the existing AgentKit/VPC/APIG permissions and model/role setup. Enable AIDAP for that account and ensure the returned PostgreSQL endpoint is reachable from Studio and Runtime. This flow uses the provider's public endpoint and does not modify database network/allowlist settings.

```yaml
managed:
  version: 1
  postgres:
    mode: auto
    admin-workspace-name: mpa_admin_workspace
    business-workspace-name: mpa_business_workspace
    project-name: default
    bootstrap-path: .adk/mpa-pg-bootstrap.sqlite3
    timeout-seconds: 600
  # Keep existing runtime, worker and network options.
```

After creation submission, prepare/reuse `mpa_admin_workspace/mpa_admin_db`, then one business Workspace with a separate `mpa_agent_<hash>` database per MPA. The creation page's PG step shows an explanation instead of editable connection fields. Workspace connections are obtained server-side; flat/template/reference PG settings are ignored or overridden in auto mode. Optional `admin-workspace-id` / `business-workspace-id` adopt existing resources; scope/name/engine must match. The default engine is PostgreSQL_17. No cloud resources are allocated by configuration inspection or dry-run.

All Studio/CLI processes for a scope must use the **same durable bootstrap file path on one coordinator host**. Preserve this file across restarts and redeployments. The private SQLite file contains only intents and IDs, never passwords. Cancelled/failed jobs retain resources. If a create response is lost, retry discovers the tagged Workspace; if its outcome is still uncertain, inspect AIDAP and provide the matching ID. Do not delete state to force another creation. Confirmed IAM/parameter rejections can be retried after correction. No Workspace is automatically deleted.

### Existing installation cutover

Automatic mode refuses to run while the old shared registry URL remains configured by default. If old MPA resources may be abandoned for **new** creations, CLI users set `managed.postgres.legacy-urls: ignore` in their private YAML; Studio's built-in profile already uses this setting. Both paths then ignore `SHARED_APIG_DATABASE_URL` and `DEPLOYMENT_DATABASE_ADMIN_URL` even if they remain in the process environment. New agents start with fresh admin and business Workspaces; old agents, databases, Runtime connections and records are not changed or deleted. Do not use this setting to resume an unfinished old creation task under the same agent ID.

To preserve and migrate old relationships instead, keep the default `legacy-urls: reject` and use the following cutover. Do not simply unset the old URL on an existing installation: that would hide existing resource relationships.

1. Back up the source registry and stop **all registry writers**, including Runtime bootstrap writers, through the whole cutover.
2. Configure auto mode and explicitly adopt the current business Workspace ID and its actual `business-workspace-name`. Keep the business endpoint unchanged. PostgreSQL_17 is required. Supply the old registry URL through a private environment variable such as `OLD_SHARED_APIG_DATABASE_URL`.
3. Run `veadk mpa init-admin-db --config mpa-create.config.yaml --source-url-env OLD_SHARED_APIG_DATABASE_URL`. It prepares the Workspaces/management DB and copies registry records atomically using the migration rules below. It does not migrate business databases or alter running Runtime environments.
4. Verify copied resource bindings. Coordinate existing Runtime `SHARED_APIG_DATABASE_URL` updates to the new management database with the existing safe deployment procedure; remove the legacy registry URL from the Studio/CLI environment only after cutover is complete. Preserve old business credentials or explicitly verify the adopted connection before removing obsolete settings. Resume writers only after verification. Keep the source backup for rollback.

No live migration or cloud allocation is performed by the repository tests. See the [automatic PG design](../../../../prd-spec/features/mpa-space-scoped-resources/2026-09-23-auto-pg-workspaces.md) for limitations and verification.


## CLI YAML and manual / legacy server setup

1. Copy the [example YAML](../../../../prd-spec/features/mpa-agent-oneclick-provision/mpa-create.config.example.yaml) to a private `mpa-create.config.yaml`. Keep filled-in configuration outside Git.
2. Supply an existing PostgreSQL instance, shared registry database, database login/owner, Runtime/worker IAM roles, images and model access. The deployment administrator needs `CREATEDB` and permission to assign the business database owner. The registry needs schema-write permissions and direct/session pooling; transaction pooling is incompatible with advisory locks.
3. For manual CLI profiles, set `DEPLOYMENT_DATABASE_ADMIN_URL` and `SHARED_APIG_DATABASE_URL` in the CLI environment. These are PostgreSQL connection URLs; the YAML stores environment variable names. Flat/template secrets support complete `${ENV_NAME}` references. Do not expose these variables in browser configuration.
4. Configure deployment credentials through a rotating `managed.credential-file` or `VOLCENGINE_ACCESS_KEY` / `VOLCENGINE_SECRET_KEY` and optional `VOLCENGINE_SESSION_TOKEN`. Without an explicit file or environment key pair, the mounted `/var/run/secrets/iam/credential` is used. Each cloud call refreshes credentials; Runtime, VPC, worker and APIG use the same verified account.
5. Select a template source: `managed.from-runtime`, a private JSON `managed.template-file`, or the flat image/model/PostgreSQL fields. Reference mode removes agent-specific channel credentials and Skill Space identity. Configure `managed.worker.image` for a dedicated worker (optional `reference-id` for worker environment settings), or use an explicit `existing-id` after verifying compatibility.
6. For a private PostgreSQL host, set the reachable `managed.network.vpc-id` and `subnet-ids`. Automatic network creation does **not** configure database allowlists, peering, or cross-VPC routes. An explicit `managed.apig.adopt-id` requires that VPC ID and a compatible gateway. Otherwise the account's registered gateway is reused or created.
7. Supply the private YAML explicitly with the CLI `--config` option. Studio does not read this file or `VEADK_MPA_CREATE_CONFIG`; it uses the code-owned Beijing profile and requires `VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY` plus deployment STS credentials in its server environment. Other Studio regions display a configuration error.

The deployment identity needs access to AgentKit Runtime, Skill Space and Tool operations, VPC/subnet operations, APIG/IM Gateway operations and `GetCallerIdentity`. The Runtime/worker roles separately need the permissions and mounted credentials required by their images. IAM policies, PostgreSQL cloud instances, model services and network connectivity are operator prerequisites, not automatically created resources.

## Manual two-Workspace configuration

Pre-create both Workspaces in the [AIDAP console](https://console.volcengine.com/aidap/region:aidap+cn-beijing/):

```text
mpa_admin_workspace
└── mpa_admin_db
    ├── mpa_account_network
    ├── mpa_account_apig
    └── mpa_agent_deployment
business Workspace (reuse the current Workspace)
├── mpa_agent_<agent-A-hash>
└── mpa_agent_<agent-B-hash>
```

For manual mode, adapt the example YAML using `managed.postgres.mode: manual`. Set `admin-workspace-name: mpa_admin_workspace`, the actual `admin-workspace-id` and `business-workspace-id`, and `admin-database-url-env: MPA_ADMIN_DATABASE_ADMIN_URL`. The two IDs and hosts must differ; the management connection must use database `mpa_admin_db`. Verify IDs and endpoint ownership in the console: local validation does not query AIDAP or prove cloud ownership. Omitting `managed.postgres` retains legacy behavior.

| Server environment variable | Destination and use |
| --- | --- |
| `DEPLOYMENT_DATABASE_ADMIN_URL` | Business Workspace, existing maintenance database; creates per-agent business databases. |
| `SHARED_APIG_DATABASE_URL` | Management Workspace, `mpa_admin_db`; registry login/owner with schema access and session pooling. |
| `MPA_ADMIN_DATABASE_ADMIN_URL` | Management Workspace, an existing maintenance database such as `aidb`; only used by `init-admin-db`, with `CREATEDB` and permission to assign the registry owner. |

Keep flat `pg-host`, `pg-user`, `pg-password` and template/runtime PG settings on the **business** Workspace. The management maintenance credential does not enter Runtime. The existing MPA image still receives `SHARED_APIG_DATABASE_URL` for registry bootstrap; this change does not redesign its permissions or add per-agent database users. No Workspace is created or deleted automatically. Normal creation requires the management database to exist and never creates an empty replacement silently.

For a fresh installation:

```bash
veadk mpa init-admin-db --config /secure/mpa-create.config.yaml
```

For an existing installation, **copy the old shared registry before cutover**:

1. Back up the old registry. Finish or reconcile pending Runtime deployments using the original configuration first: the copy rejects `pending` records because their idempotency hashes include the old shared URL. Stop Studio creation jobs and all Runtime/channel processes that can write registry records; keep them stopped through the endpoint switch. Retain business PG addresses, database names, credentials and data.
2. Configure the new private profile and environment variables above. Put the old shared connection in `OLD_SHARED_APIG_DATABASE_URL`. The source credential needs SELECT and SHARE table-lock privileges on the three tables. Do not pass a URL as a command-line argument.
3. Run:

   ```bash
   veadk mpa init-admin-db --config /secure/mpa-create.config.yaml --source-url-env OLD_SHARED_APIG_DATABASE_URL
   ```

4. The command verifies the destination owner and rejects unrelated public objects. It copies only the three tables, preserving complete JSON records and identities. An identical rerun is safe; conflicting/extra target records abort the entire copy transaction. The source receives no writes. The target database may remain after failure; retry after resolving the cause. Lock/statement limits are 5/30 seconds; the overall limit is 120 seconds.
5. Verify returned table counts and resource identities. Change the Studio/CLI shared URL and explicitly roll out the new `SHARED_APIG_DATABASE_URL` to existing MPA Runtimes before restoring writers. New deployments receive it automatically; this command does not update existing Runtimes. Keep their business PG settings unchanged and verify Runtime, channel and creation readiness.
6. Retain the source for recovery. Before any writes to the new registry, rollback can restore the old URL to **all** consumers. After new writes, reconcile registries before rollback; never switch consumers independently or delete shared resources to retry.

VPC/APIG still share by account and region. Deployment JSON records retain both Workspace IDs; changed bindings or existing business endpoints are rejected on retry before cloud writes. Business database naming and ownership checks remain unchanged. Copying these tables does not migrate business data or update Runtime images.

## Use in Studio

After a new `veadk studio deploy`, managed creation automatically reuses that Studio's UserPool, client, Identity region, and `/oauth/callback` from server-side VeFaaS environment. Studio uses built-in Beijing account, VPC/subnet, APIG, Runtime/worker image and model defaults without any creation YAML. Its model API key stays in `VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY`. For standalone CLI YAML profiles, explicitly different `user-pool-name`, `user-pool-client-name`, `identity-callback-url`, `identity-region`, or corresponding `managed.runtime.env` values fail configuration inspection before cloud writes. A Studio deployed before this capability must be redeployed to receive the values. Standalone `veadk mpa provision` without these Studio environment values continues to use explicit YAML. The shared PostgreSQL Workspace is created later during MPA creation and is not the deployment-time Identity store.

Choose **Agents → MPA agents → Create MPA agent**. The three steps collect basic information, automatic PostgreSQL preparation, and optional OpenViking service URL/resource ID/API Key. The generated agent ID is read-only. The PG step links to the [Volcengine AIDAP console](https://console.volcengine.com/aidap/region:aidap+cn-beijing/); the service obtains Workspace connections after submission. The OpenViking step links to the [context-management console](https://console.volcengine.com/vikingdb/openviking/region:openviking+cn-beijing/ov-6689fabdf032294/context-management?accountId=default&userId=default&projectName=default); this is a console page, not the service URL to enter. PG credentials stay server-configured. Enter the OpenViking URL, resource ID and masked API Key together to inject `OPENVIKING_URL`, `OPENVIKING_RESOURCE_ID`, `OPENVIKING_API_KEY` and `OPENVIKING_USER=default`. Leave all three blank to omit these variables, including inherited template/reference values. The key is not saved in browser drafts or task SQLite and must be re-entered after a browser restart. Review the resource plan and submit on step three. The workflow prepares account network/APIG/IM Gateway, a worker, an isolated business database and Skill Space, then deploys and checks Runtime and application readiness. Successful creation refreshes the directory.

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

### Explicit MPA and worker images

Use `managed.runtime.image` to pin the MPA image independently of `managed.worker.image`:

```yaml
managed:
  version: 1
  from-runtime: r-reference
  runtime:
    image: registry.example/agentkit/mpa_agent:release-tag
  worker:
    image: registry.example/agentkit/mpa_codex_worker:release-tag
```

This is an excerpt; retain the other required settings. `from-runtime` supplies role, compute/scaling/concurrency, APM/project, VPC and sanitized environment settings such as model/database connectivity, as well as its default image. The explicit Runtime image overrides that default as a custom image. The same override applies to `template-file` and flat mode; flat mode may omit top-level `image` when this field is set. Omission/null preserves previous behavior; blank, whitespace-containing or placeholder image values fail validation. Source selection is unchanged. Changing this setting does not automatically update existing agents; retain the original effective image when retrying unfinished creation.

### Explicit infrastructure without a reference Runtime

Remove `managed.from-runtime` and `managed.template-file` to use the flat model/database fields plus these overrides:

```yaml
managed:
  version: 1
  runtime:
    image: registry.example/agentkit/mpa_agent:release-tag
    role-name: IDRoleForArkClawShareAgent
    cpu-milli: 2000       # 2 CPU cores
    memory-mb: 4096      # 4 GiB
    min-instance: 1
    max-instance: 1
    max-concurrency: 100
    apmplus-enable: true
    project-name: default
    env:
      CLOUD_PROVIDER: volcengine
  network:
    vpc-id: vpc-existing
    subnet-ids: [subnet-existing]
  worker:
    image: registry.example/agentkit/mpa_codex_worker:release-tag
model-provider: openai
model-name: your-model
model-api-base: https://model.example/api/v3
model-api-key: "${MPA_MODEL_API_KEY}"
pg-host: database.example
pg-port: "5432"
pg-user: app
pg-password: "${MPA_PG_PASSWORD}"
pg-sslmode: require
pg-channel-binding: require
```

Retain region, shared/admin database secret references and any worker-specific settings from the complete example. `runtime.env` supports additional string application settings and complete environment-variable references; it cannot supply provisioner-owned identities, generated database names, Runtime keys or deployment database URLs. With any source mode, explicit runtime fields win; omission retains its defaults. Minimum instances may be zero, but cannot exceed the effective maximum. Network provisioning still requires public/private connectivity and does not create database allowlists. Pinning settings makes later reference Runtime changes irrelevant to this profile. A worker `reference-id`, if retained, still supplies that worker's environment separately. These settings affect future provisioning; existing instances are not automatically redeployed.

### Choosing images when creating in Studio

The creation dialog contains **MPA image** and **Worker image** text inputs, initially filled from the current server configuration. Edit either image for this creation, or clear it to use the configured default. These fields accept container references such as `registry.example/mpa:v2` or `registry.example/worker@sha256:<64 hex digits>`, not download URLs or registry login credentials. They do not edit the Studio built-in profile or redeploy existing agents. Submitting locks both inputs; failure, cancellation, closing and reopening retain the original request and known effective images for safe retry. A configuration based only on a reference Runtime/existing worker may have no locally available image default to display; leaving it blank retains that source. Administrators remain responsible for image access and compatibility. Explicit Worker image input provisions a dedicated worker, even when the profile otherwise selects an existing worker.

### Worker retries and failure diagnostics

Worker reference/discovery/create/read calls retry recognized timeouts, connection failures, throttling and temporary service errors up to **4 attempts**, waiting **1, 2, 4 seconds**. Create calls reuse the persisted payload and ClientToken. Recognized not-found is retried only for a registered managed Worker; missing reference/existing Workers, permission errors, invalid parameters and ownership conflicts fail immediately. Worker preparation has a default 600-second budget, including retries, and obeys task cancellation/deadlines. SDK-internal retries may add network requests. Unknown errors still require investigation/manual retry with the same identity; this does not guarantee every provider failure recovers.

Studio writes safe diagnostic categories to the server log and the private task database's `task_diagnostics` table. The latest 100 events per task survive manual retry and restart. Events contain task ID, timestamp, stage, operation, attempt, category and outcome (`retrying`, `failed`, `cancelled`), never raw messages, credentials or request payloads. Existing HTTP error codes and dialog behavior remain unchanged. To inspect locally:

```bash
sqlite3 -readonly .adk/mpa-creation.sqlite3 "SELECT task_id,datetime(created,'unixepoch'),stage,operation,category,attempt,outcome FROM task_diagnostics ORDER BY id DESC LIMIT 30;"
```

Use the configured `VEADK_MPA_TASK_DB` path when overridden. Times in this example are UTC. `permission` requires checking deployment credentials/permissions; `invalid_request` requires configuration checks; `ownership` and `configuration_changed` require reconciling the original resource identity/inputs. `timeout`, `connection`, `throttled` and `unavailable` distinguish transient failures; `not_found` identifies delayed visibility or missing resources, depending on the operation. `unknown`/`provider_error` means the provider error was not safely recognized, not success. Abnormal child exit, supervisor interruption, deadline and cancellation are also recorded. Historical errors discarded by older versions cannot be recovered.

### Initialization metadata delays

For managed Workers with a persisted creation ID/token/hash, missing ID/project/ownership tags during initialization are polled up to four incomplete observations, waiting 5, 10 and 20 seconds. This handles resources whose metadata becomes visible after CreateTool returns. Explicit conflicting values still fail immediately; Ready with missing metadata and terminal/unknown states receive no grace. These waits respect the existing stage deadline/cancellation and never create another Worker. Safe diagnostic operations identify the affected field (`worker_id`, `worker_project`, `worker_managed_by`, `worker_agent_key`, `worker_agent_binding`, `worker_state`); `metadata_pending` means waiting, `metadata_missing` means the bounded check failed. Field values remain private.

Managed provisioning accepts PostgreSQL registry URLs with `sslmode` and converts that query parameter to `ssl` for the MPA Runtime's asyncpg driver. The TLS mode is preserved. This applies to both automatic and manually configured management databases; no image rebuild is required. Existing pending deployments can resume this conversion without changing their resource identities.

## Studio A2A discovery defaults

Flat creation defaults to `ENABLE_A2A=true` and `DISABLE_JWT_AUTH=false`. With a compatible MPA image, Studio's Runtime-key `/list-apps` probe receives 404 and discovers the A2A agent card as `a2a-default`. `A2A_TIP_VERIFY_ENABLED=false` retains the existing outer gateway key-auth integration; REST JWT authentication is not bypassed. Explicit `managed.runtime.env` overrides remain supported, and referenced Runtime/template environments are preserved. Existing Runtimes need an explicit configuration update and release; reconnect in Studio to refresh discovery. No frontend rebuild is needed for this default change.
