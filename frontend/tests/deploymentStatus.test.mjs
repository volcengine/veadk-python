import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

async function loadTypeScriptModule(relativePath) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(relativePath, import.meta.url))],
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node20",
    write: false,
  });
  const source = Buffer.from(result.outputFiles[0].contents).toString("base64");
  return import(`data:text/javascript;base64,${source}`);
}

const {
  DeploymentStatusUnconfirmedError,
  isDeploymentStatusUnconfirmedError,
  pollDeploymentRecovery,
} = await loadTypeScriptModule("../src/adk/deploymentStatus.ts");
const { deployAgentkitProject } = await loadTypeScriptModule("../src/adk/client.ts");

test("classifies only explicitly ambiguous deployment outcomes as unconfirmed", () => {
  const transport = new DeploymentStatusUnconfirmedError({
    taskId: "task-1",
    cause: new TypeError("network error"),
  });

  assert.equal(isDeploymentStatusUnconfirmedError(transport), true);
  assert.equal(
    isDeploymentStatusUnconfirmedError(
      new Error("RunPipeline result could not be reconciled"),
    ),
    true,
  );
  assert.equal(
    isDeploymentStatusUnconfirmedError(new Error("Polling build status failed")),
    true,
  );
  assert.equal(isDeploymentStatusUnconfirmedError(new Error("HTTP 409")), false);
  assert.equal(isDeploymentStatusUnconfirmedError(new Error("build failed")), false);
});

test("preserves task identity without exposing the transport detail", () => {
  const error = new DeploymentStatusUnconfirmedError({
    taskId: "task-2",
    cause: new Error("private upstream detail"),
  });

  assert.equal(error.name, "DeploymentStatusUnconfirmedError");
  assert.equal(error.taskId, "task-2");
  assert.doesNotMatch(error.message, /private upstream detail/);
});

test("polls cloud-authoritative deployment status until a fresh instance confirms it", async () => {
  const observations = [
    { done: false, status: "running" },
    { done: true, success: true, runtimeId: "runtime-1", version: 4 },
  ];
  let calls = 0;

  const recovered = await pollDeploymentRecovery({
    load: async () => observations[calls++],
    timeoutMs: 1_000,
    intervalMs: 0,
  });

  assert.equal(calls, 2);
  assert.deepEqual(recovered, observations[1]);
});

test("fails fast when deployment status polling sees a non-retryable error", async () => {
  const fatal = new Error("forbidden");
  let calls = 0;

  await assert.rejects(
    pollDeploymentRecovery({
      load: async () => {
        calls += 1;
        throw fatal;
      },
      shouldRetry: () => false,
      timeoutMs: 1_000,
      intervalMs: 0,
    }),
    fatal,
  );
  assert.equal(calls, 1);
});

test("propagates user cancellation while recovery is polling", async () => {
  const controller = new AbortController();

  await assert.rejects(
    pollDeploymentRecovery({
      signal: controller.signal,
      load: async () => {
        controller.abort();
        return { done: false };
      },
      timeoutMs: 1_000,
      intervalMs: 100,
    }),
    { name: "AbortError" },
  );
});

test("recovers an accepted Runtime update when the initial fetch loses response headers", async () => {
  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  const originalSessionStorage = globalThis.sessionStorage;
  const originalLocalStorage = globalThis.localStorage;
  const storage = {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
  };
  globalThis.window = {
    location: {
      search: "",
      origin: "https://studio.example.com",
      pathname: "/",
      hash: "",
    },
    history: { replaceState: () => {} },
  };
  globalThis.sessionStorage = storage;
  globalThis.localStorage = storage;
  let deployCalls = 0;
  let statusCalls = 0;
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    if (url.endsWith("/web/deploy-agentkit")) {
      deployCalls += 1;
      throw new TypeError("network error before response headers");
    }
    if (url.endsWith("/web/deploy-agentkit/status")) {
      statusCalls += 1;
      assert.deepEqual(JSON.parse(String(init?.body)), {
        taskId: "update-task-before-headers",
        runtimeId: "runtime-1",
        runtimeName: "runtime-name",
        appName: "updated-agent",
        region: "cn-shanghai",
        projectName: "default",
        baseRuntimeVersion: 3,
      });
      return new Response(
        JSON.stringify({
          done: true,
          success: true,
          agentName: "updated-agent",
          runtimeName: "runtime-name",
          runtimeId: "runtime-1",
          region: "cn-shanghai",
          version: 4,
          url: "https://runtime.example.com",
          apikey: "runtime-key",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    throw new Error(`unexpected request: ${url}`);
  };

  try {
    const result = await deployAgentkitProject(
      "updated-agent",
      [{ path: "app.py", content: "print('ok')\n" }],
      { region: "cn-shanghai", projectName: "default" },
      {
        taskId: "update-task-before-headers",
        runtimeId: "runtime-1",
        runtimeName: "runtime-name",
        appName: "updated-agent",
        baseRuntimeVersion: 3,
      },
    );

    assert.equal(deployCalls, 1, "the accepted deployment must not be replayed");
    assert.equal(statusCalls, 1);
    assert.equal(result.runtimeId, "runtime-1");
    assert.equal(result.runtimeName, "runtime-name");
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
    globalThis.sessionStorage = originalSessionStorage;
    globalThis.localStorage = originalLocalStorage;
  }
});
