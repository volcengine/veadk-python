import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);
const markdownSource = readFileSync(
  new URL("../src/ui/Markdown.tsx", import.meta.url),
  "utf8",
);

test("restores list markers only inside rendered Markdown", () => {
  assert.match(stylesSource, /\.md ul\s*\{[^}]*list-style:\s*disc outside/s);
  assert.match(stylesSource, /\.md ol\s*\{[^}]*list-style:\s*decimal outside/s);
  assert.match(stylesSource, /\.md ul ul\s*\{[^}]*list-style-type:\s*circle/s);
  assert.match(stylesSource, /\.md ul ul ul\s*\{[^}]*list-style-type:\s*square/s);
  assert.match(stylesSource, /\.md ol ol\s*\{[^}]*list-style-type:\s*lower-alpha/s);
  assert.match(stylesSource, /\.md ol ol ol\s*\{[^}]*list-style-type:\s*lower-roman/s);
  assert.doesNotMatch(
    stylesSource,
    /(?:^|\n)\s*(?:ul|ol)\s*\{[^}]*list-style/m,
  );
});

test("contains wide Markdown tables inside a keyboard-scrollable local region", () => {
  assert.match(markdownSource, /table: \(\{ node, \.\.\.props \}\) => \(/);
  assert.match(markdownSource, /className="md-table-scroll"/);
  assert.match(markdownSource, /tabIndex=\{0\}/);
  assert.match(
    stylesSource,
    /\.md-table-scroll\s*\{[^}]*max-width:\s*100%;[^}]*overflow-x:\s*auto;/s,
  );
  assert.match(
    stylesSource,
    /\.md-table-scroll > table\s*\{[^}]*width:\s*max-content;[^}]*min-width:\s*100%;/s,
  );
  assert.match(
    stylesSource,
    /\.md table (?:th|thead th),[\s\S]*?\.md table td\s*\{[^}]*overflow-wrap:\s*anywhere;/,
  );
});

test("keeps long Markdown links and message content inside the conversation column", () => {
  assert.match(stylesSource, /\.transcript\s*\{[^}]*min-width:\s*0;[^}]*overflow-x:\s*hidden;/s);
  assert.match(stylesSource, /\.turn\s*\{[^}]*width:\s*100%;[^}]*min-width:\s*0;/s);
  assert.match(stylesSource, /\.bubble\s*\{[^}]*min-width:\s*0;[^}]*max-width:\s*100%;/s);
  assert.match(stylesSource, /\.md\s*\{[^}]*max-width:\s*100%;[^}]*overflow-wrap:\s*anywhere;/s);
  assert.match(stylesSource, /\.md a\s*\{[^}]*overflow-wrap:\s*anywhere;/s);
});
