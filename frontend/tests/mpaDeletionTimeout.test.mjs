import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

Error.stackTraceLimit = 0;
const storage = () => {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
};
globalThis.window = {
  location: { search: "", pathname: "/", hash: "", origin: "http://127.0.0.1" },
  history: { replaceState() {} },
  addEventListener() {},
  removeEventListener() {},
};
globalThis.localStorage = storage();
globalThis.sessionStorage = storage();
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
const { deleteRuntime } = await import(
  `data:text/javascript;base64,${Buffer.from(result.outputFiles[0].contents).toString("base64")}`
);
const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const timeout = () => new DOMException("signal timed out", "TimeoutError");

async function withDeadlines(run) {
  const original = AbortSignal.timeout;
  const deadlines = [];
  AbortSignal.timeout = (ms) => {
    deadlines.push(ms);
    return new AbortController().signal;
  };
  try {
    await run(deadlines);
  } finally {
    AbortSignal.timeout = original;
  }
}

test("MPA deletion gets its own deadline while general deletion remains unchanged", async () => {
  await withDeadlines(async (deadlines) => {
    globalThis.fetch = async () => json({ success: true });
    await deleteRuntime("r-mpa", "cn-beijing", { agentCategory: "mpa" });
    await deleteRuntime("r-general", "cn-beijing", {
      agentCategory: "general",
    });
    assert.deepEqual(deadlines, [180000, 30000]);
  });
});

test("MPA timeout confirms the same Runtime once without repeating deletion", async () => {
  await withDeadlines(async (deadlines) => {
    const requests = [];
    globalThis.fetch = async (url, init) => {
      requests.push({
        url: String(url),
        method: init.method,
        cache: init.cache,
      });
      if (init.method === "POST") throw timeout();
      return json({ deleted: true });
    };
    await deleteRuntime("r-one", "ap-southeast-1", { agentCategory: "mpa" });
    assert.equal(requests.length, 2);
    const check = new URL(requests[1].url, "http://127.0.0.1");
    assert.equal(check.pathname, "/web/mpa-runtime-deletion-status");
    assert.equal(check.searchParams.get("runtimeId"), "r-one");
    assert.equal(check.searchParams.get("region"), "ap-southeast-1");
    assert.equal(requests[1].cache, "no-store");
    assert.deepEqual(deadlines, [180000, 30000]);
  });
});

for (const [label, body, status] of [
  ["still present", { deleted: false }, 200],
  ["malformed", { deleted: "true" }, 200],
  ["permission", { detail: "denied" }, 403],
  ["authorization 404", { detail: "Runtime not found" }, 404],
  ["unavailable", { detail: "unavailable" }, 503],
]) {
  test(`MPA timeout preserves an uncertain result for ${label}`, async () => {
    await withDeadlines(async () => {
      let writes = 0;
      globalThis.fetch = async (_url, init) => {
        if (init.method === "POST") {
          writes++;
          throw timeout();
        }
        return json(body, status);
      };
      await assert.rejects(
        deleteRuntime("r-one", "cn-beijing", { agentCategory: "mpa" }),
        /mpaDeleteUnconfirmed|not confirmed|尚未确认|仍|超时|確認/i,
      );
      assert.equal(writes, 1);
    });
  });
}

test("general timeouts and non-timeout MPA failures do not query confirmation", async () => {
  await withDeadlines(async () => {
    let requests = 0;
    globalThis.fetch = async () => {
      requests++;
      throw timeout();
    };
    await assert.rejects(deleteRuntime("r-general", "cn-beijing"), {
      name: "TimeoutError",
    });
    assert.equal(requests, 1);
    const original = new Error("network unavailable");
    globalThis.fetch = async () => {
      requests++;
      throw original;
    };
    await assert.rejects(
      deleteRuntime("r-mpa", "cn-beijing", { agentCategory: "mpa" }),
      (error) => error === original,
    );
    assert.equal(requests, 2);
  });
});

test("confirmation transport timeout stays uncertain without replaying DELETE", async () => {
  await withDeadlines(async () => {
    const methods = [];
    globalThis.fetch = async (_url, init) => {
      methods.push(init.method ?? "GET");
      throw timeout();
    };
    await assert.rejects(
      deleteRuntime("r-one", "cn-beijing", { agentCategory: "mpa" }),
      /mpaDeleteUnconfirmed|not confirmed|尚未确认/i,
    );
    assert.deepEqual(methods, ["POST", "GET"]);
  });
});

test("non-timeout server cleanup errors retain their diagnostic detail", async () => {
  await withDeadlines(async () => {
    let requests = 0;
    globalThis.fetch = async () => {
      requests++;
      return json({ detail: { code: "mpa_resource_cleanup_failed" } }, 502);
    };
    await assert.rejects(
      deleteRuntime("r-one", "cn-beijing", { agentCategory: "mpa" }),
      /mpa_resource_cleanup_failed/,
    );
    assert.equal(requests, 1);
  });
});
