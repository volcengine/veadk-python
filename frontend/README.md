# VeADK Web

A React web UI for VeADK agents. It talks to the standard Google ADK API server
that `veadk frontend` launches (no separate backend): streaming chat with
thinking / tool-call blocks, session history, a tracing viewer, optional SSO, and
rich agent-driven UI (A2UI) rendering when an agent emits it.

## Run

The build output goes to `veadk/webui` (inside the Python package) and is
committed, so it ships with the wheel and `veadk frontend` works for installed
users without a build step:

```bash
# serve UI + agent API from one process
veadk frontend --agents-dir examples
# open http://127.0.0.1:8000
```

Rebuild the UI from source after changing it:

```bash
cd frontend && npm install && npm run build   # -> veadk/webui
```

Dev loop with hot reload:

```bash
veadk frontend --dev --agents-dir examples   # API only, CORS for vite
cd frontend && npm run dev                    # http://localhost:5173 (proxies API)
```

The agent dropdown lists every subdirectory (app) under `--agents-dir`. Point it
at a folder containing only your agent(s) to control the list.

## Authentication

The ADK `user_id` (which scopes sessions/memory) comes from the signed-in user.

**SSO (VeIdentity OAuth2)** — enable with flags; the UI shows a login page and
redirects through VeIdentity, then uses the `sub` from `/oauth2/userinfo`:

```bash
veadk frontend --agents-dir examples \
  --oauth2-user-pool <name>      --oauth2-user-pool-client <name>
  # or by id (env: OAUTH2_USER_POOL_ID / OAUTH2_USER_POOL_CLIENT_ID):
  # --oauth2-user-pool-uid <id>  --oauth2-user-pool-client-uid <id>
```
Requires Volcengine credentials (AK/SK) in the environment. The login button's
label/icon is config-driven (`--oauth2-provider` / `--oauth2-provider-label`),
exposed at `GET /web/auth-config`.

**No SSO (local)** — without those flags, the login page asks for a username
(letters + digits, ≤16), stored locally and used as the `user_id`.

Login state is cached: SSO via the `veadk_session` cookie, local mode via
`localStorage`. The session itself is created lazily on the first message (not on
page load).

## How it works

1. `adk/client.ts` calls `/list-apps`, creates a session, and streams `/run_sse`.
2. `a2ui/extract.ts` pulls A2UI messages out of the `send_a2ui_json_to_client`
   tool response (`validated_a2ui_json`).
3. `a2ui/Surface.tsx` applies `createSurface` / `updateComponents` /
   `updateDataModel` into surface state and renders the root component.
4. `a2ui/registry.ts` maps each component name to a React renderer; each renderer
   lives in its own directory under `a2ui/components/<Name>/` and self-registers.

## Adding a custom (enterprise) component

A custom component has two halves that share one **catalog id**:

**Frontend half** — drop a new directory; it auto-registers (no central edit):

```
src/a2ui/components/RevenueChart/
├── RevenueChart.tsx       # the React renderer
└── index.ts               # register("RevenueChart", RevenueChart)
```

```ts
// index.ts
import { register } from "../../registry";
import { RevenueChart } from "./RevenueChart";
register("RevenueChart", RevenueChart);
```

```tsx
// RevenueChart.tsx
import type { ComponentRendererProps } from "../../registry";
export function RevenueChart({ node, ctx }: ComponentRendererProps) {
  const series = ctx.resolve(node.series as any);
  return <div className="corp-chart">{/* render series */}</div>;
}
```

`components/index.ts` imports every `*/index.ts` via `import.meta.glob`, so the
new folder is picked up automatically.

**Backend half** — declare the component in a catalog and point the agent at it
(see `veadk.a2ui.BaseA2UICatalog`):

```python
from veadk import Agent
from veadk.a2ui import BaseA2UICatalog

class FinanceCatalog(BaseA2UICatalog):
    catalog_path = "/opt/corp/a2ui/finance_catalog.json"   # defines RevenueChart
    examples_path = "/opt/corp/a2ui/finance_examples"

agent = Agent(enable_a2ui=True, a2ui_catalog=FinanceCatalog())
```

Unknown components (no registered renderer) fall back to a collapsible JSON view,
so a catalog/renderer mismatch never crashes the UI.
