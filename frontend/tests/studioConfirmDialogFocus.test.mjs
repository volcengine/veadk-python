import assert from "node:assert/strict";
import test from "node:test";
import { createServer } from "vite";

const server = await createServer({
  configFile: new URL("../vite.config.ts", import.meta.url).pathname,
  appType: "custom",
  logLevel: "silent",
  server: { middlewareMode: true, hmr: false, port: 0 },
});

test.after(async () => {
  await server.close();
});

const { trapStudioConfirmDialogFocus } = await server.ssrLoadModule(
  "/src/ui/StudioConfirmDialog.tsx",
);

function focusTarget(name, focused) {
  return {
    focus() {
      focused.push(name);
    },
  };
}

function tabEvent({ shiftKey = false } = {}) {
  return {
    key: "Tab",
    shiftKey,
    defaultPrevented: false,
    preventDefault() {
      this.defaultPrevented = true;
    },
  };
}

test("Studio confirmation keeps forward and reverse Tab focus inside the dialog", () => {
  assert.equal(typeof trapStudioConfirmDialogFocus, "function");

  const focused = [];
  const first = focusTarget("first", focused);
  const middle = focusTarget("middle", focused);
  const last = focusTarget("last", focused);
  const dialog = {
    querySelectorAll() {
      return [first, middle, last];
    },
  };

  const forward = tabEvent();
  trapStudioConfirmDialogFocus(forward, dialog, last);
  assert.equal(forward.defaultPrevented, true);
  assert.deepEqual(focused, ["first"]);

  focused.length = 0;
  const reverse = tabEvent({ shiftKey: true });
  trapStudioConfirmDialogFocus(reverse, dialog, first);
  assert.equal(reverse.defaultPrevented, true);
  assert.deepEqual(focused, ["last"]);
});

test("Studio confirmation recovers focus when Tab starts outside the dialog", () => {
  assert.equal(typeof trapStudioConfirmDialogFocus, "function");

  const focused = [];
  const first = focusTarget("first", focused);
  const last = focusTarget("last", focused);
  const dialog = {
    querySelectorAll() {
      return [first, last];
    },
  };

  const forward = tabEvent();
  trapStudioConfirmDialogFocus(forward, dialog, {});
  assert.equal(forward.defaultPrevented, true);
  assert.deepEqual(focused, ["first"]);

  focused.length = 0;
  const reverse = tabEvent({ shiftKey: true });
  trapStudioConfirmDialogFocus(reverse, dialog, {});
  assert.equal(reverse.defaultPrevented, true);
  assert.deepEqual(focused, ["last"]);
});

test("busy Studio confirmation keeps Tab focus on the dialog when every action is disabled", () => {
  assert.equal(typeof trapStudioConfirmDialogFocus, "function");

  const focused = [];
  const dialog = {
    querySelectorAll() {
      return [];
    },
    focus() {
      focused.push("dialog");
    },
  };
  const forward = tabEvent();

  trapStudioConfirmDialogFocus(forward, dialog, {});

  assert.equal(forward.defaultPrevented, true);
  assert.deepEqual(focused, ["dialog"]);
});
