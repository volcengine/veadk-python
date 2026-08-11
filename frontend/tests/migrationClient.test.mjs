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
    fileURLToPath(new URL("../src/adk/migrations.ts", import.meta.url)),
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
const { getMigrationCapabilities, MigrationApiError } = await import(moduleUrl);

test("surfaces FastAPI validation details without blaming the proxy", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        detail: [
          {
            type: "missing",
            loc: ["body", "sourceFileName"],
            msg: "Field required",
            input: { secret: "must-not-be-rendered" },
          },
        ],
      }),
      {
        status: 422,
        headers: { "Content-Type": "application/json" },
      },
    );

  await assert.rejects(
    () => getMigrationCapabilities(),
    (cause) => {
      assert.equal(cause instanceof MigrationApiError, true);
      assert.equal(cause.code, "MIGRATION_REQUEST_INVALID");
      assert.equal(cause.retryable, false);
      assert.match(cause.message, /body\.sourceFileName: Field required/);
      assert.doesNotMatch(cause.message, /代理|网关|must-not-be-rendered/);
      return true;
    },
  );
});
