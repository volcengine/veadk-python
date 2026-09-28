import assert from "node:assert/strict";
import test from "node:test";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";

const result = await build({ entryPoints: [fileURLToPath(new URL("../src/quality/preferences.ts", import.meta.url))], bundle: true, platform: "node", format: "cjs", write: false });
const module = { exports: {} };
Function("module", "exports", result.outputFiles[0].text)(module, module.exports);
const { hasPreferenceSuggestion, togglePreferenceSuggestion } = module.exports;

test("selecting multiple suggestions preserves manual input and deselects only the matching line", () => {
  const original = "用户自己的要求\n  保留缩进和标点！";
  const first = togglePreferenceSuggestion(original, "缺少订单号时先追问");
  const second = togglePreferenceSuggestion(first, "回答必须有事实依据");
  assert.equal(second, original + "\n缺少订单号时先追问\n回答必须有事实依据");
  assert.equal(togglePreferenceSuggestion(second, "缺少订单号时先追问"), original + "\n回答必须有事实依据");
  assert.equal(togglePreferenceSuggestion(togglePreferenceSuggestion(second, "缺少订单号时先追问"), "回答必须有事实依据"), original);
});

test("selection follows the edited text without removing modified requirements", () => {
  const edited = "缺少订单号时先追问，并核对收货人";
  assert.equal(hasPreferenceSuggestion(edited, "缺少订单号时先追问"), false);
  assert.equal(togglePreferenceSuggestion(edited, "缺少订单号时先追问"), edited + "\n缺少订单号时先追问");
  assert.equal(hasPreferenceSuggestion("  缺少订单号时先追问  \r\n", "缺少订单号时先追问"), true);
});

test("suggestions respect the field length limit and do not duplicate trailing line breaks", () => {
  const full = "x".repeat(6000);
  assert.equal(togglePreferenceSuggestion(full, "新建议"), full);
  assert.equal(togglePreferenceSuggestion("已有要求\n", "新建议"), "已有要求\n新建议");
  assert.equal(togglePreferenceSuggestion("   ", "新建议"), "新建议");
});
