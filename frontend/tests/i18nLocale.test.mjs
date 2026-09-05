import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

const localeBuild = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/i18n/locales.ts", import.meta.url)),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const localeModuleUrl = `data:text/javascript;base64,${Buffer.from(
  localeBuild.outputFiles[0].contents,
).toString("base64")}`;
const {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  detectLocale,
  localeCompatibleBackendText,
  resolveSupportedLocale,
} = await import(localeModuleUrl);

function mockBrowser({ storedLocale = null, languages = [] } = {}) {
  const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      localStorage: {
        getItem: (key) => (key === LOCALE_STORAGE_KEY ? storedLocale : null),
      },
    },
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { language: languages[0] ?? "", languages },
  });
  return () => {
    if (windowDescriptor) {
      Object.defineProperty(globalThis, "window", windowDescriptor);
    } else {
      delete globalThis.window;
    }
    if (navigatorDescriptor) {
      Object.defineProperty(globalThis, "navigator", navigatorDescriptor);
    } else {
      delete globalThis.navigator;
    }
  };
}

test("normalizes supported language variants", () => {
  assert.equal(resolveSupportedLocale("zh-CN"), "zh-CN");
  assert.equal(resolveSupportedLocale("en-US"), "en-US");
  assert.equal(resolveSupportedLocale("zh-Hant-TW"), "zh-CN");
  assert.equal(resolveSupportedLocale("en_GB"), "en-US");
  assert.equal(resolveSupportedLocale("fr-FR"), null);
});

test("filters backend copy that does not match the active language", () => {
  assert.equal(localeCompatibleBackendText("管理员未配置持久化存储", "en-US"), "");
  assert.equal(localeCompatibleBackendText("Storage is not configured", "zh-CN"), "");
  assert.equal(
    localeCompatibleBackendText("SANDBOX_DEV 暂不可用", "zh-CN"),
    "SANDBOX_DEV 暂不可用",
  );
  assert.equal(
    localeCompatibleBackendText("Storage is not configured", "en-US"),
    "Storage is not configured",
  );
});

test("prefers a stored locale over browser languages", (t) => {
  const restore = mockBrowser({
    storedLocale: "en-US",
    languages: ["zh-CN", "en-US"],
  });
  t.after(restore);
  assert.equal(detectLocale(), "en-US");
});

test("uses the first supported browser language and falls back to English", async (t) => {
  let restore = mockBrowser({ languages: ["fr-FR", "zh-TW"] });
  t.after(() => restore());
  assert.equal(detectLocale(), "zh-CN");

  restore();
  restore = mockBrowser({ languages: ["fr-FR"] });
  assert.equal(detectLocale(), DEFAULT_LOCALE);
});
