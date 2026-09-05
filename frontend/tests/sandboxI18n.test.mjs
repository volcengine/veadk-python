import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

async function loadSandboxModules() {
  const result = await build({
    stdin: {
      contents: [
        'export { i18n } from "./src/i18n/runtime";',
        'export * from "./src/ui/sandboxCommands";',
      ].join("\n"),
      resolveDir: fileURLToPath(new URL("..", import.meta.url)),
      sourcefile: "sandbox-i18n-test-entry.ts",
      loader: "ts",
    },
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node20",
    write: false,
  });
  const source = Buffer.from(result.outputFiles[0].contents).toString("base64");
  return import(`data:text/javascript;base64,${source}`);
}

test("Sandbox commands resolve labels from the active locale at call time", async () => {
  const sandbox = await loadSandboxModules();

  await sandbox.i18n.changeLanguage("en-US");
  const english = sandbox.matchingSandboxCommands("model");
  assert.equal(english[0].description, "Show or switch the current conversation model");

  await sandbox.i18n.changeLanguage("zh-CN");
  const chinese = sandbox.matchingSandboxCommands("模型");
  assert.equal(chinese[0].description, "显示或切换当前对话模型");
});

test("Sandbox generated status content is localized without changing raw values", async () => {
  const sandbox = await loadSandboxModules();
  const status = {
    threadId: "thread-raw-value",
    cwd: "/workspace/raw-path",
    busy: true,
    model: "raw-model-id",
  };

  await sandbox.i18n.changeLanguage("en-US");
  const details = sandbox.sandboxStatusDetails(status);
  assert.equal(details[1].label, "Workspace");
  assert.equal(details[1].value, "/workspace/raw-path");
  assert.equal(details[2].value, "raw-model-id");
  assert.equal(details[3].value, "Running");
});
