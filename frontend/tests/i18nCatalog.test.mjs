import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
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

test("all locale catalogs have matching keys and interpolation variables", () => {
  const result = spawnSync(process.execPath, ["scripts/check-i18n.mjs"], {
    cwd: new URL("..", import.meta.url),
    encoding: "utf8",
  });

  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /locales and \d+ namespaces are consistent/);
});

test("the i18n runtime discovers namespaces and initializes before rendering", () => {
  const i18nSource = readFileSync(
    new URL("../src/i18n/index.ts", import.meta.url),
    "utf8",
  );
  const mainSource = readFileSync(
    new URL("../src/main.tsx", import.meta.url),
    "utf8",
  );
  const runtimeSource = readFileSync(
    new URL("../src/i18n/runtime.ts", import.meta.url),
    "utf8",
  );

  assert.match(i18nSource, /import\.meta\.glob<LocaleModule>/);
  assert.match(i18nSource, /"\.\/resources\/\*\/\*\.json"/);
  assert.match(runtimeSource, /initAsync:\s*false/);
  assert.match(mainSource, /import "\.\/i18n";/);
});

test("the account menu exposes an accessible language radio submenu", () => {
  const sidebarSource = readFileSync(
    new URL("../src/ui/Sidebar.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    sidebarSource,
    /Menu\.Item[\s\S]*?account\.systemInfo[\s\S]*?Menu\.Sub[\s\S]*?account\.language/,
  );
  assert.match(sidebarSource, /<Menu\.RadioGroup/);
  assert.match(sidebarSource, /SUPPORTED_LOCALES\.map/);
  assert.match(sidebarSource, /void changeLanguage\(locale\)/);
  assert.match(sidebarSource, /<Menu\.SubContent sideOffset=\{6\} minWidth=\{136\}>/);
});

test("English uses bundled Inter while product branding keeps its display face", () => {
  const mainSource = readFileSync(
    new URL("../src/main.tsx", import.meta.url),
    "utf8",
  );
  const stylesSource = readFileSync(
    new URL("../src/styles.css", import.meta.url),
    "utf8",
  );

  assert.match(mainSource, /@fontsource\/inter\/latin-400\.css/);
  assert.match(mainSource, /@fontsource\/inter\/latin-500\.css/);
  assert.match(mainSource, /@fontsource\/inter\/latin-600\.css/);
  assert.match(stylesSource, /html\[lang="en-US"\][\s\S]*?"Inter"/);
  assert.match(stylesSource, /ui-sans-serif[\s\S]*?"PingFang SC"[\s\S]*?"Microsoft YaHei"/);
  assert.match(stylesSource, /\.brand-title[\s\S]*?"Byte Sans"/);
  assert.match(stylesSource, /\.login-brand[\s\S]*?"Byte Sans"/);
});

test("automation-generated content resolves from the requested locale", async () => {
  const { automationT } = await loadTypeScriptModule("../src/automations/i18n.ts");

  assert.equal(
    automationT("cards.review.pullRequest.title", { lng: "en-US" }),
    "chore: configure automated PR review",
  );
  assert.equal(
    automationT("cards.review.pullRequest.title", { lng: "zh-CN" }),
    "chore: 配置 PR 自动评审",
  );
  assert.match(
    automationT("cards.delivery.pullRequest.description", {
      lng: "en-US",
      provider: "BytePlus",
    }),
    /BytePlus secrets/,
  );
});

test("non-React workspace messages resolve from the requested locale", async () => {
  const { workspaceToolsT } = await loadTypeScriptModule(
    "../src/ui/workspaceToolsI18n.ts",
  );

  assert.equal(
    workspaceToolsT("resourceMetadata.unknownSource", { lng: "en-US" }),
    "Unknown source",
  );
  assert.equal(
    workspaceToolsT("resourceMetadata.unknownSource", { lng: "zh-CN" }),
    "未知来源",
  );
});
