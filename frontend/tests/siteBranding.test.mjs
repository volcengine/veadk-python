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
const loginSource = readFileSync(
  new URL("../src/ui/LoginPage.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
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
  assert.match(sidebarSource, /width=\{20\}\s*height=\{20\}/);
  assert.match(loginSource, /width=\{20\}\s*height=\{20\}/);
  assert.match(loginSource, /<h1 className="login-title">\{branding\.title\}<\/h1>/);
  assert.match(loginSource, /火山引擎 VeADK 提供企业级 Agent 解决方案/);
  assert.match(stylesSource, /flex: 0 0 20px/);
  assert.match(stylesSource, /object-fit: contain/);
  assert.match(htmlSource, /<link rel="icon"/);
  assert.match(htmlSource, /<title>VeADK Studio<\/title>/);
});
