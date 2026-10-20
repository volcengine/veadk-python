import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";
import ts from "typescript";

const storage = () => {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
};
globalThis.localStorage = storage();
globalThis.sessionStorage = storage();
globalThis.window = {
  location: { search: "", pathname: "/", hash: "", origin: "http://localhost" },
  history: { replaceState() {} },
};

// Execute the real chat preflight without mounting the entire application.
const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));
const app = ts.createSourceFile(appPath, readFileSync(appPath, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let preflight;
let artifactCondition;
function visit(node) {
  if (ts.isFunctionDeclaration(node) && node.name?.text === "resolveMpaRunConfig") {
    preflight = node.getText(app);
  }
  if (ts.isJsxElement(node) && node.openingElement.attributes.properties.some(
    attribute => ts.isJsxAttribute(attribute) && attribute.name.getText(app) === "className"
      && attribute.initializer?.getText(app) === '"runtime-artifact-entry"',
  )) {
    assert.ok(ts.isParenthesizedExpression(node.parent));
    assert.ok(ts.isBinaryExpression(node.parent.parent));
    artifactCondition = node.parent.parent.left.getText(app);
  }
  ts.forEachChild(node, visit);
}
visit(app);
assert.ok(preflight);
assert.ok(artifactCondition);
const bundled = await build({
  stdin: {
    contents: `
      export * from './client';
      export { registerConnections, remoteAppId } from './connections';
      import { isMpaRuntimeApp, isMpaA2aRuntimeApp } from './client';
      export function showRuntimeArtifacts(appName, sandboxSession = false, currentRuntime = {}, sessionId = 's-test') {
        return Boolean(${artifactCondition});
      }
      export function chatPreflight(appName, currentConn, getMpaSessionExecutionConfig) {
        const currentRuntimeAppName = currentConn?.apps[0];
        const cloudProvider = 'volcengine';
        const defaultCloudRegion = () => 'cn-beijing';
        ${preflight}
        return resolveMpaRunConfig;
      }
    `,
    resolveDir: fileURLToPath(new URL("../src/adk", import.meta.url)),
    loader: "ts",
  },
  bundle: true, platform: "node", format: "esm", write: false,
});
const api = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].contents).toString("base64")}`);
const connection = (app = "a2a-default", metadata = { agentCategory: "mpa", mpaInstanceId: "mi-test" }) => ({
  id: "test-connection", name: "Test", runtimeId: "r-test", region: "cn-beijing", apps: [app], ...metadata,
});
function setup(t, conn = connection()) {
  const originalFetch = globalThis.fetch;
  api.registerConnections([conn]);
  t.after(() => { globalThis.fetch = originalFetch; api.clearRemoteApps(); });
  return api.remoteAppId(conn.id, conn.apps[0]);
}
const pathname = (url) => new URL(String(url), "http://localhost").pathname;
const sse = () => new Response('data: {"id":"answer","author":"agent","content":{"parts":[{"text":"OK"}]},"turnComplete":true}\n\ndata: [DONE]\n\n', {
  headers: { "Content-Type": "text/event-stream" },
});

for (const appName of ["default", "a2a-default"]) {
  for (const metadata of [{ agentCategory: "mpa" }, { mpaInstanceId: "mi-test" }]) {
    test(`MPA ${appName} does not mount session artifacts: ${Object.keys(metadata)}`, t => {
      const id = setup(t, connection(appName, metadata));
      assert.equal(api.showRuntimeArtifacts(id), false);
    });
  }
  for (const metadata of [{ agentCategory: "general" }, {}]) {
    test(`general ${appName} retains session artifacts: ${Object.keys(metadata)}`, t => {
      const id = setup(t, connection(appName, metadata));
      assert.equal(api.showRuntimeArtifacts(id), true);
      assert.equal(api.showRuntimeArtifacts(id, true), false);
      assert.equal(api.showRuntimeArtifacts(id, false, null), false);
      assert.equal(api.showRuntimeArtifacts(id, false, {}, ""), false);
    });
  }
}

test("session artifact visibility follows general-to-MPA-to-general selection", t => {
  const id = setup(t, connection("a2a-default", { agentCategory: "general" }));
  assert.equal(api.showRuntimeArtifacts(id), true);
  api.registerConnections([connection("a2a-default", { agentCategory: "mpa" })]);
  assert.equal(api.showRuntimeArtifacts(id), false);
  api.registerConnections([connection("a2a-default", { agentCategory: "general" })]);
  assert.equal(api.showRuntimeArtifacts(id), true);
});

for (const metadata of [{ agentCategory: "mpa" }, { mpaInstanceId: "mi-test" }, { agentCategory: "mpa", mpaInstanceId: "mi-test" }]) {
  test(`restored A2A connection keeps one session protocol: ${Object.keys(metadata).join(",")}`, async (t) => {
    const id = setup(t, connection("a2a-default", metadata));
    const calls = [];
    globalThis.fetch = async (url, init = {}) => {
      const path = pathname(url);
      calls.push({ path, method: init.method ?? "GET", body: init.body ? JSON.parse(init.body) : null });
      if (path.endsWith("/run_sse")) return sse();
      if (path.endsWith("/sessions/s-test")) return Response.json({ id: "s-test", events: [] });
      if (path.endsWith("/sessions")) return Response.json(init.method === "POST" ? { id: "s-test" } : []);
      return Response.json({ detail: "JWT_PUBLIC_KEY is not configured" }, { status: 500 });
    };
    assert.equal(api.isMpaRuntimeApp(id), false);
    assert.equal(await api.createSession(id, "test-user"), "s-test");
    assert.deepEqual(await api.listSessions(id, "test-user"), []);
    assert.equal((await api.getSession(id, "test-user", "s-test")).id, "s-test");
    const events = [];
    for await (const event of api.runSSE({ appName: id, userId: "test-user", sessionId: "s-test", text: "test" })) events.push(event);
    assert.equal(events[0].content.parts[0].text, "OK");
    await api.deleteSession(id, "test-user", "s-test");
    assert.equal(calls.length, 5);
    assert.ok(calls.every(({ path }) => !path.includes("/api/v1/") && !path.includes("runtime-detail")));
    assert.match(calls[0].path, /\/apps\/a2a-default\/users\/test-user\/sessions$/);
    assert.equal(calls[3].body.app_name, "a2a-default");
    assert.equal(calls[3].body.session_id, "s-test");
  });
}

for (const appName of ["a2a-default", "default"]) {
  test(`chat preflight follows the ${appName} protocol`, async (t) => {
    const conn = connection(appName);
    const id = setup(t, conn);
    const calls = [];
    const ctrl = new AbortController();
    const run = api.chatPreflight(id, conn, async (args) => { calls.push(args); return { revision: 9 }; });
    const result = await run("s-test", ctrl.signal);
    if (appName === "a2a-default") {
      assert.equal(result, null);
      assert.equal(calls.length, 0);
    } else {
      assert.equal(result.executionConfigVersion, 9);
      assert.match(result.idempotencyKey, /^mpa-run:s-test:/);
      assert.equal(calls[0].signal, ctrl.signal);
    }
  });
}

for (const status of [401, 403, 500]) {
  test(`A2A HTTP ${status} stays on A2A; explicit retry uses the same route`, async (t) => {
    const id = setup(t);
    const paths = [];
    globalThis.fetch = async (url) => {
      if (pathname(url) === "/web/auth-config") return Response.json({ providers: [] });
      if (pathname(url) === "/oauth2/userinfo") return Response.json({ name: "test-user" });
      paths.push(pathname(url));
      return paths.length === 1 ? Response.json({ detail: `upstream_${status}` }, { status }) : Response.json({ id: "s-retry" });
    };
    await assert.rejects(api.createSession(id, "test-user"), new RegExp(`upstream_${status}`));
    assert.equal(paths.length, 1);
    assert.equal(await api.createSession(id, "test-user"), "s-retry");
    assert.equal(paths[0], paths[1]);
    assert.match(paths[0], /\/apps\/a2a-default\//);
  });
}

test("A2A run cancellation does not submit a native run", async (t) => {
  const id = setup(t);
  const ctrl = new AbortController();
  const paths = [];
  globalThis.fetch = async (url, init) => {
    paths.push(pathname(url));
    ctrl.abort();
    init.signal.throwIfAborted();
  };
  await assert.rejects(async () => {
    for await (const event of api.runSSE({ appName: id, userId: "test-user", sessionId: "s-test", text: "test", signal: ctrl.signal })) void event;
  }, { name: "AbortError" });
  assert.deepEqual(paths, ["/web/runtime-proxy/r-test/run_sse"]);
});

test("native MPA authentication failure does not fall back to A2A", async (t) => {
  const id = setup(t, connection("default"));
  const paths = [];
  globalThis.fetch = async (url) => {
    paths.push(pathname(url));
    return Response.json({ detail: "JWT_PUBLIC_KEY is not configured" }, { status: 500 });
  };
  assert.equal(api.isMpaRuntimeApp(id), true);
  await assert.rejects(api.createSession(id, "test-user"), /JWT_PUBLIC_KEY/);
  assert.deepEqual(paths, ["/web/runtime-proxy/r-test/api/v1/agents/mi-test/profile-status"]);
});

test("ordinary ADK sessions retain their app name and routes", async (t) => {
  const id = setup(t, connection("assistant", { agentCategory: "general" }));
  const paths = [];
  globalThis.fetch = async (url) => { paths.push(pathname(url)); return Response.json({ id: "s-adk" }); };
  assert.equal(await api.createSession(id, "test-user"), "s-adk");
  assert.deepEqual(paths, ["/web/runtime-proxy/r-test/apps/assistant/users/test-user/sessions"]);
});

for (const [app, metadata, expected] of [
  ['a2a-default', {agentCategory:'mpa'}, true],
  ['a2a-default', {mpaInstanceId:'mi-test'}, true],
  ['a2a-default', {agentCategory:'general'}, false],
  ['a2a-default', {}, false],
  ['default', {agentCategory:'mpa'}, false],
]) {
  test(`MPA A2A presentation gate: ${app} ${JSON.stringify(metadata)}`, t => {
    const id = setup(t, connection(app, metadata));
    assert.equal(api.isMpaA2aRuntimeApp(id), expected);
    assert.equal(api.isMpaA2aRuntimeApp('local-agent'), false);
  });
}
