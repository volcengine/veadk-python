import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

function transpileUrl(source) {
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  });
  return `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
}

const timeoutSource = readFileSync(new URL("../src/adk/timeout.ts", import.meta.url), "utf8");
const timeoutUrl = transpileUrl(timeoutSource);
const identitySource = readFileSync(
  new URL("../src/adk/identity.ts", import.meta.url),
  "utf8",
).replace('from "./timeout"', `from "${timeoutUrl}"`);
const { fetchProviders, resolveIdentity } = await import(transpileUrl(identitySource));

const originalFetch = globalThis.fetch;
const originalWarn = console.warn;
test.before(() => {
  console.warn = () => {};
});
test.afterEach(() => {
  globalThis.fetch = originalFetch;
  delete globalThis.localStorage;
});
test.after(() => {
  console.warn = originalWarn;
});

test("identity 200 resolves as authenticated", async () => {
  globalThis.fetch = async () => Response.json({ sub: "u-1", name: "Li" });
  const identity = await resolveIdentity();
  assert.equal(identity.status, "authenticated");
  assert.equal(identity.userId, "u-1");
  assert.equal(identity.local, undefined);
});

test("identity 401 keeps SSO mode unauthenticated", async () => {
  globalThis.fetch = async () => new Response("", { status: 401 });
  const identity = await resolveIdentity();
  assert.deepEqual(identity, { status: "unauthenticated", userId: "", local: false });
});

test("identity 404 enters legacy local mode", async () => {
  globalThis.fetch = async () => new Response("", { status: 404 });
  const identity = await resolveIdentity();
  assert.deepEqual(identity, { status: "unauthenticated", userId: "", local: true });
});

test("identity 404 restores a saved local username", async () => {
  globalThis.localStorage = { getItem: () => "alice" };
  globalThis.fetch = async () => new Response("", { status: 404 });
  const identity = await resolveIdentity();
  assert.equal(identity.status, "authenticated");
  assert.equal(identity.userId, "alice");
  assert.equal(identity.local, true);
});

test("identity network and server failures do not enter local mode", async (t) => {
  globalThis.localStorage = { getItem: () => "alice" };
  await t.test("network failure", async () => {
    globalThis.fetch = async () => {
      throw new TypeError("fetch failed");
    };
    await assert.rejects(resolveIdentity(), /无法连接身份服务/);
  });
  await t.test("gateway failure", async () => {
    globalThis.fetch = async () => new Response("bad gateway", { status: 502 });
    await assert.rejects(resolveIdentity(), /HTTP 502/);
  });
});

test("identity rejects a non-JSON success response", async () => {
  globalThis.fetch = async () => new Response("<!doctype html>", { status: 200 });
  await assert.rejects(resolveIdentity(), /无法解析/);
});

test("provider lookup enables local mode only after a successful empty response", async () => {
  globalThis.fetch = async () => Response.json({ providers: [] });
  assert.deepEqual(await fetchProviders(), []);
});

test("provider lookup surfaces failures instead of returning an empty list", async (t) => {
  await t.test("network failure", async () => {
    globalThis.fetch = async () => {
      throw new TypeError("fetch failed");
    };
    await assert.rejects(fetchProviders(), /无法加载登录配置/);
  });
  await t.test("server failure", async () => {
    globalThis.fetch = async () => new Response("bad gateway", { status: 502 });
    await assert.rejects(fetchProviders(), /HTTP 502/);
  });
  await t.test("non-JSON response", async () => {
    globalThis.fetch = async () => new Response("<!doctype html>", { status: 200 });
    await assert.rejects(fetchProviders(), /无法解析/);
  });
});
