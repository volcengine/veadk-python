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
globalThis.localStorage.setItem?.("agentkit.studio.locale", "zh-CN");
globalThis.window.localStorage = {
  getItem: (key) => key === "agentkit.studio.locale" ? "zh-CN" : null,
};

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
  runtimeLogErrorText,
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

test("formats the complete cloud error for display and copying", () => {
  const text = runtimeLogErrorText({
    message: "日志连接暂时中断，正在重试。",
    statusCode: "403",
    errorCode: "AccessDenied",
    requestId: "request-cloud-123",
    detail: "GetRuntimeInstanceLogs failed",
    responseBody: '{"message":"missing permission","field":"logs"}',
  });

  assert.match(text, /HTTP 状态码：403/);
  assert.match(text, /错误码：AccessDenied/);
  assert.match(text, /Request ID：request-cloud-123/);
  assert.match(text, /GetRuntimeInstanceLogs failed/);
  assert.match(text, /"field":"logs"/);
});

test("preserves a non-JSON upstream error response", async () => {
  globalThis.fetch = async () => new Response(
    "gateway returned the complete diagnostic body",
    { status: 502, statusText: "Bad Gateway" },
  );

  await assert.rejects(
    async () => {
      for await (const _event of streamRuntimeLogs({
        runtimeId: "runtime-1",
        region: "cn-beijing",
        instanceName: "instance-1",
        follow: false,
      })) {
        // Consume the stream so the response error is raised.
      }
    },
    /HTTP 502 Bad Gateway[\s\S]*gateway returned the complete diagnostic body/,
  );
});

test("renders every structured cloud error field from the BFF response", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({
    detail: {
      message: "读取实例日志失败。",
      detail: "GetRuntimeInstanceLogs failed",
      statusCode: "403",
      errorCode: "AccessDenied",
      requestId: "request-cloud-123",
      responseBody: '{"message":"missing permission"}',
    },
  }), {
    status: 502,
    statusText: "Bad Gateway",
    headers: { "Content-Type": "application/json" },
  });

  await assert.rejects(
    async () => {
      for await (const _event of streamRuntimeLogs({
        runtimeId: "runtime-1",
        region: "cn-beijing",
        instanceName: "instance-1",
        follow: false,
      })) {
        // Consume the stream so the response error is raised.
      }
    },
    (error) => {
      assert.match(error.message, /HTTP 状态码：403/);
      assert.match(error.message, /错误码：AccessDenied/);
      assert.match(error.message, /Request ID：request-cloud-123/);
      assert.match(error.message, /missing permission/);
      return true;
    },
  );
});
