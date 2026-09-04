import assert from "node:assert/strict";
import test from "node:test";

import { createServer } from "vite";

test("ADK client messages and headers follow the active locale", async (t) => {
  const server = await createServer({
    logLevel: "silent",
    server: { middlewareMode: true },
    appType: "custom",
  });
  t.after(() => server.close());

  const { i18n } = await server.ssrLoadModule("/src/i18n/index.ts");
  const { withLocaleHeaders } = await server.ssrLoadModule("/src/adk/i18n.ts");
  const { sandboxStatusLabel } = await server.ssrLoadModule("/src/adk/sandbox.ts");
  const { cloudRegionOptions } = await server.ssrLoadModule("/src/adk/cloudProvider.ts");
  const { runSseFirstEventTimeoutError } = await server.ssrLoadModule("/src/adk/client.ts");

  await i18n.changeLanguage("zh-CN");
  assert.equal(sandboxStatusLabel("ready"), "就绪");
  assert.equal(cloudRegionOptions("volcengine")[0].label, "华北 2（北京）");
  assert.equal(withLocaleHeaders().get("Accept-Language"), "zh-CN");
  assert.match(runSseFirstEventTimeoutError(), /30 秒内未收到首个 SSE 事件/);

  await i18n.changeLanguage("en-US");
  assert.equal(sandboxStatusLabel("ready"), "Ready");
  assert.equal(cloudRegionOptions("volcengine")[0].label, "China North 2 (Beijing)");
  assert.equal(withLocaleHeaders().get("Accept-Language"), "en-US");
  assert.match(runSseFirstEventTimeoutError(), /No SSE event was received within 30 seconds/);
  assert.equal(
    withLocaleHeaders({ "Accept-Language": "fr-FR" }).get("Accept-Language"),
    "fr-FR",
  );
});
