import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

async function loadCreateCatalogFixture() {
  const result = await build({
    stdin: {
      contents: `
        export { i18n } from "../src/i18n/runtime.ts";
        export { emptyDraft } from "../src/create/types.ts";
        export { AGENT_TYPES } from "../src/create/agentTypeMeta.tsx";
        export {
          BUILTIN_TOOLS,
          STM_BACKENDS,
          LTM_BACKENDS,
          KB_BACKENDS,
          TRACING_EXPORTERS,
          FEISHU_ENV,
        } from "../src/create/veadkCatalog.ts";
        export {
          HARNESS_SIDECAR_OPTIONS,
          harnessSidecarProviderNotice,
        } from "../src/create/harnessSidecarOptions.ts";
      `,
      resolveDir: fileURLToPath(new URL(".", import.meta.url)),
      sourcefile: "create-catalog-i18n-fixture.ts",
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

test("create metadata and new-draft defaults follow runtime language changes", async () => {
  const catalog = await loadCreateCatalogFixture();

  await catalog.i18n.changeLanguage("zh-CN");
  assert.equal(catalog.BUILTIN_TOOLS[0].label, "联网搜索");
  assert.equal(catalog.STM_BACKENDS[0].desc, "进程内，不持久化。适合开发调试。");
  assert.equal(catalog.FEISHU_ENV[1].placeholder, "输入 App Secret");
  assert.equal(catalog.AGENT_TYPES[1].label, "顺序型智能体");
  assert.equal(catalog.HARNESS_SIDECAR_OPTIONS[0].displayName, "上下文治理");
  assert.match(catalog.emptyDraft().instruction, /专业、可靠/);

  await catalog.i18n.changeLanguage("en-US");
  assert.equal(catalog.BUILTIN_TOOLS[0].label, "Web search");
  assert.equal(
    catalog.STM_BACKENDS[0].desc,
    "Stored in the process without persistence. Best for development and debugging.",
  );
  assert.equal(catalog.FEISHU_ENV[1].placeholder, "Enter the app secret");
  assert.equal(catalog.AGENT_TYPES[1].label, "Sequential agent");
  assert.equal(catalog.HARNESS_SIDECAR_OPTIONS[0].displayName, "Context management");
  assert.match(catalog.harnessSidecarProviderNotice("byteplus"), /not available/);
  assert.match(catalog.emptyDraft().instruction, /professional and reliable/);
});
