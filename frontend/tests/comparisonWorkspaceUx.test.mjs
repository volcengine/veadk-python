import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const customCreateCss = readFileSync(
  new URL("../src/create/CustomCreate.css", import.meta.url),
  "utf8",
);
const comparisonTraceSource = readFileSync(
  new URL(
    "../src/create/comparison/ComparisonTraceDrawer.tsx",
    import.meta.url,
  ),
  "utf8",
);
const comparisonDrawerUrl = new URL(
  "../src/create/comparison/ComparisonDrawer.tsx",
  import.meta.url,
);
const comparisonDrawerSource = existsSync(comparisonDrawerUrl)
  ? readFileSync(comparisonDrawerUrl, "utf8")
  : "";

test("keeps comparison controls outside the shared message composer", () => {
  assert.match(customCreateSource, /className="cw-comparison-toolbar"/);
  assert.match(customCreateSource, /className="cw-comparison-toolbar-actions"/);
  assert.doesNotMatch(customCreateSource, /转入场景评测（API 待接入）/);

  const composerStart = customCreateSource.indexOf(
    '<div className="cw-ab-composer">',
  );
  const composerEnd = customCreateSource.indexOf(
    "{editingVariant ? (",
    composerStart,
  );
  const composer = customCreateSource.slice(composerStart, composerEnd);
  assert.ok(composer, "shared composer should remain present");
  assert.doesNotMatch(composer, /添加对照组|对齐 Trace|停止全部|最近对照记录/);
});

test("uses progressive disclosure for risk, baseline detail, and history", () => {
  assert.match(customCreateSource, /aria-expanded=\{safetyExpanded\}/);
  assert.match(customCreateSource, /查看全部配置/);
  assert.match(customCreateSource, /最近对照记录/);
  assert.match(customCreateSource, /setBaselineDrawerOpen\(true\)/);
  assert.match(customCreateSource, /setHistoryDrawerOpen\(true\)/);
});

test("shows concrete candidate differences before the conversation", () => {
  const summaryStart = customCreateSource.indexOf(
    "function DebugVariantDifferenceSummary(",
  );
  assert.ok(summaryStart >= 0, "candidate difference summary should exist");
  const summaryEnd = customCreateSource.indexOf(
    "function DebugVariantConfigurationPanel(",
    summaryStart,
  );
  const summarySource = customCreateSource.slice(summaryStart, summaryEnd);
  assert.match(summarySource, /与基准组的配置差异/);
  assert.match(summarySource, /aria-expanded=\{expanded\}/);
  assert.match(summarySource, /aria-controls=\{contentId\}/);
  assert.match(summarySource, /查看全部 \$\{totalCount\} 项/);
  assert.match(summarySource, /收起，仅显示前 \$\{COMPARISON_DIFF_PREVIEW_LIMIT\} 项/);

  const diffLinesStart = customCreateSource.indexOf(
    "function debugChangeDiffLines(",
  );
  assert.ok(diffLinesStart >= 0, "structured difference lines should exist");
  const diffLinesSource = customCreateSource.slice(
    diffLinesStart,
    summaryStart,
  );
  assert.match(diffLinesSource, /label: "Model ID"/);
  assert.match(diffLinesSource, /label: "Provider"/);
  assert.match(diffLinesSource, /label: "API Base"/);
  assert.match(diffLinesSource, /label: "凭据"/);
  assert.match(diffLinesSource, /baseline\.instruction \|\| "空提示词"/);
  assert.doesNotMatch(diffLinesSource, /baseline:\s*baseline\.apiKey/);
  assert.doesNotMatch(diffLinesSource, /candidate:\s*change\.apiKey/);
  const credentialStart = customCreateSource.indexOf(
    "function debugCredentialLabel(",
  );
  const credentialSource = customCreateSource.slice(
    credentialStart,
    diffLinesStart,
  );
  assert.match(credentialSource, /change\.apiKeyLocked \|\| change\.apiKey/);
  assert.match(credentialSource, /临时凭据已配置/);
  assert.match(credentialSource, /服务端凭据/);

  const cardStart = customCreateSource.indexOf("{variants.map((variant");
  const cardEnd = customCreateSource.indexOf(
    '<div className="cw-comparison-verdict">',
    cardStart,
  );
  const cardSource = customCreateSource.slice(cardStart, cardEnd);
  const summaryPosition = cardSource.indexOf("<DebugVariantDifferenceSummary");
  const conversationPosition = cardSource.indexOf(
    'className="cw-ab-conversation"',
  );
  assert.ok(summaryPosition >= 0, "candidate card should render the summary");
  assert.ok(
    summaryPosition < conversationPosition,
    "candidate differences should appear before the conversation",
  );
  assert.doesNotMatch(
    customCreateSource,
    /<details className="cw-comparison-diffs">/,
  );
});

test("keeps candidate differences compact and keyboard readable", () => {
  assert.match(
    customCreateCss,
    /\.cw-comparison-diff-summary\s*\{[^}]*border:\s*1px solid hsl\(var\(--border\)\)/s,
  );
  assert.match(
    customCreateCss,
    /\.cw-comparison-diff-long\s*\{[^}]*-webkit-line-clamp:\s*2/s,
  );
  assert.match(
    customCreateCss,
    /\.cw-comparison-diff-long:focus-visible\s*\{[^}]*-webkit-line-clamp:\s*unset/s,
  );
  assert.match(
    customCreateCss,
    /\.cw-comparison-diff-toggle:focus-visible/,
  );
  assert.doesNotMatch(
    customCreateCss,
    /\.cw-comparison-diff-summary\s*\{[^}]*box-shadow:/s,
  );
});

test("renders comparison configuration in an accessible 720px drawer", () => {
  assert.match(comparisonDrawerSource, /role="dialog"/);
  assert.match(comparisonDrawerSource, /aria-modal="true"/);
  assert.match(comparisonDrawerSource, /document\.body\.style\.overflow/);
  assert.match(comparisonDrawerSource, /event\.key === "Escape"/);
  assert.match(customCreateCss, /\.cw-comparison-drawer\s*\{[^}]*width:\s*min\(720px,/s);
  assert.match(customCreateSource, /<ComparisonDrawer/);
});

test("uses Studio confirmation dialogs for destructive debug actions", () => {
  const destructiveDebugActions = customCreateSource.slice(
    customCreateSource.indexOf("const removeDebugVariant"),
    customCreateSource.indexOf("const handleDeploy"),
  );
  assert.doesNotMatch(destructiveDebugActions, /window\.confirm\(/);
  assert.match(customCreateSource, /删除测试组/);
});

test("uses the shared comparison drawer for Trace alignment", () => {
  assert.match(comparisonTraceSource, /ComparisonDrawer/);
  assert.match(comparisonTraceSource, /width="wide"/);
  assert.doesNotMatch(comparisonTraceSource, /<aside className="drawer/);
});

test("uses a bounded VE-O workspace and standard comparison cards", () => {
  assert.match(customCreateCss, /\.cw-root\.is-validate\s*\{[^}]*1260px/s);
  assert.match(customCreateCss, /\.cw-workspace-footer\s*\{[^}]*min-height:\s*64px/s);
  assert.match(customCreateCss, /\.cw-ab-card\s*\{[^}]*border:\s*1px solid/s);
  assert.doesNotMatch(customCreateCss, /\.cw-ab-card\s*\{[^}]*border:\s*1px dashed/s);
});
