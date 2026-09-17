import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);

const reconcileResult = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/transcriptReconcile.ts", import.meta.url)),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const reconcileUrl = "data:text/javascript;base64," + Buffer.from(
  reconcileResult.outputFiles[0].contents,
).toString("base64");
const { reconcilePersistedTranscript } = await import(reconcileUrl);

test("conversation reports a completed stream that has no final displayable reply", () => {
  assert.match(appSource, /let hasCompletedReply = false/);
  assert.match(
    appSource,
    /projection\.completed &&[\s\S]*?turnHasVisibleContent\(projection\.turn\)[\s\S]*?hasCompletedReply = true/,
  );
  assert.match(
    appSource,
    /for \(const unfinished of eventProjector\.finish\(\)\) \{[\s\S]*?turnHasVisibleContent\(unfinished\)[\s\S]*?hasCompletedReply = true/,
  );
  assert.match(
    appSource,
    /!ctrl\.signal\.aborted && !streamFailed && !hasCompletedReply[\s\S]*?runSseIncompleteResponseError\(\)[\s\S]*?setError/,
  );
  assert.match(appSource, /eventProjector\.finish\(\)[\s\S]*?if \(\s*!ctrl\.signal\.aborted && !streamFailed && !hasCompletedReply/);
  assert.match(appSource, /finally \{[\s\S]*?streamFailed[\s\S]*?setInput\(\(current\) => current\.trim\(\) \? current : text\)/);
});

test("MPA session refresh keeps history listing lightweight and reconciles the active transcript after success", () => {
  const clientImport = appSource.match(
    /import \{[^}]*\} from "\.\/adk\/client";/s,
  )?.[0] ?? "";
  const blocksImport = appSource.match(
    /import \{[^}]*\} from "\.\/blocks";/s,
  )?.[0] ?? "";
  assert.match(clientImport, /isMpaRuntimeApp/);
  assert.doesNotMatch(blocksImport, /isMpaRuntimeApp/);
  assert.match(
    appSource,
    /const list = await listSessions\(appName, userId\);[\s\S]*?if \(isMpaRuntimeApp\(appName\)\) return list;/,
  );
  assert.match(
    appSource,
    /async function refreshSessionTranscript\([\s\S]*?expectedEventId: string,[\s\S]*?\): Promise<void> \{[\s\S]*?const session = await getSession\(app, userId, sid\);[\s\S]*?eventsToTurns\(session\.events \?\? \[\], session\.state\)/,
  );
  assert.match(
    appSource,
    /reconcilePersistedTranscript\([\s\S]*?existing,[\s\S]*?nextTurns,[\s\S]*?expectedEventId/,
  );
  assert.match(
    appSource,
    /reconciled === existing[\s\S]*?\? current[\s\S]*?: \{ \.\.\.current, \[sid\]: reconciled \}/,
  );
  assert.match(
    appSource,
    /void refreshSessions\(appName\);[\s\S]*?if \(!ctrl\.signal\.aborted && !streamFailed && finalEventId\) \{[\s\S]*?void refreshSessionTranscript\(appName, sid, finalEventId\);/,
  );
});

test("transcript reconciliation rejects a stale multi-turn snapshot", () => {
  const firstUser = { role: "user", blocks: [{ kind: "text", text: "first" }] };
  const firstReply = {
    role: "assistant",
    blocks: [{ kind: "text", text: "first answer" }],
    meta: { eventId: "event-old" },
  };
  const latestUser = { role: "user", blocks: [{ kind: "text", text: "latest" }] };
  const latestReply = {
    role: "assistant",
    blocks: [{ kind: "text", text: "latest answer" }],
    meta: { eventId: "event-latest" },
  };
  const current = [firstUser, firstReply, latestUser, latestReply];
  const stale = [firstUser, firstReply, latestUser];

  assert.equal(
    reconcilePersistedTranscript(current, stale, "event-latest"),
    current,
  );
});

test("transcript reconciliation accepts only the matching latest reply", () => {
  const current = [
    { role: "user", blocks: [{ kind: "text", text: "latest" }] },
    {
      role: "assistant",
      blocks: [{ kind: "text", text: "live answer" }],
      meta: { eventId: "event-latest" },
    },
  ];
  const persisted = [
    current[0],
    {
      role: "assistant",
      blocks: [{ kind: "text", text: "persisted answer" }],
      meta: { eventId: "event-latest" },
    },
  ];
  assert.equal(
    reconcilePersistedTranscript(current, persisted, "event-latest"),
    persisted,
  );

  const newerStream = [
    ...current,
    { role: "user", blocks: [{ kind: "text", text: "newer" }] },
    {
      role: "assistant",
      blocks: [{ kind: "thinking", text: "working", done: false }],
      meta: { localId: "newer-stream", streaming: true },
    },
  ];
  assert.equal(
    reconcilePersistedTranscript(newerStream, persisted, "event-latest"),
    newerStream,
  );
});

test("conversation keeps aborts separate from unexpected stream failures", () => {
  assert.match(
    appSource,
    /\(e as Error\)\?\.name !== "AbortError"[\s\S]*?!ctrl\.signal\.aborted/,
  );
  assert.match(
    appSource,
    /e instanceof Error \? e\.message : String\(e\)/,
  );
  assert.match(appSource, /streamFailed = true;\s*streamError = e;/);
});

test("function-response recovery rejects partial-only and empty resumed streams", () => {
  const onAuthSource = appSource.slice(
    appSource.indexOf("async function onAuth"),
    appSource.indexOf("// Hooks must stay above", appSource.indexOf("async function onAuth")),
  );
  assert.match(onAuthSource, /let streamFailed = false;[\s\S]*?let hasCompletedReply = false/);
  assert.match(
    onAuthSource,
    /projection\.completed &&[\s\S]*?turnHasVisibleContent\(projection\.turn\)[\s\S]*?hasCompletedReply = true/,
  );
  assert.match(
    onAuthSource,
    /!ctrl\.signal\.aborted && !streamFailed && !hasCompletedReply[\s\S]*?runSseIncompleteResponseError\(\)[\s\S]*?setError/,
  );
  assert.match(onAuthSource, /catch \(e\) \{\s*streamFailed = true;/);
  assert.match(onAuthSource, /setError\(e instanceof Error \? e\.message : String\(e\)\)/);
});
