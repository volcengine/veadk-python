import assert from "node:assert/strict";
import test from "node:test";

import { createServer } from "vite";

test("shared resource, Skill source, and Composer copy follow language changes", async (t) => {
  const server = await createServer({
    logLevel: "silent",
    server: { middlewareMode: true },
    appType: "custom",
  });
  t.after(() => server.close());

  const { i18n } = await server.ssrLoadModule("/src/i18n/index.ts");

  await i18n.changeLanguage("zh-CN");
  assert.equal(i18n.t("resourceCollection.loading", { ns: "ui" }), "资源加载中，请稍候");
  assert.equal(i18n.t("skillSourcePicker.tabs.local", { ns: "ui" }), "本地文件");
  assert.match(i18n.t("composer.prompts.ppt.quarterlyReview", { ns: "ui" }), /经营表现/);

  await i18n.changeLanguage("en-US");
  assert.equal(i18n.t("resourceCollection.loading", { ns: "ui" }), "Loading resources…");
  assert.equal(i18n.t("skillSourcePicker.tabs.local", { ns: "ui" }), "Local files");
  assert.match(i18n.t("composer.prompts.ppt.quarterlyReview", { ns: "ui" }), /business performance/);
  assert.equal(i18n.t("navigation.library", { ns: "sidebar" }), "Library");
  assert.equal(i18n.t("navigation.cronjobs", { ns: "sidebar" }), "Cronjob");
  assert.equal(i18n.t("titles.cronJobs", { ns: "app" }), "Cronjob");
  assert.equal(i18n.t("page.title", { ns: "cronjobs" }), "Cronjob");
});
