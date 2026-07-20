import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/ui/composerKeyboard.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const { isImeCompositionEvent } = await import(moduleUrl);

test("recognizes explicit IME composition", () => {
  assert.equal(isImeCompositionEvent({ isComposing: true, keyCode: 13 }), true);
});

test("recognizes Safari's legacy IME key code", () => {
  assert.equal(isImeCompositionEvent({ isComposing: false, keyCode: 229 }), true);
});

test("allows a normal Enter key after composition", () => {
  assert.equal(isImeCompositionEvent({ isComposing: false, keyCode: 13 }), false);
});
