import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const analyticsSource = readFileSync(
  new URL("../src/analytics/webpro.ts", import.meta.url),
  "utf8",
);
const mainSource = readFileSync(
  new URL("../src/main.tsx", import.meta.url),
  "utf8",
);
const viteSource = readFileSync(
  new URL("../vite.config.ts", import.meta.url),
  "utf8",
);

test("analytics is optional and respects browser Do Not Track", () => {
  assert.match(analyticsSource, /__APMPLUS_ENABLED__\.toLowerCase\(\) !== "false"/);
  assert.match(analyticsSource, /navigator\.doNotTrack !== "1"/);
  assert.match(viteSource, /env\.APM_APP_ID/);
  assert.match(viteSource, /env\.APM_APP_TOKEN/);
});

test("OAuth callback pages never initialize analytics", () => {
  assert.match(mainSource, /const handledOAuthCallback =/);
  assert.match(
    mainSource,
    /if \(!handledOAuthCallback\) \{[\s\S]*?void initAnalytics\(\);[\s\S]*?\}/,
  );
});

test("custom events always include a numeric metric for WebPro charts", () => {
  assert.match(
    analyticsSource,
    /Object\.keys\(normalizedMetrics\)\.length > 0 \? normalizedMetrics : \{ count: 1 \}/,
  );
  assert.match(analyticsSource, /metrics: eventMetrics/);
});
