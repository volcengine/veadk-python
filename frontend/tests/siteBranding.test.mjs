import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);
const htmlSource = readFileSync(
  new URL("../index.html", import.meta.url),
  "utf8",
);

test("applies configured branding to the UI, document title, and favicon", () => {
  assert.match(appSource, /document\.title = siteBranding\.title/);
  assert.match(appSource, /favicon\.href = siteBranding\.logoUrl \|\| defaultSiteLogo/);
  assert.match(sidebarSource, /\{branding\.title\}/);
  assert.match(sidebarSource, /branding\.logoUrl \|\| volcengineLogo/);
  assert.match(htmlSource, /<link rel="icon"/);
  assert.match(htmlSource, /<title>VeADK Studio<\/title>/);
});
