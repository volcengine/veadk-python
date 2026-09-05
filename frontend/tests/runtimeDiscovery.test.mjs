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

const windowEvents = new EventTarget();
globalThis.window = {
  location: {
    search: "",
    pathname: "/",
    hash: "",
    origin: "http://localhost",
  },
  history: { replaceState() {} },
  setTimeout,
  clearTimeout,
  dispatchEvent: windowEvents.dispatchEvent.bind(windowEvents),
  addEventListener: windowEvents.addEventListener.bind(windowEvents),
  removeEventListener: windowEvents.removeEventListener.bind(windowEvents),
};
globalThis.sessionStorage = memoryStorage();
globalThis.localStorage = memoryStorage();

const result = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/adk/runtimeDiscovery.ts", import.meta.url)),
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
const runtimeDiscovery = await import(moduleUrl);
const {
  RuntimeAccessDeniedError,
  RuntimeListError,
  RuntimeProbeError,
  getRuntimes,
  getRuntimesWithTimeoutRetry,
  probeRuntimeApps,
  runRuntimeCompatibilityChecks,
  runtimeRegionCandidates,
  setClientCloudProvider,
  waitForRetryDelay,
} = runtimeDiscovery;

test("uses provider-specific Runtime regions without cross-cloud fallback", () => {
  setClientCloudProvider("volcengine");
  assert.deepEqual(runtimeRegionCandidates(), ["cn-beijing", "cn-shanghai"]);
  assert.deepEqual(runtimeRegionCandidates("cn-shanghai"), ["cn-shanghai", "cn-beijing"]);
  assert.deepEqual(runtimeRegionCandidates("ap-southeast-1"), ["cn-beijing", "cn-shanghai"]);

  setClientCloudProvider("byteplus");
  assert.deepEqual(runtimeRegionCandidates(), ["ap-southeast-1"]);
  assert.deepEqual(runtimeRegionCandidates("cn-beijing"), ["ap-southeast-1"]);
  assert.deepEqual(runtimeRegionCandidates("ap-southeast-1"), ["ap-southeast-1"]);
});

test("retries a Runtime list timeout once after the configured delay", async () => {
  const timeout = new DOMException("timed out", "TimeoutError");
  const calls = [];
  const waits = [];
  const page = await getRuntimesWithTimeoutRetry(
    { region: "ap-southeast-1", scope: "all" },
    {
      request: async (options) => {
        calls.push(options);
        if (calls.length === 1) throw timeout;
        return { runtimes: [], nextToken: "" };
      },
      wait: async (delay, signal) => waits.push({ delay, signal }),
    },
  );

  assert.deepEqual(page, { runtimes: [], nextToken: "" });
  assert.equal(calls.length, 2);
  assert.deepEqual(waits, [{ delay: 5_000, signal: undefined }]);
});

test("retries only transient Runtime list statuses and never more than once", async () => {
  for (const status of [500, 502, 503, 504]) {
    let calls = 0;
    await assert.rejects(
      getRuntimesWithTimeoutRetry(
        {},
        {
          request: async () => {
            calls += 1;
            throw new RuntimeListError(`HTTP ${status}`, status);
          },
          wait: async () => {},
        },
      ),
      (error) => error instanceof RuntimeListError && error.status === status,
    );
    assert.equal(calls, 2);
  }

  let permanentCalls = 0;
  await assert.rejects(
    getRuntimesWithTimeoutRetry(
      {},
      {
        request: async () => {
          permanentCalls += 1;
          throw new RuntimeListError("forbidden", 403);
        },
        wait: async () => assert.fail("403 must not wait or retry"),
      },
    ),
    (error) => error instanceof RuntimeListError && error.status === 403,
  );
  assert.equal(permanentCalls, 1);
});

test("cancels the Runtime list retry while it is waiting", async () => {
  const controller = new AbortController();
  let calls = 0;
  const pending = getRuntimesWithTimeoutRetry(
    { signal: controller.signal },
    {
      request: async () => {
        calls += 1;
        throw new DOMException("timed out", "TimeoutError");
      },
      wait: async (delay, signal) => {
        controller.abort();
        return waitForRetryDelay(delay, signal);
      },
    },
  );

  await assert.rejects(pending, (error) => error?.name === "AbortError");
  assert.equal(calls, 1);
});

test("caps compatibility probes at four concurrent requests", async () => {
  let active = 0;
  let peak = 0;
  const completed = [];
  await runRuntimeCompatibilityChecks(
    Array.from({ length: 13 }, (_, index) => index),
    async (index) => {
      active += 1;
      peak = Math.max(peak, active);
      await new Promise((resolve) => setTimeout(resolve, 2));
      completed.push(index);
      active -= 1;
    },
  );

  assert.equal(peak, 4);
  assert.equal(completed.length, 13);
});

test("loads Runtime pages with the requested BytePlus region and preserves status", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });

  const urls = [];
  globalThis.fetch = async (url) => {
    urls.push(String(url));
    return Response.json({ runtimes: [], nextToken: "next" });
  };
  assert.deepEqual(
    await getRuntimes({ region: "ap-southeast-1", scope: "mine", pageSize: 24 }),
    { runtimes: [], nextToken: "next" },
  );
  assert.equal(
    urls[0],
    "/web/runtimes?scope=mine&page_size=24&region=ap-southeast-1",
  );

  globalThis.fetch = async () => new Response("upstream unavailable", { status: 503 });
  await assert.rejects(
    getRuntimes({ region: "ap-southeast-1" }),
    (error) => error instanceof RuntimeListError &&
      error.status === 503 &&
      error.message.includes("upstream unavailable"),
  );
});

