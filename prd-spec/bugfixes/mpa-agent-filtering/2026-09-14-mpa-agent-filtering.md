# MPA Agent Filtering Bugfix

- Change ID: `mpa-agent-filtering`
- Created: 2026-09-14
- Status: approved
- Chinese: [2026-09-14-mpa-agent-filtering.zh.md](2026-09-14-mpa-agent-filtering.zh.md)
- Related specs: [MPA Runtime Provisioning](../../../specs/mpa-runtime-provisioning/README.md), [Studio MPA Control Plane](../../../specs/studio-mpa-control-plane/README.md)

## Background And Evidence

Studio added `CloudRuntime.agentCategory` and the new-chat picker can show an `MPA Agent` type, but MPA Runtimes are not reliably returned there. The server classification must use an explicit Runtime tag; artifact URL matching lets old test images pollute the MPA filter and is not reliable enough for product grouping. The MPA Runtime provisioning path does not write that tag, and frontend filtering currently happens after one `/web/runtimes` page is loaded, so MPA Runtimes can be missed when a page mostly contains general agents. The My Agents page also lacks an `mpa` type option.

## Goals

- Persist a stable MPA Runtime classification tag during `veadk mpa create`.
- Let `/web/runtimes` filter by agent category on the server side.
- Make the new-chat picker and My Agents page use the same MPA category.
- Preserve compatibility with existing callers that do not pass a category.

## Non-Goals

- Do not change the mpa-agent image or its runtime protocol.
- Do not push images or modify `~/workspace/bytedance/mpa/agentkit-mpa-agent` in this bugfix.
- Do not automatically mutate cloud Runtime tags during read-only listing.

## Requirements

- `FR-1`: MPA Runtime create and convergent update must include `veadk:agent-type=mpa`.
- `FR-2`: `/web/runtimes` must accept optional `agentCategory=general|mpa` and return pages that are filtered before pagination is exposed to the frontend.
- `FR-5`: `agentCategory=mpa` must use the Volcano Tag service's positive `veadk:agent-type=mpa` lookup before Runtime detail hydration so sparse MPA results do not require scanning unrelated Runtime pages.
- `FR-3`: Existing untagged MPA Runtimes must not be classified as MPA by image-name heuristics. They enter the MPA filter only after an explicit tag repair writes `veadk:agent-type=mpa`.
- `FR-4`: New-chat and My Agents type filters must both expose MPA and must not mix MPA Runtimes into General.

## Design

`veadk.integrations.mpa.mpa_runtime.provision_runtime()` adds a `tags` mapping parameter. The MPA CLI passes `{"veadk:agent-type": "mpa"}`. The function writes tags on both `CreateRuntimeRequest` and `UpdateRuntimeRequest` so retries converge existing named Runtimes to the same category.

`GET /web/runtimes` keeps its response shape and adds an optional query parameter `agentCategory`. Invalid values return `400`. Runtime category is derived only from explicit Runtime tags. When `agentCategory=mpa` is present, the server queries the Volcano Tag service with a positive `veadk:agent-type=mpa` filter to obtain candidate Runtime IDs, then hydrates those Runtime records by ID. The existing per-page Tag service lookup is retained for ordinary Runtime listing because the Runtime SDK response may omit custom tags. `agentCategory=general` remains a local exclusion filter because the control plane does not expose a negative tag filter.

The frontend adds `agentCategory` to `getRuntimes()` options. NewChatAgentPicker asks the server for `mpa` or `general` instead of filtering a single page locally. MyAgents adds `mpa` to its type enum and uses the same runtime listing path for `general` and `mpa`; personal sandbox agent types remain unchanged.

## Tasks

- `T-1`: Update MPA Runtime provisioning tags and tests.
- `T-2`: Update `/web/runtimes` filtering and tests.
- `T-3`: Update frontend client, NewChatAgentPicker, MyAgents, i18n, and source-based tests.
- `T-4`: Run targeted Python/frontend checks and rebuild Studio assets if frontend output changes.

## Verification And Acceptance

| Requirement | Task | Acceptance criterion | Verification | Result |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1` | MPA create/update Runtime requests include `veadk:agent-type=mpa`. | `uv run --extra dev pytest tests/integrations/test_mpa_runtime.py tests/cli/test_cli_mpa.py` | pass |
| `FR-2` | `T-2` | `/web/runtimes?agentCategory=mpa` returns only MPA Runtime pages and rejects invalid categories. | `uv run --extra dev pytest tests/cli/test_frontend_runtime_proxy.py::test_runtime_list_filters_agent_category_before_pagination -q` | pass |
| `FR-5` | `T-2` | MPA Runtime listing uses the Tag service positive filter to obtain candidate Runtime IDs and avoids scanning later unrelated Runtime list pages. | `uv run --extra dev pytest tests/cli/test_frontend_runtime_proxy.py::test_runtime_list_filters_agent_category_before_pagination -q` | pass |
| `FR-4` | `T-3` | New-chat and My Agents expose MPA and request category-filtered Runtime pages. | `node --test frontend/tests/newChatAgentPicker.test.mjs frontend/tests/myAgents.test.mjs`; `npm --prefix frontend test` | pass |
| All | `T-4` | Built Studio assets match source changes. | `npm --prefix frontend run build -- --mode development`; `npm --prefix frontend run test:webui-assets`; `git diff --check` | pass |

## Risks

Historical MPA Runtimes without `veadk:agent-type=mpa` remain classified as General until a deliberate tag repair is run. This bugfix does not add that repair command; it makes new and updated MPA Runtime classifications reliable and fixes server-side filtering semantics without admitting old test images by name.
