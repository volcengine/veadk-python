import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const sandboxClientSource = readFileSync(
  new URL("../src/adk/sandbox.ts", import.meta.url),
  "utf8",
);
const dialogSource = readFileSync(
  new URL("../src/ui/SandboxLaunchDialog.tsx", import.meta.url),
  "utf8",
);
const sandboxSessionSource = readFileSync(
  new URL("../src/ui/SandboxSession.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/ui/SandboxSession.css", import.meta.url),
  "utf8",
);
const iconSource = readFileSync(
  new URL("../src/ui/icons/InsightIcon.tsx", import.meta.url),
  "utf8",
);

test("sandbox access is isolated behind a reusable typed client", () => {
  assert.match(sandboxClientSource, /export interface AgentKitSandboxClient/);
  assert.match(sandboxClientSource, /startSession\(options\?: SandboxRequestOptions\)/);
  assert.match(sandboxClientSource, /sendMessage\([\s\S]*options\?: SandboxRequestOptions/);
  assert.match(sandboxClientSource, /closeSession\([\s\S]*options\?: SandboxRequestOptions/);
  assert.match(sandboxClientSource, /signal\?: AbortSignal/);
  assert.match(sandboxClientSource, /\/web\/sandbox\/sessions/);
  assert.match(sandboxClientSource, /withAuth/);
  assert.match(sandboxClientSource, /withLocalUser/);
  assert.match(sandboxClientSource, /Accept: "text\/event-stream"/);
  assert.doesNotMatch(sandboxClientSource, /setTimeout|crypto\.randomUUID/);
});

test("new chat and global header expose the same sandbox entry", () => {
  assert.match(appSource, /variant="composer"[\s\S]*?onClick=\{openSandboxLaunch\}/);
  assert.match(appSource, /variant="header"[\s\S]*?onClick=\{openSandboxLaunch\}/);
  assert.match(sandboxSessionSource, /"灵光一现"/);
  assert.match(stylesSource, /\.sandbox-entry--composer/);
  assert.match(stylesSource, /\.sandbox-entry--header/);
});

test("sandbox launch dialog covers confirmation loading failure and retry", () => {
  assert.match(dialogSource, /role="dialog"/);
  assert.match(dialogSource, /将启动 AgentKit 沙箱来开启临时会话/);
  assert.match(dialogSource, /您的会话将不会被持久化保存/);
  assert.match(dialogSource, /正在初始化沙箱/);
  assert.match(dialogSource, /启动失败/);
  assert.match(dialogSource, /重新尝试/);
  assert.match(dialogSource, /if \(event\.key === "Escape"/);
  assert.match(appSource, /sandboxLaunchAbortRef\.current\?\.abort\(\)/);
});

test("active sandbox conversation is visibly temporary and never uses normal sessions", () => {
  assert.match(sandboxSessionSource, /当前为临时会话，退出后对话内容消失/);
  assert.match(sandboxSessionSource, /退出临时会话/);
  assert.match(appSource, /sandboxClient\.sendMessage/);
  assert.doesNotMatch(sandboxClientSource, /runSSE|listSessions/);
  assert.match(stylesSource, /\.main\.is-sandbox-session::before/);
  assert.match(stylesSource, /\.sandbox-session-warning/);
  assert.match(
    stylesSource,
    /\.sandbox-session-warning-copy[\s\S]*text-align:\s*center/,
  );
  assert.match(
    stylesSource,
    /\.sandbox-composer-wrap \.composer-box[\s\S]*grid-template-rows/,
  );
  assert.match(
    stylesSource,
    /\.main\.is-sandbox-session[\s\S]*linear-gradient\([\s\S]*to bottom/,
  );
});

test("sandbox visuals use repository-owned icons and reduced motion", () => {
  assert.match(iconSource, /export function InsightIcon/);
  assert.match(iconSource, /viewBox="0 0 24 24"/);
  assert.doesNotMatch(iconSource, /lucide-react|<img|data:image/);
  assert.match(stylesSource, /@media \(prefers-reduced-motion: reduce\)/);
});
