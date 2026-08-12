import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/ui/releaseNotes.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const { parseReleaseNotes, splitReleaseNotes } = await import(moduleUrl);

test("splits English and Chinese semicolon release notes into bullets", () => {
  assert.deepEqual(
    splitReleaseNotes([
      "新增多地域智能体; 修复更新提示；优化弹窗排版",
      "单独一项",
      "； ; ",
    ]),
    ["新增多地域智能体", "修复更新提示", "优化弹窗排版", "单独一项"],
  );
});

test("trims and de-duplicates release note bullets", () => {
  assert.deepEqual(
    splitReleaseNotes(["  修复更新提示 ;修复更新提示", "修复更新提示；新增能力"]),
    ["修复更新提示", "新增能力"],
  );
});

test("parses build-time JSON and keeps a raw-string compatibility fallback", () => {
  assert.deepEqual(
    parseReleaseNotes('["新增能力;修复问题", "优化体验；"]'),
    ["新增能力", "修复问题", "优化体验"],
  );
  assert.deepEqual(parseReleaseNotes("新增能力;修复问题"), ["新增能力", "修复问题"]);
  assert.deepEqual(parseReleaseNotes(undefined), []);
});
