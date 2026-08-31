import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const storage = () => ({
  getItem: () => null,
  setItem() {},
  removeItem() {},
});
globalThis.window = {
  location: { search: "", pathname: "/", hash: "", origin: "http://localhost" },
  history: { replaceState() {} },
};
globalThis.localStorage = storage();
globalThis.sessionStorage = storage();

const result = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/adk/runtimeLogs.ts", import.meta.url)),
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
  runtimeContextFromResponse,
  runtimeConsoleUrl,
  runtimeLogLevel,
  streamRuntimeLogs,
} = await import(moduleUrl);

test("reads only the BFF-safe runtime context headers", () => {
  const response = new Response(null, {
    headers: {
      "X-Studio-FaaS-Instance": "instance-1",
      "X-Studio-FaaS-Request-Id": "request-1",
      "X-Session-Id": "secret-session-routing-value",
    },
  });

  assert.deepEqual(
    runtimeContextFromResponse(response, "runtime-1", "cn-beijing"),
    {
      runtimeId: "runtime-1",
      region: "cn-beijing",
      instanceName: "instance-1",
      requestId: "request-1",
    },
  );
});

test("does not create a runtime context without a selected cloud Runtime", () => {
  assert.equal(runtimeContextFromResponse(new Response(), "", ""), null);
});

test("builds provider-specific console links", () => {
  assert.match(
    runtimeConsoleUrl("volcengine", "cn-beijing", "runtime-1", "instance-1"),
    /^https:\/\/console\.volcengine\.com\/agentkit\//,
  );
  assert.match(
    runtimeConsoleUrl("byteplus", "ap-southeast-1", "runtime-1", "instance-1"),
    /^https:\/\/console\.byteplus\.com\/agentkit\//,
  );
});

test("classifies common Runtime log levels without trusting markup", () => {
  assert.equal(runtimeLogLevel("2026-08-31 ERROR request failed"), "error");
  assert.equal(runtimeLogLevel("WARN slow request"), "warning");
  assert.equal(runtimeLogLevel("DEBUG payload received"), "debug");
  assert.equal(runtimeLogLevel("INFO ready"), "info");
  assert.equal(runtimeLogLevel("plain output"), "default");
});

test("streams typed log snapshots through a locally served Studio BFF", async () => {
  let requested = "";
  globalThis.fetch = async (url) => {
    requested = String(url);
    return new Response(
      'data: {"type":"context","instanceName":"instance-1","consoleUrl":"https://console.example"}\n\n' +
      'data: {"type":"logs","text":"INFO ready","updatedAt":1}\n\n' +
      'data: {"type":"done"}\n\n',
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    );
  };

  const events = [];
  for await (const event of streamRuntimeLogs({
    runtimeId: "runtime/1",
    region: "ap-southeast-1",
    instanceName: "instance/1",
    follow: false,
  })) events.push(event);

  assert.match(requested, /\/web\/runtime-logs\/runtime%2F1\/stream\?/);
  assert.match(requested, /instance_name=instance%2F1/);
  assert.deepEqual(events.map((event) => event.type), ["context", "logs", "done"]);
});

test("lets the BFF resolve an instance from the current session", async () => {
  let requested = "";
  globalThis.fetch = async (url) => {
    requested = String(url);
    return new Response('data: {"type":"done"}\n\n', {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
  };

  for await (const _event of streamRuntimeLogs({
    runtimeId: "runtime-1",
    region: "cn-beijing",
    sessionId: "session-1",
    follow: false,
  })) {
    // Consume the stream so the requested URL can be asserted.
  }

  assert.match(requested, /session_id=session-1/);
  assert.doesNotMatch(requested, /instance_name=/);
});
