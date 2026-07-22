import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const navbarSource = readFileSync(
  new URL("../src/ui/Navbar.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

test("uses the active session name in the conversation header", () => {
  assert.match(appSource, /function activeSessionTitle/);
  assert.match(appSource, /sessionTitle\(session\?\.events\)/);
  assert.match(appSource, /turn\.role !== "user"/);
  assert.match(appSource, /: conversationTitle/);
});

test("keeps long session names inside the available header width", () => {
  assert.match(navbarSource, /className="navbar-title" title=\{title\}/);
  assert.match(
    stylesSource,
    /\.navbar-title\s*\{[^}]*max-width:\s*min\(60vw, 640px\)[^}]*text-overflow:\s*ellipsis[^}]*white-space:\s*nowrap/,
  );
});
