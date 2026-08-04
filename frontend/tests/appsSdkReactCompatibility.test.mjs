import assert from "node:assert/strict";
import test from "node:test";
import { createServer } from "vite";

test("the installed React runtime renders the Apps SDK RadioGroup used by Agent creation", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
    ssr: { noExternal: ["@openai/apps-sdk-ui", "radix-ui"] },
  });
  try {
    const module = await server.ssrLoadModule(
      "/tests/fixtures/appsSdkRadioGroupRender.tsx",
    );
    assert.match(module.renderAppsSdkRadioGroup(), /Agent 类型/);
  } finally {
    await server.close();
  }
});
