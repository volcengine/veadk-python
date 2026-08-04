import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
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
