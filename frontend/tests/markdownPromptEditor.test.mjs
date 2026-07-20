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
const createStyles = readFileSync(
  new URL("../src/create/CustomCreate.css", import.meta.url),
  "utf8",
);
const appStyles = readFileSync(
  new URL("../src/styles.css", import.meta.url),
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

test("long form content scrolls inside bounded editors", () => {
  assert.match(
    createStyles,
    /\.cw-markdown-editor:not\(\.mdxeditor-popup-container\)/,
  );
  assert.doesNotMatch(
    createStyles,
    /(?:^|,)\s*\.cw-markdown-editor\s*\{/m,
  );
  assert.match(
    createStyles,
    /\.cw-textarea-sm\s*\{[\s\S]*?max-height:\s*160px;[\s\S]*?overflow-y:\s*auto;/,
  );
  assert.match(
    createStyles,
    /\.cw-markdown-content\s*\{[\s\S]*?max-height:\s*360px;[\s\S]*?overflow-y:\s*auto;/,
  );
});

test("application shell contains scrolling within the viewport", () => {
  assert.match(
    appStyles,
    /html, body, #root\s*\{[\s\S]*?overflow:\s*hidden;/,
  );
  assert.match(
    appStyles,
    /#root\s*\{[\s\S]*?position:\s*fixed;[\s\S]*?inset:\s*0;/,
  );
  assert.match(
    appStyles,
    /\.layout\s*\{[\s\S]*?height:\s*100dvh;[\s\S]*?overflow:\s*hidden;/,
  );
  assert.match(
    appStyles,
    /\.sidebar\s*\{[\s\S]*?height:\s*100%;[\s\S]*?min-height:\s*0;/,
  );
});

test("narrow workbench stacks sections instead of squeezing the form", () => {
  assert.match(
    appStyles,
    /@media \(max-width:\s*860px\)\s*\{[\s\S]*?\.sidebar\s*\{[\s\S]*?width:\s*220px;/,
  );
  assert.match(
    createStyles,
    /@media \(max-width:\s*1080px\)\s*\{[\s\S]*?\.cw-detail\s*\{[\s\S]*?height:\s*min\(720px,\s*calc\(100dvh\s*-\s*120px\)\);[\s\S]*?\.cw-debug\s*\{[\s\S]*?flex:\s*0\s+0\s+100%;/,
  );
  assert.match(
    createStyles,
    /@media \(max-width:\s*860px\)\s*\{[\s\S]*?\.cw-editor\s*\{[\s\S]*?flex-direction:\s*column;[\s\S]*?\.cw-tree\s*\{[\s\S]*?width:\s*100%;[\s\S]*?\.cw-detail\s*\{[\s\S]*?width:\s*100%;/,
  );
  assert.match(
    createStyles,
    /@media \(max-width:\s*700px\)\s*\{[\s\S]*?\.cw-typeradio-item\s*\{[\s\S]*?padding-inline:\s*6px;/,
  );
});
