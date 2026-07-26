import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) =>
  readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

const appSource = read("App.tsx");
const clientSource = read("adk/client.ts");
const sidebarSource = read("ui/Sidebar.tsx");
const stylesSource = read("styles.css");

test("account menu opens system information with the current version", () => {
  assert.match(clientSource, /version: string;/);
  assert.match(appSource, /setVersion\(cfg\.version\)/);
  assert.match(appSource, /version=\{version\}/);
  assert.match(
    sidebarSource,
    /系统信息[\s\S]*?退出登录/,
    "system information should appear above logout",
  );
  assert.match(sidebarSource, /role="dialog"/);
  assert.match(sidebarSource, /aria-modal="true"/);
  assert.match(sidebarSource, /<dt>当前版本<\/dt>[\s\S]*?\{version \|\| "—"\}/);
  assert.match(
    stylesSource,
    /\.system-info-meta div\s*\{[^}]*flex-direction:\s*column;[^}]*align-items:\s*flex-start;/,
  );
  assert.match(stylesSource, /\.system-info-meta dd\s*\{[^}]*overflow-wrap:\s*anywhere;/);
  assert.match(stylesSource, /\.system-info-meta dd\s*\{[^}]*font-weight:\s*400;/);
  assert.match(stylesSource, /\.system-info-meta dd\s*\{[^}]*font-family:\s*inherit;/);
  assert.match(
    stylesSource,
    /\.system-info-head\s*\{[^}]*margin:\s*0 20px;[^}]*padding:\s*20px 0 16px;/,
  );
});
