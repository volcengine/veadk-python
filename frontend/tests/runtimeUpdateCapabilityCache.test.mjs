import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
}

globalThis.window = {
  location: {
    search: "",
    pathname: "/",
    hash: "",
    origin: "http://127.0.0.1",
  },
  history: { replaceState() {} },
  addEventListener() {},
  removeEventListener() {},
};
globalThis.localStorage = memoryStorage();
globalThis.sessionStorage = memoryStorage();

const result = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/adk/client.ts", import.meta.url)),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(
  result.outputFiles[0].contents,
).toString("base64")}`;
const {
  getCachedRuntimeUpdateCapability,
  getRuntimeUpdateCapability,
  invalidateRuntimeUpdateCapabilityCache,
} = await import(moduleUrl);

function capability(runtimeId, currentVersion = 1) {
  return {
    canUpdate: true,
    reason: "",
    recoveryStatus: "complete",
    editMode: "regenerate",
    recoverySource: "editable-spec",
    warnings: [],
    etag: `etag-${runtimeId}-${currentVersion}`,
    runtime: {
      runtimeId,
      name: "cache-test",
      region: "cn-shanghai",
      currentVersion,
      envs: [],
      configuredEnvKeys: [],
      network: {},
    },
    agent: { appName: "cache_test" },
  };
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

test("deduplicates in-flight capability requests and reuses the versioned result", async () => {
  let requestCount = 0;
  let releaseRequest;
  globalThis.fetch = () => {
    requestCount += 1;
    return new Promise((resolve) => {
      releaseRequest = () => resolve(jsonResponse(capability("runtime-cache")));
    });
  };

  const request = {
    runtimeId: "runtime-cache",
    region: "cn-shanghai",
    currentVersion: 1,
  };
  const first = getRuntimeUpdateCapability(request);
  const second = getRuntimeUpdateCapability(request);
  assert.equal(requestCount, 1);
  releaseRequest();
  const [firstValue, secondValue] = await Promise.all([first, second]);
  assert.strictEqual(firstValue, secondValue);

  const thirdValue = await getRuntimeUpdateCapability(request);
  assert.strictEqual(thirdValue, firstValue);
  assert.equal(requestCount, 1);
  assert.strictEqual(getCachedRuntimeUpdateCapability(request), firstValue);
});

test("keeps shared work alive when one detail waiter is aborted", async () => {
  let requestCount = 0;
  let releaseRequest;
  globalThis.fetch = () => {
    requestCount += 1;
    return new Promise((resolve) => {
      releaseRequest = () => resolve(jsonResponse(capability("runtime-abort")));
    });
  };

  const controller = new AbortController();
  const request = {
    runtimeId: "runtime-abort",
    region: "cn-shanghai",
    currentVersion: 1,
  };
  const waiting = getRuntimeUpdateCapability({
    ...request,
    signal: controller.signal,
  });
  controller.abort();
  await assert.rejects(waiting, { name: "AbortError" });
  releaseRequest();
  await getRuntimeUpdateCapability(request);
  assert.equal(requestCount, 1);
  assert.ok(getCachedRuntimeUpdateCapability(request));
});

test("does not cache failures and invalidates a successful Runtime result", async () => {
  let requestCount = 0;
  globalThis.fetch = async () => {
    requestCount += 1;
    return requestCount === 1
      ? jsonResponse({ detail: "temporary" }, 502)
      : jsonResponse(capability("runtime-retry", 2));
  };

  const request = {
    runtimeId: "runtime-retry",
    region: "cn-shanghai",
    currentVersion: 2,
  };
  await assert.rejects(getRuntimeUpdateCapability(request));
  assert.equal(getCachedRuntimeUpdateCapability(request), null);
  await getRuntimeUpdateCapability(request);
  assert.equal(requestCount, 2);

  invalidateRuntimeUpdateCapabilityCache("runtime-retry", "cn-shanghai");
  assert.equal(getCachedRuntimeUpdateCapability(request), null);
});

test("does not cache preparing responses and sends the Runtime version", async () => {
  let requestCount = 0;
  const requestedUrls = [];
  globalThis.fetch = async (input) => {
    requestCount += 1;
    requestedUrls.push(String(input));
    if (requestCount === 1) {
      return jsonResponse({
        ...capability("runtime-preparing", 5),
        canUpdate: false,
        reason: "更新配置正在后台恢复，完成后将自动启用。",
        recoveryStatus: "preparing",
        editMode: "blocked",
        recoverySource: "none",
        etag: "",
        agent: null,
      }, 202);
    }
    return jsonResponse(capability("runtime-preparing", 5));
  };

  const request = {
    runtimeId: "runtime-preparing",
    region: "cn-shanghai",
    currentVersion: 5,
  };
  const pending = await getRuntimeUpdateCapability(request);
  assert.equal(pending.recoveryStatus, "preparing");
  assert.equal(getCachedRuntimeUpdateCapability(request), null);

  const completed = await getRuntimeUpdateCapability(request);
  assert.equal(completed.recoveryStatus, "complete");
  assert.equal(requestCount, 2);
  assert.match(requestedUrls[0], /currentVersion=5/);
  assert.strictEqual(getCachedRuntimeUpdateCapability(request), completed);
});
