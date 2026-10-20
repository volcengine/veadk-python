import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

function memoryStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
}

async function loadAuth(search, stored = {}) {
  const replacements = [];
  globalThis.window = {
    location: {
      search,
      pathname: "/",
      hash: "#result",
      origin: "https://studio.example.com",
    },
    history: {
      replaceState: (_state, _title, url) => replacements.push(url),
    },
  };
  globalThis.sessionStorage = memoryStorage(stored);
  const result = await build({
    entryPoints: [fileURLToPath(new URL("../src/adk/auth.ts", import.meta.url))],
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node20",
    write: false,
  });
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(
    result.outputFiles[0].contents,
  ).toString("base64")}#${Math.random()}`;
  return { auth: await import(moduleUrl), replacements };
}

test("keeps intelligent deployment deep-link fields out of forwarded auth", async () => {
  const local = new URLSearchParams({
    view: "runtime-deploy",
    source: "intelligent-development",
    sessionId: "session-1",
    projectId: "project-1",
    versionId: "version-1",
    artifactSha256: "a".repeat(64),
    validationReportSha256: "b".repeat(64),
  });
  const { auth, replacements } = await loadAuth(`?token=secret&${local}`);

  const request = new URL(
    auth.withAuth("/web/intelligent-development/releases/summary?sessionId=session-1"),
    "https://studio.example.com",
  );

  assert.equal(request.searchParams.get("token"), "secret");
  assert.equal(request.searchParams.get("sessionId"), "session-1");
  assert.equal(request.searchParams.has("view"), false);
  assert.equal(request.searchParams.has("projectId"), false);
  assert.equal(request.searchParams.has("versionId"), false);
  assert.equal(request.searchParams.has("artifactSha256"), false);
  assert.deepEqual(replacements, [`/?${local}#result`]);
});

test("a local-only deep link stays visible and preserves stored auth", async () => {
  const local = new URLSearchParams({
    view: "runtime-deploy",
    source: "intelligent-development",
    sessionId: "session-1",
    projectId: "project-1",
    versionId: "version-1",
    artifactSha256: "a".repeat(64),
    validationReportSha256: "b".repeat(64),
  });
  const { auth, replacements } = await loadAuth(`?${local}`, {
    veadk_auth_qs: "signature=stored",
  });

  const request = new URL(auth.withAuth("/web/access"), "https://studio.example.com");

  assert.equal(request.searchParams.get("signature"), "stored");
  assert.deepEqual(replacements, []);
});

test("similarly named non-deep-link fields are still forwarded", async () => {
  const { auth, replacements } = await loadAuth(
    "?source=oauth&sessionId=auth-session",
  );

  const request = new URL(auth.withAuth("/web/access"), "https://studio.example.com");

  assert.equal(request.searchParams.get("source"), "oauth");
  assert.equal(request.searchParams.get("sessionId"), "auth-session");
  assert.deepEqual(replacements, ["/#result"]);
});
