import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const dialogSource = readFileSync(
  new URL("../src/ui/AuthExpiredDialog.tsx", import.meta.url),
  "utf8",
);

test("the global authentication event opens a blocking relogin dialog", () => {
  assert.match(appSource, /setAuthExpired\(true\)/);
  assert.match(appSource, /authenticationRestored\(\)/);
  assert.match(appSource, /isAuthenticationPending\(\)/);
  assert.match(appSource, /openLoginWindow\(\)/);
  assert.match(dialogSource, /role="alertdialog"/);
  assert.match(dialogSource, /aria-modal="true"/);
  assert.match(dialogSource, /重新登录/);
  assert.match(dialogSource, /当前编辑内容会保留/);
});

test("API requests recover only after a confirmed authentication failure", () => {
  assert.match(clientSource, /isAuthenticationRedirect\(response\)/);
  assert.match(clientSource, /response\.status !== 401/);
  assert.match(clientSource, /isOAuthLoginRequired\(\)/);
  assert.match(clientSource, /const operationSignal = requestSignal\(init\.signal, timeoutMs\)/);
  assert.match(clientSource, /waitForAuthentication\(operationSignal\)/);
});
