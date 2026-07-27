import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const blocksModelSource = readFileSync(
  new URL("../src/blocks.ts", import.meta.url),
  "utf8",
);
const blocksViewSource = readFileSync(
  new URL("../src/ui/Blocks.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

test("preserves the emitting Agent on history and live assistant turns", () => {
  assert.match(blocksModelSource, /author\?: string/);
  assert.match(blocksModelSource, /last\.meta\?\.author !== author/);
  assert.match(blocksModelSource, /meta\.author = author/);
  assert.match(appSource, /currentStreamAuthor/);
  assert.match(appSource, /last\.meta(?:\?\.|\.)author === currentStreamAuthor/);
  assert.match(appSource, /author: currentStreamAuthor/);
});

test("models transfer_to_agent without rendering a separate event row", () => {
  assert.match(blocksModelSource, /kind: "agent-transfer"/);
  assert.match(blocksModelSource, /fc\.name === TRANSFER_AGENT_TOOL/);
  assert.match(blocksModelSource, /fr\.name === TRANSFER_AGENT_TOOL/);
  assert.match(blocksViewSource, /case "agent-transfer":\s*return null;/);
  assert.match(appSource, /turn\.blocks\.every\(\(block\) => block\.kind === "agent-transfer"\)/);
});

test("groups child Agent work in an identified muted execution card", () => {
  assert.match(appSource, /className="subagent-run-label"/);
  assert.match(appSource, /className="subagent-run-handoff"/);
  assert.match(appSource, /<span>智能体移交<\/span>/);
  assert.match(appSource, /className="subagent-run-title">\{agentDisplayName\}/);
  assert.match(appSource, /className="subagent-run-description"/);
  assert.match(appSource, /turn--subagent/);
  assert.match(appSource, /agentNode\?\.description/);
  assert.match(stylesSource, /\.turn--subagent\s*\{/);
  assert.match(stylesSource, /\.turn--subagent\s*\{[^}]*backdrop-filter:\s*blur\(18px\)/s);
  assert.match(stylesSource, /\.turn--subagent::before\s*\{[^}]*radial-gradient/s);
  assert.match(stylesSource, /\.subagent-run-label\s*\{[^}]*position:\s*absolute/s);
  assert.match(stylesSource, /\.subagent-run-title\s*\{[^}]*font-size:\s*14\.5px[^}]*font-weight:\s*400/s);
  assert.match(stylesSource, /\.turn--subagent \.turn-meta\s*\{[^}]*position:\s*absolute/s);
  assert.match(appSource, /<CornerDownRight \/>/);
  assert.match(stylesSource, /\.subagent-run-description\s*\{[^}]*font-size:\s*13\.5px/s);
  assert.doesNotMatch(stylesSource, /\.subagent-run-description\s*\{[^}]*border-bottom/s);
  assert.match(stylesSource, /@media \(max-width: 700px\)[\s\S]*?\.turn--subagent/);
});
