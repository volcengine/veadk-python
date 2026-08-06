import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/adk/runtimeClientTools.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const {
  clearRuntimeClientToolsSupportCache,
  declaresClientToolsProtocol,
  openApiSupportsClientTools,
  probeRuntimeClientToolsSupport,
} = await import(moduleUrl);

globalThis.window = {
  clearTimeout: globalThis.clearTimeout,
  setTimeout: globalThis.setTimeout,
};

function jsonResponse(status, value) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => value,
  };
}

test("requires an explicit client_tools/v1 protocol declaration", () => {
  assert.equal(
    declaresClientToolsProtocol({ protocols: { client_tools: { version: 1 } } }),
    true,
  );
  assert.equal(
    declaresClientToolsProtocol({ protocols: { client_tools: { version: 2 } } }),
    false,
  );
  assert.equal(declaresClientToolsProtocol({ protocols: ["client_tools/v1"] }), false);
  assert.equal(declaresClientToolsProtocol({ client_tools: true }), false);
});

test("accepts a strict client_tools request schema as an OpenAPI fallback", () => {
  const openApi = {
    paths: {
      "/harness/run_sse": {
        post: {
          requestBody: {
            content: {
              "application/json": {
                schema: { $ref: "#/components/schemas/HarnessRunAgentRequest" },
              },
            },
          },
        },
      },
    },
    components: {
      schemas: {
        HarnessRunAgentRequest: {
          allOf: [
            { $ref: "#/components/schemas/RunAgentRequest" },
            { type: "object", properties: { client_tools: { type: "array" } } },
          ],
        },
        RunAgentRequest: { type: "object", properties: { app_name: { type: "string" } } },
      },
    },
  };
  assert.equal(openApiSupportsClientTools(openApi), true);
});

test("does not confuse basic Harness or the Janus-specific field with client_tools/v1", () => {
  const oldOpenApi = {
    paths: {
      "/harness/run_sse": {
        post: {
          requestBody: {
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  properties: { browser_context_available: { type: "boolean" } },
                },
              },
            },
          },
        },
      },
    },
  };
  assert.equal(openApiSupportsClientTools(oldOpenApi), false);
});

test("probes the explicit capability before using OpenAPI fallback", async () => {
  clearRuntimeClientToolsSupportCache();
  const requests = [];
  const fetcher = async (url) => {
    requests.push(url);
    return jsonResponse(200, { protocols: { client_tools: { version: 1 } } });
  };
  assert.equal(
    await probeRuntimeClientToolsSupport("runtime/1", "cn-beijing", { fetcher }),
    true,
  );
  assert.deepEqual(requests, [
    "/web/runtime-proxy/runtime%2F1/harness/capabilities?region=cn-beijing",
  ]);
});

test("deduplicates concurrent probes and caches the result by runtime and region", async () => {
  clearRuntimeClientToolsSupportCache();
  let requestCount = 0;
  const fetcher = async () => {
    requestCount += 1;
    return jsonResponse(200, { protocols: { client_tools: { version: 1 } } });
  };
  const options = { fetcher, cacheTtlMs: 60_000 };
  const [first, second] = await Promise.all([
    probeRuntimeClientToolsSupport("runtime-1", "cn-beijing", options),
    probeRuntimeClientToolsSupport("runtime-1", "cn-beijing", options),
  ]);
  assert.deepEqual([first, second], [true, true]);
  assert.equal(
    await probeRuntimeClientToolsSupport("runtime-1", "cn-beijing", options),
    true,
  );
  assert.equal(requestCount, 1);
});

test("falls back to OpenAPI only when the capability endpoint is absent", async () => {
  clearRuntimeClientToolsSupportCache();
  const requests = [];
  const fetcher = async (url) => {
    requests.push(url);
    if (url.includes("harness/capabilities")) return jsonResponse(404, null);
    return jsonResponse(200, {
      paths: {
        "/harness/run_sse": {
          post: {
            requestBody: {
              content: {
                "application/json": {
                  schema: { type: "object", properties: { client_tools: { type: "array" } } },
                },
              },
            },
          },
        },
      },
    });
  };
  assert.equal(
    await probeRuntimeClientToolsSupport("runtime-1", "cn-beijing", { fetcher }),
    true,
  );
  assert.equal(requests.length, 2);
});

test("fails closed when the capability endpoint errors", async () => {
  clearRuntimeClientToolsSupportCache();
  let requestCount = 0;
  const fetcher = async () => {
    requestCount += 1;
    return jsonResponse(503, null);
  };
  assert.equal(
    await probeRuntimeClientToolsSupport("runtime-1", "cn-beijing", { fetcher }),
    false,
  );
  assert.equal(requestCount, 1);
});
