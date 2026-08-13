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
const { revealModelApiKey } = await import(moduleUrl);

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
