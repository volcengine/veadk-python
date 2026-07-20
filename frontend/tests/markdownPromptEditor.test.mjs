import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const editorSource = readFileSync(
  new URL("../src/create/MarkdownPromptEditor.tsx", import.meta.url),
  "utf8",
);
const createSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);

test("system prompt lazily loads a focused Markdown editor", () => {
  assert.match(
    createSource,
    /lazy\(\(\) => import\("\.\/MarkdownPromptEditor"\)\)/,
  );
  assert.match(createSource, /<MarkdownPromptEditor/);
  assert.match(editorSource, /markdownShortcutPlugin\(\)/);
  assert.match(
    editorSource,
    /headingsPlugin\(\{ allowedHeadingLevels: \[1, 2, 3\] \}\)/,
  );
  assert.match(editorSource, /suppressHtmlProcessing/);
  assert.match(editorSource, /trim=\{false\}/);
  assert.match(editorSource, /if \(!initialMarkdownNormalize\)/);
});

test("description remains a plain text field", () => {
  assert.match(
    createSource,
    /<textarea[\s\S]*?value=\{node\.description\}[\s\S]*?patch\(\{ description:/,
  );
});
