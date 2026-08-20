import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../vite.config.ts", import.meta.url),
  "utf8",
);

test("proxies the session trace API in development", () => {
  assert.match(source, /["']\/dev["']\s*:\s*localApiProxy\(\)/);
});

test("proxies session capability APIs in development", () => {
  assert.match(source, /["']\/harness["']\s*:\s*localApiProxy\(\)/);
});

test("local API proxy strips browser origin headers before forwarding", () => {
  assert.match(
    source,
    /function localApiProxy\(\): ProxyOptions[\s\S]*?proxy\.on\(["']proxyReq["'][\s\S]*?removeHeader\(["']origin["']\)[\s\S]*?removeHeader\(["']referer["']\)/,
  );
  for (const route of [
    "/list-apps",
    "/apps",
    "/run_sse",
    "/run",
    "/harness",
    "/debug",
    "/dev",
    "/oauth2",
    "/web",
  ]) {
    assert.match(source, new RegExp(`['"]${route}['"]\\s*:\\s*localApiProxy\\(\\)`));
  }
});

test("groups built assets by role and visualization runtime", () => {
  assert.match(source, /entryFileNames:\s*["']assets\/app\/\[name\]-\[hash\]\.js["']/);
  assert.match(source, /assets\/visualizations\/mermaid/);
  assert.match(source, /assets\/visualizations\/echarts/);
  assert.match(source, /assets\/chunks/);
  assert.match(source, /assets\/styles\/\[name\]-\[hash\]\[extname\]/);
  assert.match(source, /assets\/media\/\[name\]-\[hash\]\[extname\]/);
});
