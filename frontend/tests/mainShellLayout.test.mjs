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
const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);

test("the main shell renders content without a top navigation row", () => {
  assert.match(appSource, /<section className="main-shell">\s*<main\s+className=/);
  assert.doesNotMatch(appSource, /<Navbar\b/);
  assert.match(stylesSource, /\.main-shell\s*\{[^}]*min-height:\s*0[^}]*display:\s*flex/);
  assert.match(stylesSource, /\.main\s*\{[^}]*flex:\s*1[^}]*margin:\s*0;/);
  assert.match(stylesSource, /\.main\s*\{[^}]*background:\s*hsl\(var\(--background\)\)/);
  assert.match(stylesSource, /\.main\s*\{[^}]*border:\s*0;[^}]*border-radius:\s*0;[^}]*box-shadow:\s*none;/);
});

test("ProjectPreview keeps its inline toolbar when no portal host exists", () => {
  assert.match(
    projectPreviewSource,
    /if \(!targets\) \{\s*return \(\s*<header className="pp-toolbar">[\s\S]*?\{left\}[\s\S]*?\{right\}[\s\S]*?<\/header>/,
  );
  assert.match(projectPreviewSource, /<ProjectHeaderPortal[\s\S]*?onBack/);
});

test("the complete create Agent flow collapses the sidebar without locking it closed", () => {
  assert.match(
    appSource,
    /collapseRequested=\{showAddMenu \|\| Boolean\(visibleCreateView\)\}/,
  );
  assert.match(
    sidebarSource,
    /if \(!collapseRequested\) return;\s*setCollapsed\(true\);\s*setMenuFor\(null\);/,
  );
  assert.match(sidebarSource, /onClick=\{toggleCollapsed\}/);
});
