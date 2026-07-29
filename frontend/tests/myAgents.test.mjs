import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const pageSource = readFileSync(
  new URL("../src/ui/MyAgents.tsx", import.meta.url),
  "utf8",
);
const pageStyles = readFileSync(
  new URL("../src/ui/MyAgents.css", import.meta.url),
  "utf8",
);
const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

test("shows only the Agent navigation in the sidebar", () => {
  assert.match(sidebarSource, /onMyAgents: \(\) => void/);
  assert.doesNotMatch(sidebarSource, /onManageAgents/);
  assert.doesNotMatch(sidebarSource, /aria-label="智能体库"/);
  assert.match(
    sidebarSource,
    /onClick=\{onMyAgents\}[\s\S]*?aria-label="智能体"[\s\S]*?<ManageAgentsIcon \/>/,
  );
  assert.match(appSource, /const openMyAgentsPage = \(\) => \{/);
  assert.match(appSource, /<Sidebar[\s\S]*?onMyAgents=\{openMyAgentsPage\}/);
  assert.match(appSource, /myAgents \? \([\s\S]*?<MyAgents/);
});

test("shows four agent families with a dashed add card first", () => {
  for (const title of ["通用智能体", "Codex 智能体", "OpenClaw 智能体", "Hermes 智能体"]) {
    assert.match(pageSource, new RegExp(`title: "${title}"`));
  }
  assert.match(
    pageSource,
    /<div className="my-agent-grid" ref=\{gridRef\}>[\s\S]*?className="my-agent-add"[\s\S]*?visibleAgents\.map/,
  );
  assert.match(pageStyles, /\.my-agent-add\s*\{[\s\S]*?border: 1px dashed/);
  assert.match(pageStyles, /\.my-agent-card,\s*\.my-agent-add\s*\{[\s\S]*?aspect-ratio: 1;/);
});

test("renders only account-backed agents and never ships placeholder cards", () => {
  assert.doesNotMatch(pageSource, /STATIC_SECTIONS/);
  assert.doesNotMatch(
    pageSource,
    /codex-code-review|codex-test-coverage|openclaw-research|hermes-data-analysis/,
  );
  assert.equal(
    (pageSource.match(/title: "通用智能体", agents: runtimeAgents/g) ?? []).length,
    1,
  );
  for (const title of ["Codex 智能体", "OpenClaw 智能体", "Hermes 智能体"]) {
    assert.match(pageSource, new RegExp(`title: "${title}", agents: \\[\\]`));
  }
});

test("agent cards keep only requested information and actions", () => {
  assert.match(pageSource, /<h3>\{agent\.name\}<\/h3>/);
  assert.match(pageSource, /\{agent\.description\}/);
  assert.match(pageSource, /<dt>工具<\/dt>/);
  assert.match(pageSource, /<dt>技能<\/dt>/);
  assert.match(pageSource, /<dt>创建时间<\/dt>/);
  assert.match(pageSource, /connected \? "已连接" : "使用"/);
  assert.match(pageSource, />\s*查看详情\s*<\/button>/);
  assert.doesNotMatch(pageSource, /<small|<code/);
  assert.doesNotMatch(pageStyles, /font-family/);
});

test("uses a compact shadcn-style card grid with horizontal footer actions", () => {
  assert.match(
    pageStyles,
    /\.my-agent-grid\s*\{[\s\S]*?grid-template-columns: repeat\(auto-fill, minmax\(min\(174px, 100%\), 1fr\)\)/,
  );
  assert.doesNotMatch(pageStyles, /\.my-agent-grid\s*\{[^}]*justify-content:/);
  assert.doesNotMatch(pageStyles, /justify-content: space-between/);
  assert.match(
    pageStyles,
    /\.my-agent-actions\s*\{[\s\S]*?grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/,
  );
  assert.doesNotMatch(pageStyles, /\.my-agent-actions\s*\{[^}]*border-top:/);
  assert.doesNotMatch(pageStyles, /\.my-agent-actions\s*\{[^}]*background:/);
  assert.match(pageStyles, /\.my-agent-actions button\s*\{[\s\S]*?border-radius:/);
});

test("add card uses only the requested plus icon and regular text weight", () => {
  assert.match(pageSource, /import \{ Plus \} from "lucide-react"/);
  assert.match(pageSource, /<Plus aria-hidden="true" \/>[\s\S]*?<span>添加智能体<\/span>/);
  assert.match(pageStyles, /\.my-agent-add\s*\{[\s\S]*?font-weight: 400/);
});

test("tool and skill counts render as compact labels", () => {
  assert.match(pageSource, /<dt>工具<\/dt>[\s\S]*?<dd>\{agent\.toolCount\} 个<\/dd>/);
  assert.match(pageSource, /<dt>技能<\/dt>[\s\S]*?<dd>\{agent\.skillCount\} 个<\/dd>/);
  assert.match(pageStyles, /\.my-agent-label\s*\{[\s\S]*?border-radius:/);
  assert.match(pageStyles, /\.my-agent-label dt,[\s\S]*?font-weight: 400/);
  assert.match(pageStyles, /\.my-agent-created-at dd\s*\{[\s\S]*?font-weight: 400/);
});

test("distributes responsive card columns across the available width", () => {
  assert.doesNotMatch(pageStyles, /\.my-agent-card,[\s\S]*?\.my-agent-add\s*\{[^}]*max-width:/);
  assert.match(pageSource, /const MIN_CARD_WIDTH = 174/);
});

test("loads owned runtimes into the general agents section", () => {
  assert.match(pageSource, /getRuntimes/);
  assert.match(pageSource, /scope: "mine"/);
  assert.match(pageSource, /getRuntimeAgentInfo/);
  assert.match(pageSource, /id: runtime\.runtimeId/);
  assert.match(pageSource, /runtimeId: runtime\.runtimeId/);
  assert.match(pageSource, /region: runtime\.region/);
  assert.match(pageSource, /<AgentCard[\s\S]*?key=\{agent\.id\}/);
  assert.match(pageSource, /title: "通用智能体"[\s\S]*?agents: runtimeAgents/);
  assert.match(pageSource, /pageSize,/);
  assert.match(
    pageSource,
    /onPageSizeChange\?\.\(Math\.max\(1, nextColumns \* MAX_ROWS - 1\)\)/,
  );
  assert.match(pageSource, /onList\(page\.runtimes\.map\(runtimeToAgent\)\)/);
  assert.match(pageSource, /void fetchRuntimePage\(runtimePage \+ 1, runtimeNextToken, runtimePageSize\)/);
  assert.match(pageSource, /runtimeRequestRef\.current !== requestId/);
  assert.match(pageSource, /if \(page > 1 && count === 0\)/);
  assert.match(pageSource, /className="my-agent-loading"/);
  assert.match(pageSource, /className="loading-gap-spinner"/);
  assert.match(pageStyles, /\.my-agent-loading\s*\{[\s\S]*?position: absolute/);
});

test("wires general agent creation, details, and use actions into App navigation", () => {
  assert.match(pageSource, /onClick=\{onCreateAgent\}/);
  assert.match(pageSource, /onClick=\{\(\) => void onUse\?\.\(agent\)\}/);
  assert.match(pageSource, /onClick=\{\(\) => onViewDetails\?\.\(agent\)\}/);
  assert.match(pageSource, /onCreateAgent=\{createActions\[index\]\}/);
  assert.match(appSource, /const openAgentCreateFromMyAgents/);
  assert.match(appSource, /const connectMyAgent[\s\S]*?connectRuntime[\s\S]*?startNewChat\(\)[\s\S]*?setAppName\(agentId\)/);
  assert.match(appSource, /const openMyAgentDetails[\s\S]*?setAgentDetailTarget\(agent\)[\s\S]*?setManageAgents\(true\)/);
  assert.doesNotMatch(appSource, /const openMyAgentDetails[\s\S]*?connectRuntime\(/);
  assert.match(appSource, /const detailAgentEntry:[\s\S]*?id: `detail:\$\{agentDetailTarget\.runtime\.runtimeId\}`/);
  assert.match(appSource, /<MyAgents[\s\S]*?onCreateAgent=\{openAgentCreateFromMyAgents\}[\s\S]*?onUseAgent=/);
});

test("routes add cards to Codex launch and coming-soon flows", () => {
  assert.match(pageSource, /onCreateCodexAgent: \(\) => void/);
  assert.match(
    pageSource,
    /const createActions = \[[\s\S]*?onCreateAgent,[\s\S]*?onCreateCodexAgent,[\s\S]*?undefined,[\s\S]*?undefined,[\s\S]*?\]/,
  );
  assert.match(pageSource, /onCreateAgent=\{createActions\[index\]\}/);
  assert.match(pageSource, /title: "OpenClaw 智能体", agents: \[\], comingSoon: true/);
  assert.match(pageSource, /title: "Hermes 智能体", agents: \[\], comingSoon: true/);
  assert.match(pageSource, /className="my-agent-coming-soon-overlay" role="status"[\s\S]*?敬请期待/);
  assert.match(pageStyles, /\.my-agent-coming-soon-overlay\s*\{[\s\S]*?position: absolute[\s\S]*?inset: 0/);
  assert.match(appSource, /onCreateCodexAgent=\{openSandboxLaunch\}/);
  assert.match(appSource, /function openSandboxLaunch\(\)[\s\S]*?setSandboxLaunchOpen\(true\)/);
  assert.match(
    appSource,
    /async function launchSandboxSession\(\)[\s\S]*?setSandboxSession\(nextSession\)[\s\S]*?setAgentDetailTarget\(null\)[\s\S]*?setMyAgents\(false\)[\s\S]*?setSandboxLaunchOpen\(false\)/,
  );
});

test("shows connecting progress and preserves the connected Runtime state", () => {
  assert.match(pageSource, /const \[connectingAgentId, setConnectingAgentId\] = useState\(""\)/);
  assert.match(
    pageSource,
    /setConnectingAgentId\(agent\.id\)[\s\S]*?requestAnimationFrame[\s\S]*?await onUseAgent\(agent\)[\s\S]*?setConnectingAgentId\(""\)/,
  );
  assert.match(pageSource, /aria-busy=\{connecting \|\| undefined\}/);
  assert.match(pageSource, /className="my-agent-use-spinner"[\s\S]*?<span>连接中<\/span>/);
  assert.match(pageSource, /connected \? "已连接" : "使用"/);
  assert.match(pageSource, /disabled=\{!agent\.runtime \|\| connecting \|\| connected\}/);
  assert.match(appSource, /connectedRuntimeId=\{currentRuntime\?\.runtimeId\}/);
  assert.match(pageStyles, /\.my-agent-use-spinner\s*\{[\s\S]*?border-right-color: transparent/);
  assert.match(
    pageStyles,
    /\.my-agent-actions \.my-agent-use\.is-connected,[\s\S]*?background: hsl\(142 55% 94%\)[\s\S]*?color: hsl\(142 62% 30%\)/,
  );
});

test("prompts users to choose an Agent only while disconnected", () => {
  assert.match(
    pageSource,
    /!connectedRuntimeId && \([\s\S]*?className="my-agents-connect-banner" role="status"[\s\S]*?请选择一个智能体以对话/,
  );
  assert.match(pageStyles, /\.my-agents-connect-banner\s*\{[\s\S]*?margin-bottom:\s*24px;/);
  assert.match(appSource, /connectedRuntimeId=\{currentRuntime\?\.runtimeId\}/);
});

test("authenticated users land on the Agent page by default", () => {
  assert.match(appSource, /if \(id\.status === "authenticated"\)[\s\S]*?setMyAgents\(true\)/);
  assert.match(appSource, /function onUsername[\s\S]*?startNewChat\(\);[\s\S]*?setMyAgents\(true\)/);
  assert.match(appSource, /defaultViewAppliedRef\.current \|\| myAgents/);
});

test("limits every agent family to two responsive rows with independent pagination", () => {
  assert.match(pageSource, /const MAX_ROWS = 2/);
  assert.match(pageSource, /pageSize = Math\.max\(1, columns \* MAX_ROWS - 1\)/);
  assert.match(pageSource, /useState\(1\)/);
  assert.match(pageSource, /className="my-agent-pagination"/);
  assert.match(pageSource, /aria-label="上一页"[\s\S]*?>\s*‹\s*<\/button>/);
  assert.match(pageSource, /aria-label="下一页"[\s\S]*?>\s*›\s*<\/button>/);
  assert.match(pageStyles, /\.my-agent-pagination\s*\{[\s\S]*?justify-content: center/);
  assert.match(pageSource, /serverPagination \? currentPage : `\$\{page\} \/ \$\{pageCount\}`/);
});
