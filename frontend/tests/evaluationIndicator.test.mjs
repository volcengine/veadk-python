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
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

test("tracks automatic evaluation separately from reply streaming", () => {
  assert.match(appSource, /const \[evaluatingSids, setEvaluatingSids\] = useState<Set<string>>/);
  assert.match(appSource, /getAutomaticEvaluationStatuses\(\{/);
  assert.match(appSource, /status\.state === "running"/);
  assert.match(
    appSource,
    /status\.state === "pending"[\s\S]*?Date\.parse\(status\.dueAt\)/,
  );
  assert.match(appSource, /automaticEvaluationStatusRefreshRef\.current\(\)/);
  assert.doesNotMatch(appSource, /AUTO_EVALUATION_DELAY_MS/);
  assert.doesNotMatch(appSource, /scheduleAutomaticEvaluation/);
  assert.match(appSource, /evaluatingSids=\{evaluatingSids\}/);
});

test("refreshes server-owned evaluation state when the selected agent changes", () => {
  assert.match(appSource, /automaticEvaluationTargetForSelection\(connections, appName\)/);
  assert.match(appSource, /getAutomaticEvaluationStatuses\([\s\S]*?userId/);
  assert.match(appSource, /\[appName, connections, userId\]/);
  assert.match(appSource, /window\.clearTimeout\(automaticEvaluationStatusTimerRef\.current\)/);
});

test("renders an accessible evaluation status with streaming priority", () => {
  assert.match(sidebarSource, /evaluatingSids\?: Set<string>/);
  assert.match(
    sidebarSource,
    /const streaming = streamingSids\?\.has\(item\.id\) === true/,
  );
  assert.match(
    sidebarSource,
    /const evaluating = !streaming[\s\S]*?evaluatingSids\?\.has\(item\.id\) === true/,
  );
  assert.match(sidebarSource, /className="history-evaluating-status"[\s\S]*?t\("history\.evaluating"\)/);
  assert.match(stylesSource, /\.history-evaluating\s*\{[\s\S]*?animation: history-evaluation-pulse/);
  assert.match(
    stylesSource,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.history-evaluating/,
  );
});
