import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const result = await build({
  entryPoints: [
    fileURLToPath(
      new URL(
        "../src/migrations/migrationHistoryStatus.ts",
        import.meta.url,
      ),
    ),
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
  isMigrationEnvironmentExpired,
  migrationHistoryStatus,
} = await import(moduleUrl);

function task(overrides = {}) {
  return {
    id: `migration-v1-${"1".repeat(32)}`,
    state: "succeeded",
    message: "done",
    sourceFileName: "source.zip",
    instruction: "",
    createdAt: "2026-09-09T08:00:00Z",
    expiresAt: "2026-09-09T10:00:00Z",
    sessionTtlSeconds: 7200,
    canModify: false,
    canUpload: false,
    canAnswer: false,
    canConfirm: false,
    canStop: false,
    artifact: {
      state: "ready",
      previewReady: true,
      downloadReady: true,
      deployReady: true,
    },
    ...overrides,
  };
}

function evaluation(state) {
  return {
    enabled: true,
    state,
    message: state,
    canResume: state === "waiting_environment",
    canRetry: state === "failed" || state === "blocked",
  };
}

test("keeps successful migrations in progress until evaluation completes", () => {
  assert.deepEqual(
    migrationHistoryStatus(task({ evaluation: evaluation("pending") })),
    { labelKey: "historyStatus.evaluationPending", tone: "active" },
  );
  for (const state of [
    "preparing",
    "deploying",
    "executing",
    "judging",
    "aggregating",
  ]) {
    assert.deepEqual(
      migrationHistoryStatus(task({ evaluation: evaluation(state) })),
      { labelKey: "historyStatus.evaluationRunning", tone: "active" },
    );
  }
  assert.deepEqual(
    migrationHistoryStatus(task({ evaluation: evaluation("completed") })),
    { labelKey: "state.succeeded", tone: "success" },
  );
});

test("shows actionable evaluation outcomes without hiding migration success", () => {
  assert.deepEqual(
    migrationHistoryStatus(
      task({ evaluation: evaluation("waiting_dataset") }),
    ),
    { labelKey: "historyStatus.waitingDataset", tone: "warning" },
  );
  assert.deepEqual(
    migrationHistoryStatus(
      task({ evaluation: evaluation("waiting_environment") }),
    ),
    { labelKey: "historyStatus.waitingEnvironment", tone: "warning" },
  );
  assert.deepEqual(
    migrationHistoryStatus(task({ evaluation: evaluation("failed") })),
    { labelKey: "historyStatus.evaluationFailed", tone: "warning" },
  );
  assert.deepEqual(
    migrationHistoryStatus(task({ evaluation: evaluation("blocked") })),
    { labelKey: "historyStatus.evaluationBlocked", tone: "warning" },
  );
  assert.deepEqual(
    migrationHistoryStatus(task({ evaluation: evaluation("cancelled") })),
    { labelKey: "historyStatus.evaluationCancelled", tone: "neutral" },
  );
});

test("migration failure remains authoritative when no evaluable output exists", () => {
  assert.deepEqual(
    migrationHistoryStatus(
      task({ state: "failed", evaluation: evaluation("pending") }),
    ),
    { labelKey: "state.failed", tone: "error" },
  );
});

test("treats expiration as availability metadata instead of a result", () => {
  const finished = task({
    state: "expired",
    persistence: {
      state: "saved",
      message: "saved",
      projectId: "project-1",
      versionId: "version-1",
    },
  });
  assert.deepEqual(migrationHistoryStatus(finished), {
    labelKey: "state.succeeded",
    tone: "success",
  });
  assert.deepEqual(
    migrationHistoryStatus(task({ state: "expired" })),
    { labelKey: "historyStatus.resultUnavailable", tone: "neutral" },
  );
  assert.equal(
    isMigrationEnvironmentExpired(
      task(),
      Date.parse("2026-09-09T09:59:59Z"),
    ),
    false,
  );
  assert.equal(
    isMigrationEnvironmentExpired(
      task(),
      Date.parse("2026-09-09T10:00:00Z"),
    ),
    true,
  );
  assert.equal(
    isMigrationEnvironmentExpired(
      task({ state: "expired", expiresAt: "invalid" }),
      Date.parse("2026-09-09T09:00:00Z"),
    ),
    true,
  );
});