test("classifies /list-apps success, empty, malformed, auth, unsupported, and server errors", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });

  let response = Response.json([" agent "]);
  const urls = [];
  globalThis.fetch = async (url) => {
    urls.push(String(url));
    return response;
  };
  assert.deepEqual(
    await probeRuntimeApps("runtime-success", "ap-southeast-1", { signal: new AbortController().signal }),
    ["agent"],
  );
  assert.equal(
    urls[0],
    "/web/runtime-proxy/runtime-success/list-apps?_runtime_region=ap-southeast-1",
  );

  response = Response.json([]);
  assert.deepEqual(
    await probeRuntimeApps("runtime-empty", "ap-southeast-1", { signal: new AbortController().signal }),
    [],
  );

  for (const invalid of [
    Response.json({ apps: ["agent"] }),
    Response.json(["agent", ""]),
    new Response("not json", { status: 200 }),
  ]) {
    response = invalid;
    await assert.rejects(
      probeRuntimeApps(`runtime-invalid-${Math.random()}`, "ap-southeast-1", {
        signal: new AbortController().signal,
      }),
      (error) => error instanceof RuntimeProbeError && error.message.includes("/list-apps"),
    );
  }

  response = Response.json({ detail: "runtime_access_denied" }, { status: 404 });
  await assert.rejects(
    probeRuntimeApps("runtime-denied", "ap-southeast-1", { signal: new AbortController().signal }),
    (error) => error instanceof RuntimeAccessDeniedError,
  );

  response = Response.json({ detail: "Not Found" }, { status: 404 });
  await assert.rejects(
    probeRuntimeApps("runtime-unsupported", "ap-southeast-1", { signal: new AbortController().signal }),
    (error) => error instanceof RuntimeProbeError && error.unsupported === true,
  );

  response = Response.json({ detail: "Forbidden" }, { status: 403 });
  await assert.rejects(
    probeRuntimeApps("runtime-forbidden", "ap-southeast-1", { signal: new AbortController().signal }),
    (error) => error instanceof RuntimeProbeError && error.message.includes("authentication"),
  );

  globalThis.fetch = async (url) => {
    const path = String(url);
    if (path === "/oauth2/userinfo") {
      return Response.json({ sub: "user-1" });
    }
    if (path === "/web/auth-config") {
      return Response.json({ providers: [] });
    }
    return Response.json({ detail: "Unauthorized" }, { status: 401 });
  };
  await assert.rejects(
    probeRuntimeApps("runtime-unauthorized", "ap-southeast-1", {
      signal: new AbortController().signal,
    }),
    (error) => error instanceof RuntimeProbeError && error.message.includes("authentication"),
  );

  globalThis.fetch = async () =>
    Response.json({ detail: "runtime_proxy_timeout" }, { status: 504 });
  await assert.rejects(
    probeRuntimeApps("runtime-gateway-timeout", "ap-southeast-1", {
      signal: new AbortController().signal,
    }),
    (error) => error instanceof RuntimeProbeError &&
      error.retryable === true &&
      error.message.includes("cannot connect yet"),
  );

  globalThis.fetch = async () =>
    Response.json({ error: "internal server error" }, { status: 500 });
  await assert.rejects(
    probeRuntimeApps("runtime-error", "ap-southeast-1", { signal: new AbortController().signal }),
    (error) => error instanceof Error &&
      error.message.includes("HTTP 500") &&
      error.message.includes("internal server error"),
  );
});

test("honors probe timeout, caller abort, and successful cache reuse", async (t) => {
  const previousFetch = globalThis.fetch;
  const previousNow = Date.now;
  t.after(() => {
    globalThis.fetch = previousFetch;
    Date.now = previousNow;
  });

  globalThis.fetch = async (_url, init) => new Promise((_resolve, reject) => {
    init.signal.addEventListener("abort", () => reject(init.signal.reason), { once: true });
  });
  const timeoutProbe = probeRuntimeApps("runtime-timeout", "cn-beijing", {
    timeoutMs: 5,
    signal: new AbortController().signal,
  });
  await assert.rejects(
    Promise.race([
      timeoutProbe,
      new Promise((_resolve, reject) => {
        setTimeout(() => reject(new Error("timeout signal did not fire")), 100);
      }),
    ]),
    (error) => error?.name === "TimeoutError",
  );

  const controller = new AbortController();
  const aborted = probeRuntimeApps("runtime-abort", "cn-beijing", {
    timeoutMs: 1_000,
    signal: controller.signal,
  });
  controller.abort();
  await assert.rejects(aborted, (error) => error?.name === "AbortError");

  let now = 1_000;
  let calls = 0;
  Date.now = () => now;
  globalThis.fetch = async () => {
    calls += 1;
    return Response.json(["cached-agent"]);
  };
  assert.deepEqual(
    await probeRuntimeApps("runtime-cache", "ap-southeast-1", { signal: new AbortController().signal }),
    ["cached-agent"],
  );
  assert.deepEqual(
    await probeRuntimeApps("runtime-cache", "ap-southeast-1", { preferCached: true }),
    ["cached-agent"],
  );
  assert.equal(calls, 1);

  now += 30_001;
  await probeRuntimeApps("runtime-cache", "ap-southeast-1", { preferCached: true });
  assert.equal(calls, 2);
});
