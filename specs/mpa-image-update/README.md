# MPA image management

[中文](README.zh.md)

Component ID: mpa-image-update. Revision: 2026-10-22. Status: active.

## Responsibility and interfaces

Studio exposes GET /web/mpa-images/{runtime_id}/{component}, GET .../versions, GET .../latest-preview?revision=... and POST ... for component runtime or worker only. All routes require Agent management, fresh owner/admin Runtime authorization (no shared connection fallback), valid provider region and MPA category. Runtime targets its authorized RuntimeId. Worker targets only the consistent Runtime.ToolId / AGENTKIT_TOOL_ID / deployment record worker_id binding, proven managed ownership tags and project, with no other Runtime/registry reference.

GET detail returns only component, resourceId, currentImage, status, repository, revision, canUpdate, reason and operation; never credentials/environments. revision hashes fresh identity, binding, image and status. POST accepts exactly {tag, revision}, {image, revision}, or {tag:latest, revision, selection:{image,digest}}; both/neither source and selection on other sources are rejected. Reject unchanged targets and stale revisions. Runtime sends only RuntimeId, ArtifactType, ArtifactUrl and ReleaseEnable=true. ArtifactType is public_image for its matching fixed public repository and image for a custom manual image. Worker sends only ToolId and ImageUrl. No automatic second-component mutation.

## Catalog and bounds

Provider volcengine uses agentkit-platform-2112682748-cn-beijing.cr.volces.com/mpa; byteplus uses agentkit-platform-3001037806-ap-southeast-1.cr.bytepluses.com/mpa. runtime suffix mpa_agent; worker suffix mpa_codex_worker. The public catalog accepts no arbitrary repository input. OCI pages contain up to 100 tags, cursor is a validated last tag. UI offers version selection and load-more without a search field. No fabricated publication timestamps or chronological ordering. HTTP timeout 12 seconds, overall catalog operation 25 seconds, response limit 1 MiB, no redirects. Anonymous token requests use only the fixed registry /service/token and expected service/scope; ignore untrusted challenge realms and Link hosts. Validate JSON shape, tags and pagination progress. Verify target manifest existence before a public-tag write; manual-address writes do not perform Studio registry requests.

## State and concurrency

Managed deployment registry account/region lock serializes image writes with provisioning/deletion. Pending/deleting deployments reject writes. Separate image_updates.runtime and image_updates.worker records persist target and phase before cloud mutation. Update acknowledgements mean submitted, not healthy. Usable status plus observed target clears active intent to configured. Explicit provider rejection clears active intent; timeout/transport/5xx/aborted submission stays uncertain. Never auto-retry cloud writes. Browser read abort/late response cannot change another Agent/component. Once dispatched, server mutation continues under its lock despite client disconnect; registry intent survives process interruption. Provisioning/deletion reject active image intents. Existing creation hashes remain unchanged because images are not recreated by this flow.

## Failures and compatibility

Return safe reason codes for forbidden, invalid_request, invalid_image, stale, busy, ownership, missing_worker, read_failed, catalog_failed, latest_resolution_failed, rejected, unchanged, not_found and outcome_unknown, with no raw provider payload. Cloud permission errors stay permission errors. Shared/unproven workers are read-only with an actionable reason. Existing sandbox sessions may keep their old Worker image; users create a new session to use updated template. Runtime requests immediate release; no application health guarantee. No SDK/config/source generation/public session contract changes. No live cloud write is included in automated tests.

Related design: [independent updates](../../prd-spec/features/mpa-image-update/2026-10-22-independent-images.md).

## Contract verification

| Contract | Guarantee | Validation |
| --- | --- | --- |
| CON-IMAGE-ISOLATION | Independent payloads and navigation | tests/cli/test_mpa_images.py; frontend/tests/mpaImages.test.tsx; frontend/tests/mpaBasicDetails.test.tsx |
| CON-IMAGE-CATALOG | Fixed providers, bounded anonymous OCI reads | tests/cli/test_mpa_images.py; public read-only smoke |
| CON-IMAGE-OWNERSHIP | Fresh ownership, revision and shared-resource guards | tests/cli/test_mpa_images.py; tests/cli/test_frontend_runtime_proxy.py |
| CON-IMAGE-OUTCOME | Durable intent and no blind retry | tests/cli/test_mpa_images.py; tests/integrations/mpa_managed/test_deletion.py |
| CON-IMAGE-SOURCE | Mutually exclusive manual/public targets, format validation and no arbitrary-host requests | tests/cli/test_mpa_images.py; frontend/tests/mpaImages.test.tsx |
| CON-IMAGE-LATEST | Existing same-repository version, saved digest revalidation and creation-state isolation | tests/cli/test_mpa_images.py; tests/integrations/mpa_managed/test_image_snapshot.py; frontend/tests/mpaImages.test.tsx |
| CON-IMAGE-UI | Loading/errors/cancellation/keyboard/narrow layout | frontend/tests/mpaImages.test.tsx; mocked browser verification |

## Manual source: CON-IMAGE-SOURCE

[Manual image source design](../../prd-spec/features/mpa-image-update/2026-10-22-manual-image-source.md). Replace the search input with a full image reference as an alternative to public tag selection; the latest explicit input clears the other source on that component only. Extend POST with exactly {image, revision} or the compatible {tag, revision}. Manual-address format validation must not cause Studio to fetch arbitrary registry hosts. A valid manual target must remain usable when catalog loading fails. Runtime custom images use ArtifactType=image; matching fixed public images use public_image. Worker still sends only ImageUrl. All existing authorization, ownership, stale-revision and durable intent rules remain. Manual references may use other registries. Format: explicit registry host with one or more repository path segments and a required tag, at most 2048 characters, lowercase DNS host/path, optional port 1–65535, no scheme, embedded credentials, whitespace, query, fragment or digest. An explicit host contains a dot or port, or is localhost. Leading/trailing input whitespace is trimmed by the UI before submission; the API accepts only canonical references. Pull permissions and image compatibility are checked by AgentKit, using existing permissions. Public list refresh preserves manual input, and catalog loading/errors do not block manual submission. No image update is triggered by input alone.

## Latest version resolution: CON-IMAGE-LATEST

[Latest update design](../../prd-spec/features/mpa-image-update/2026-10-22-latest-update-snapshots.md). Public latest updates reuse managed.image_snapshot.snapshot_image for all Volcengine/BytePlus Runtime/Worker combinations. MPA-only authorization remains mandatory. A read-only GET .../latest-preview?revision=... resolves outside the deployment lock and rechecks resource identity before returning {component, revision, requestedImage, image, digest}. Confirmation shows that target; a tag=latest request may carry selection={image,digest}, revalidated without rereading latest. Legacy latest requests resolve server-side. Persist actual target, requestedImage and digest only in the selected component update intent; creation image_snapshots is unchanged. Fixed-tag and manual requests keep existing behavior. No match, changed content, timeout or stale metadata prevents mutation. Preview lookup failures use latest_resolution_failed and do not represent an unknown cloud write. Closing aborts browser preview and discards late results; confirmation stays disabled during loading/error. The preview deadline is 180 seconds.

The optional selection must contain exactly image and digest: a non-latest tag in the matching fixed repository and lowercase sha256 with 64 hexadecimal digits. Reject malformed selections with invalid_request before registry reads. Read-only preview requires a nonempty revision of at most 128 characters. MPA image POST requests and latest previews have a 180-second browser deadline; other image reads keep 30 seconds. The upstream resolver retains its 120-second discovery budget, bounded responses and pagination. Backend preview has a 180-second deadline; an in-flight cancelled thread can finish read-only registry calls without cloud mutation.
