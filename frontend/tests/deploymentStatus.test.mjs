import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

async function loadTypeScriptModule(relativePath) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(relativePath, import.meta.url))],
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node20",
    write: false,
  });
  const source = Buffer.from(result.outputFiles[0].contents).toString("base64");
  return import(`data:text/javascript;base64,${source}`);
}

const {
  DeploymentStatusUnconfirmedError,
  isDeploymentStatusUnconfirmedError,
} = await loadTypeScriptModule("../src/adk/deploymentStatus.ts");

test("classifies only explicitly ambiguous deployment outcomes as unconfirmed", () => {
  const transport = new DeploymentStatusUnconfirmedError({
    taskId: "task-1",
    cause: new TypeError("network error"),
  });

  assert.equal(isDeploymentStatusUnconfirmedError(transport), true);
  assert.equal(
    isDeploymentStatusUnconfirmedError(
      new Error("RunPipeline result could not be reconciled"),
    ),
    true,
  );
  assert.equal(
    isDeploymentStatusUnconfirmedError(new Error("Polling build status failed")),
    true,
  );
  assert.equal(isDeploymentStatusUnconfirmedError(new Error("HTTP 409")), false);
  assert.equal(isDeploymentStatusUnconfirmedError(new Error("build failed")), false);
});

test("preserves task identity without exposing the transport detail", () => {
  const error = new DeploymentStatusUnconfirmedError({
    taskId: "task-2",
    cause: new Error("private upstream detail"),
  });

  assert.equal(error.name, "DeploymentStatusUnconfirmedError");
  assert.equal(error.taskId, "task-2");
  assert.doesNotMatch(error.message, /private upstream detail/);
});
