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
const {
  getMigrationArtifact,
  getMigrationCapabilities,
  getMigrationTask,
  MigrationApiError,
} = await import(moduleUrl);

function migrationArtifact(environment) {
  return {
    schema_version: 1,
    run_id: `migration-v1-${"1".repeat(32)}`,
    cli: { name: "agentkit-cli", version: "0.52.1" },
    migration: {
      engine: "agentic",
      framework: "any",
      source_sha256: "2".repeat(64),
      provenance_sha256: "3".repeat(64),
    },
    status: "succeeded",
    files: [
      {
        path: "main.py",
        size: 10,
        sha256: "4".repeat(64),
        mode: "0644",
      },
    ],
    startup: { module: "main.py", object: "app" },
    environment,
    verification: { status: "passed", checks: [] },
    warnings: [],
    report: { path: "main.py" },
    artifact: {
      path: "migration-result.zip",
      size: 20,
      sha256: "5".repeat(64),
    },
    created_at: "2026-08-15T08:00:00Z",
  };
}

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

test("accepts an actionable unsupported analysis without a fake recommendation", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        id: `migration-v1-${"1".repeat(32)}`,
        state: "failed",
        message: "ZIP 中没有足以恢复 Agent 行为的项目材料。",
        sourceFileName: "compiled-only.zip",
        instruction: "",
        createdAt: "2026-08-14T08:00:00Z",
        expiresAt: "2026-08-14T09:00:00Z",
        sessionTtlSeconds: 3600,
        canModify: false,
        canUpload: false,
        canAnswer: false,
        canConfirm: false,
        canStop: false,
        artifact: {
          state: "none",
          previewReady: false,
          downloadReady: false,
          deployReady: false,
        },
        analysis: {
          schema_version: 1,
          status: "unsupported",
          attempt: 1,
          input_sha256: "2".repeat(64),
          summary: "ZIP 中没有足以恢复 Agent 行为的项目材料。",
          frameworks: [],
          recommended: null,
          entries: [],
          boundary: { include: [], exclude: ["编译产物"] },
          assumptions: [],
          questions: [],
          warnings: ["请上传源码、工作流定义或提示词。"],
        },
        analysisRef: {
          attempt: 1,
          sha256: "3".repeat(64),
          inputSha256: "2".repeat(64),
        },
        error: {
          code: "MIGRATION_ANALYSIS_UNSUPPORTED",
          message: "项目材料不足。",
          retryable: false,
        },
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );

  const task = await getMigrationTask(`migration-v1-${"1".repeat(32)}`);

  assert.equal(task.analysis.recommended, null);
  assert.equal(task.analysis.summary, "ZIP 中没有足以恢复 Agent 行为的项目材料。");
  assert.equal(task.canConfirm, false);
});

test("normalizes public migration environment defaults and legacy artifacts", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  const responses = [
    migrationArtifact({
      required: ["ARK_API_KEY"],
      optional: ["ENABLE_LLM_SHIELD", "MODEL_AGENT_API_BASE"],
      defaults: {
        ENABLE_LLM_SHIELD: "false",
        MODEL_AGENT_API_BASE: "https://ark.example/api/v3",
      },
    }),
    migrationArtifact({ required: [], optional: [] }),
  ];
  globalThis.fetch = async () =>
    new Response(JSON.stringify(responses.shift()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });

  const artifact = await getMigrationArtifact(`migration-v1-${"1".repeat(32)}`);
  const legacyArtifact = await getMigrationArtifact(
    `migration-v1-${"1".repeat(32)}`,
  );

  assert.deepEqual(artifact.environment.defaults, {
    ENABLE_LLM_SHIELD: "false",
    MODEL_AGENT_API_BASE: "https://ark.example/api/v3",
  });
  assert.deepEqual(legacyArtifact.environment.defaults, {});
});
