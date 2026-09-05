import assert from "node:assert/strict";
import test from "node:test";

import { createServer } from "vite";

test("Skill runtime messages follow language changes and preserve response context", async (t) => {
  const server = await createServer({
    logLevel: "silent",
    server: { middlewareMode: true },
    appType: "custom",
  });
  t.after(() => server.close());

  const originalFetch = globalThis.fetch;
  const originalWindow = globalThis.window;
  const originalSessionStorage = globalThis.sessionStorage;
  const originalLocalStorage = globalThis.localStorage;
  t.after(() => {
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
    globalThis.sessionStorage = originalSessionStorage;
    globalThis.localStorage = originalLocalStorage;
  });
  const storage = { getItem: () => null, setItem: () => undefined };
  globalThis.window = {
    location: { search: "", pathname: "/", hash: "", origin: "http://localhost" },
    history: { replaceState: () => undefined },
  };
  globalThis.sessionStorage = storage;
  globalThis.localStorage = storage;
  globalThis.fetch = async () => new Response("upstream unavailable", {
    status: 502,
    statusText: "Bad Gateway",
    headers: { "Content-Type": "text/plain" },
  });

  const { i18n } = await server.ssrLoadModule("/src/i18n/index.ts");
  const { getSkillWorkbenchCapability } = await server.ssrLoadModule(
    "/src/ui/skill-workbench/api.ts",
  );

  await i18n.changeLanguage("en-US");
  await assert.rejects(
    getSkillWorkbenchCapability(),
    /Failed to load Skill workbench capabilities.*HTTP 502.*text\/plain.*proxy or gateway/,
  );

  await i18n.changeLanguage("zh-CN");
  await assert.rejects(
    getSkillWorkbenchCapability(),
    /读取 Skill 工作台能力失败.*HTTP 502.*text\/plain.*代理或网关/,
  );
});
