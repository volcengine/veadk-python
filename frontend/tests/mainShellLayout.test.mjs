import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

test("the main shell renders a flush, full-height workspace without a top navigation row", () => {
  assert.match(appSource, /<section className="main-shell">\s*<main\s+className=/);
  assert.doesNotMatch(appSource, /<Navbar\b/);
  assert.match(stylesSource, /\.main-shell\s*\{[^}]*min-height:\s*0[^}]*display:\s*flex/);
  assert.match(
    stylesSource,
    /\.main\s*\{[^}]*flex:\s*1[^}]*margin:\s*0;[^}]*background:\s*hsl\(var\(--panel\)\);[^}]*border:\s*0;[^}]*border-radius:\s*0;/,
  );
});

test("ProjectPreview keeps its inline toolbar when no portal host exists", () => {
  assert.match(
    projectPreviewSource,
    /if \(!targets\) \{\s*return \(\s*<header className="pp-toolbar">[\s\S]*?\{left\}[\s\S]*?\{right\}[\s\S]*?<\/header>/,
  );
  assert.match(projectPreviewSource, /<ProjectHeaderPortal[\s\S]*?onBack/);
});
