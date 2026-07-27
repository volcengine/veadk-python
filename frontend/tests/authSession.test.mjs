import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/adk/authSession.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const {
  AUTHENTICATION_REQUIRED_EVENT,
  authenticationRestored,
  isAuthenticationRedirect,
  isAuthenticationPending,
  waitForAuthentication,
} = await import(moduleUrl);

test("detects an API request redirected to the OAuth authorization page", () => {
  assert.equal(
    isAuthenticationRedirect({
      redirected: true,
      url: "https://example.userpool.auth.example.com/authorize?client_id=test",
    }),
    true,
  );
});

test("does not classify an ordinary API response as an expired login", () => {
  assert.equal(
    isAuthenticationRedirect({
      redirected: false,
      url: "https://studio.example.com/web/generated-agent-test-runs",
    }),
    false,
  );
});

test("notifies the app and releases waiting requests after authentication", async () => {
  const previousWindow = globalThis.window;
  const windowTarget = new EventTarget();
  globalThis.window = windowTarget;
  let notified = false;
  windowTarget.addEventListener(AUTHENTICATION_REQUIRED_EVENT, () => {
    notified = true;
  });

  try {
    const waiting = waitForAuthentication();
    assert.equal(notified, true);
    assert.equal(isAuthenticationPending(), true);
    authenticationRestored();
    await waiting;
    assert.equal(isAuthenticationPending(), false);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("an aborted caller stops waiting without cancelling global recovery", async () => {
  const previousWindow = globalThis.window;
  globalThis.window = new EventTarget();
  const controller = new AbortController();

  try {
    const waiting = waitForAuthentication(controller.signal);
    controller.abort(new Error("cancelled"));
    await assert.rejects(waiting, /cancelled/);
    assert.equal(isAuthenticationPending(), true);
    authenticationRestored();
    assert.equal(isAuthenticationPending(), false);
  } finally {
    globalThis.window = previousWindow;
  }
});
