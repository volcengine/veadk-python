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
    origin: "http://localhost",
  },
  history: { replaceState() {} },
};
globalThis.sessionStorage = memoryStorage();
globalThis.localStorage = memoryStorage();

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
const { revealModelApiKey, listModelApiKeys, httpErrorMessage } = await import(moduleUrl);

test("model errors display the original cloud body and status", async () => {
  const body = '{"ResponseMetadata":{"RequestId":"cloud-request-id","Error":{"Code":"AccessDenied","Message":"original cloud message"}}}';
  const message = await httpErrorMessage(new Response(body, { status: 403, headers: {
    "X-Studio-Error-Source": "upstream",
    "X-Studio-Upstream-Status": "403",
    "X-Studio-Upstream-Action": "ListModelActivations",
  } }), "load models failed");
  assert.ok(message.includes(body));
  assert.ok(message.includes("403"));
  assert.ok(message.includes("ListModelActivations"));
});

test("each API key list read requests a fresh complete list", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = previousFetch; });
  const requests = [];
  globalThis.fetch = async (url, init = {}) => {
    requests.push({ url: String(url), init });
    return Response.json({ provider: "volcengine", keys: Array.from({ length: requests.length }, (_, index) => ({ id: String(index), name: `Key ${index}` })) });
  };
  assert.equal((await listModelApiKeys()).keys.length, 1);
  assert.equal((await listModelApiKeys()).keys.length, 2);
  assert.equal(requests.length, 2);
  assert.ok(requests.every((request) => request.url === "/web/model-api-keys" && request.init.cache === "no-store"));
});

test("reveals a selected ModelArk API key through an explicit uncached POST", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });

  const requests = [];
  globalThis.fetch = async (url, init = {}) => {
    requests.push({ url: String(url), init });
    return Response.json(
      { value: "raw-key-returned-only-to-the-caller" },
      { headers: { "Cache-Control": "no-store" } },
    );
  };

  const controller = new AbortController();
  const response = await revealModelApiKey("key/id with spaces", controller.signal);

  assert.deepEqual(response, { value: "raw-key-returned-only-to-the-caller" });
  assert.equal(requests.length, 1);
  assert.equal(
    requests[0].url,
    "/web/model-api-keys/key%2Fid%20with%20spaces/value",
  );
  assert.equal(requests[0].init.method, "POST");
  assert.equal(requests[0].init.cache, "no-store");
  assert.equal(requests[0].init.signal.aborted, false);
  controller.abort();
  assert.equal(requests[0].init.signal.aborted, true);
  assert.equal(requests[0].init.body, undefined);
});
