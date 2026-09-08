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
  const { localizeDeployStageMessage } = await server.ssrLoadModule(
    "/src/adk/deploymentI18n.ts",
  );
  const { sandboxStatusLabel } = await server.ssrLoadModule("/src/adk/sandbox.ts");
  const { cloudRegionOptions } = await server.ssrLoadModule("/src/adk/cloudProvider.ts");
  const { runSseFirstEventTimeoutError } = await server.ssrLoadModule("/src/adk/client.ts");

  await i18n.changeLanguage("zh-CN");
  assert.equal(sandboxStatusLabel("ready"), "就绪");
  assert.equal(cloudRegionOptions("volcengine")[0].label, "华北 2（北京）");
  assert.equal(withLocaleHeaders().get("Accept-Language"), "zh-CN");
  assert.match(runSseFirstEventTimeoutError(), /30 秒内未收到首个 SSE 事件/);
  assert.equal(
    localizeDeployStageMessage({
      phase: "build",
      message: "正在构建镜像，已同步构建日志。",
      buildLog: { status: "running" },
    }),
    "正在构建镜像，已同步构建日志。",
  );

  await i18n.changeLanguage("en-US");
  assert.equal(sandboxStatusLabel("ready"), "Ready");
  assert.equal(cloudRegionOptions("volcengine")[0].label, "China North 2 (Beijing)");
  assert.equal(withLocaleHeaders().get("Accept-Language"), "en-US");
  assert.match(runSseFirstEventTimeoutError(), /No SSE event was received within 30 seconds/);
  assert.equal(
    localizeDeployStageMessage({
      phase: "build",
      message: "正在构建镜像，已同步构建日志。",
      buildLog: { status: "running" },
    }),
    "Building the image. Build logs are up to date.",
  );
  assert.equal(
    localizeDeployStageMessage({
      phase: "update",
      message: "正在更新 Runtime 实例配置。",
    }),
    "Updating the Runtime configuration",
  );
  assert.equal(
    localizeDeployStageMessage({
      phase: "build",
      message: "服务端旧文案",
      messageCode: "deploy.build.logs_complete",
    }),
    "Build log sync complete.",
  );
  assert.equal(
    localizeDeployStageMessage({
      phase: "deploy",
      message: "Waiting for the Runtime endpoint",
    }),
    "Waiting for the Runtime endpoint",
  );
  assert.equal(
    withLocaleHeaders({ "Accept-Language": "fr-FR" }).get("Accept-Language"),
    "fr-FR",
  );
});
