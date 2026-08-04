import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const railSource = readFileSync(
  new URL("../src/ui/AgentTopology.tsx", import.meta.url),
  "utf8",
);
const capabilityDialogsSource = readFileSync(
  new URL("../src/ui/SessionCapabilityDialogs.tsx", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const skillspaceClientSource = readFileSync(
  new URL("../src/create/skills/skillspace.ts", import.meta.url),
  "utf8",
);
const navbarSource = readFileSync(
  new URL("../src/ui/Navbar.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);
const railStyles = stylesSource.slice(
  stylesSource.indexOf("/* ---------- agent information rail"),
  stylesSource.indexOf("/* ---------- quick create"),
);

test("reuses loaded Agent metadata for the conversation information rail", () => {
  assert.match(appSource, /<AgentInfoPanel[\s\S]*?info=\{agentInfo\}/);
  assert.match(appSource, /<AgentInfoPanel[\s\S]*?loading=\{capabilitiesLoading\}/);
  assert.match(railSource, /info: AgentInfo \| null/);
  assert.doesNotMatch(railSource, /getAgentInfo/);
});

test("shows Agent tools, skills, and a fullscreen execution canvas", () => {
  assert.match(railSource, /Agent 信息/);
  assert.match(railSource, /title="工具"/);
  assert.match(railSource, /title="技能"/);
  assert.match(railSource, /未配置/);
  assert.doesNotMatch(railSource, /const hasTopology/);
  assert.match(railSource, /className="topo-module-card topo-tools-card"/);
  assert.match(railSource, /className="topo-module-card topo-skills-card"/);
  assert.match(railSource, /className="topo-module-card topo-topology" aria-label="Agent 画布"/);
  assert.match(railSource, /<ModuleTitle title="结构拓扑" count=\{totalNodes\(graph\)\} \/>/);
  assert.doesNotMatch(railSource, /<ModuleTitle title="画布"/);
  assert.match(
    railSource,
    /<AgentBuildCanvas[\s\S]*?direction="horizontal"[\s\S]*?readOnly[\s\S]*?interactivePreview/,
  );
  assert.match(railSource, /aria-label="全屏查看 Agent 画布"/);
  assert.match(railSource, /createPortal\([\s\S]*?role="dialog"[\s\S]*?aria-label="全屏 Agent 执行画布"/);
  assert.match(railSource, /event\.key === "Escape"/);
  assert.match(railStyles, /\.topo-canvas-preview[\s\S]*?border-radius:\s*12px/);
  assert.match(railStyles, /\.topo-canvas-dialog\s*\{[\s\S]*?position:\s*fixed;[\s\S]*?inset:\s*0;/);
  assert.doesNotMatch(railSource, /className="topo-kicker"/);
  assert.match(railSource, /className="topo-module-scroll topo-tools-scroll"/);
  assert.match(railSource, /className="topo-module-scroll topo-skills-scroll"/);
  assert.match(railSource, /aria-label="工具列表"[\s\S]*?tabIndex=\{0\}/);
  assert.match(railSource, /aria-label="技能列表"[\s\S]*?tabIndex=\{0\}/);
  assert.match(railSource, /className="topo-skill-name"/);
  assert.doesNotMatch(railSource, /<strong>\{skill\.name\}<\/strong>/);
  assert.match(
    railSource,
    /className="topo-module-label"[\s\S]*?className="topo-section-count"[\s\S]*?\{count\}/,
  );
  assert.match(railSource, /aria-label=\{`\$\{count\} 项`\}/);
  assert.doesNotMatch(railSource, /\{count\} 项<\/span>/);
  assert.match(
    railStyles,
    /\.topo-capability-name\s*\{[^}]*font-size:\s*13px;/,
  );
  assert.match(
    railStyles,
    /\.topo-skill-name\s*\{[^}]*font-size:\s*13px;/,
  );

  const agentCard = railSource.slice(
    railSource.indexOf('<section className="topo-agent-card"'),
    railSource.indexOf('<div className="topo-module-stack">'),
  );
  assert.doesNotMatch(agentCard, /AgentIdentityIcon|topo-identity-mark/);

  const toolsIndex = railSource.indexOf('title="工具"');
  const skillsIndex = railSource.indexOf('title="技能"');
  const topologyIndex = railSource.indexOf('className="topo-module-card topo-topology"');
  assert.ok(toolsIndex > -1 && skillsIndex > toolsIndex);
  assert.ok(topologyIndex > skillsIndex);
});

test("keeps Agent information out of the new-session empty state", () => {
  const emptyState = appSource.slice(
    appSource.indexOf(": turns.length === 0 ? ("),
    appSource.indexOf("className={`transcript"),
  );
  assert.doesNotMatch(emptyState, /<AgentInfoPanel/);
  assert.match(appSource, /: turns\.length === 0 \? \([\s\S]*?<AgentInfoPanel/);
  assert.doesNotMatch(appSource, /className="agent-info-trigger"/);
  assert.doesNotMatch(appSource, /<AgentInfoDrawer\b/);
});

test("places the rail on the right and protects the conversation column", () => {
  assert.match(railStyles, /\.topo\s*\{[\s\S]*?right:\s*18px;/);
  assert.match(railStyles, /\.topo\s*\{[\s\S]*?top:\s*28px;/);
  assert.match(railStyles, /\.topo\s*\{[\s\S]*?width:\s*288px;/);
  assert.match(stylesSource, /\.transcript\s*\{[^}]*padding:\s*28px 16px 8px;/);
  assert.match(railStyles, /\.topo\s*\{[\s\S]*?background:\s*hsl\(var\(--background\)\);/);
  assert.match(railStyles, /\.topo\s*\{[\s\S]*?border-radius:\s*18px;/);
  assert.match(railStyles, /\.topo-agent-card\s*\{[\s\S]*?border-bottom:/);
  assert.match(railStyles, /\.topo-module-card\s*\{[\s\S]*?background:\s*transparent;/);
  assert.match(railStyles, /\.topo-module-card\s*\{[^}]*border:\s*0;/);
  assert.match(railStyles, /\.topo-module-card \+ \.topo-module-card\s*\{[\s\S]*?border-top:/);
  assert.match(railStyles, /\.topo-module-title\s*\{[\s\S]*?position:\s*static;/);
  assert.match(railStyles, /\.topo-module-title\s*\{[\s\S]*?color:\s*hsl\(var\(--muted-foreground\)\);/);
  assert.match(railStyles, /\.topo-module-title\s*\{[^}]*line-height:\s*1;/);
  assert.match(railStyles, /\.topo-module-label\s*\{[^}]*align-items:\s*center;/);
  assert.match(railStyles, /\.topo-section-count\s*\{[\s\S]*?border-radius:\s*999px;/);
  assert.match(railStyles, /\.topo-section-count\s*\{[\s\S]*?font-size:\s*11px;/);
  assert.match(railStyles, /\.topo-skill-name\s*\{[\s\S]*?font-weight:\s*500;/);
  assert.doesNotMatch(railStyles, /\.topo-section-count\s*\{[^}]*position:\s*absolute;/);
  assert.match(railStyles, /\.topo-tools-scroll\s*\{\s*max-height:/);
  assert.match(railStyles, /\.topo-skills-scroll\s*\{\s*max-height:/);
  assert.match(railStyles, /\.topo-canvas-preview\s*\{[\s\S]*?min-height:\s*120px;/);
  assert.match(railStyles, /\.topo-module-scroll\s*\{[^}]*padding-top:\s*9px;/);
  assert.match(railStyles, /\.topo-tool:first-child\s*\{\s*padding-top:\s*0;/);
  assert.match(railStyles, /\.topo-skill:first-child\s*\{\s*padding-top:\s*0;/);
  assert.match(railStyles, /\.topo-module-scroll:focus-visible/);
  assert.match(railStyles, /\.topo\s*\{[\s\S]*?overflow:\s*hidden;/);
  assert.match(railStyles, /\.topo-module-stack\s*\{[\s\S]*?grid-template-rows:/);
  assert.doesNotMatch(railStyles, /\.topo\s*\{[^}]*left:\s*18px;/);
  assert.match(railStyles, /\.main:has\(> \.topo\) > \.transcript/);
  assert.match(appSource, /className="conversation-composer-slot"/);
  assert.match(
    railStyles,
    /\.main:has\(> \.topo\) > \.conversation-composer-slot\s*\{[\s\S]*?padding-right:\s*322px;/,
  );
  assert.doesNotMatch(railStyles, /\.main:has\(> \.topo\) > \.composer[\s\S]*?transform:/);
  assert.match(railStyles, /@media \(max-width:\s*1279px\)/);
});

test("keeps Agent information in the conversation rail without a title trigger", () => {
  assert.match(navbarSource, /titleLeading\?: ReactNode/);
  assert.match(navbarSource, /\{titleLeading\}/);
  assert.doesNotMatch(appSource, /className="agent-info-trigger"/);
  assert.doesNotMatch(appSource, /<AgentInfoDrawer\b/);
  assert.match(appSource, /<AgentInfoPanel[\s\S]*?info=\{agentInfo\}/);
  assert.match(railSource, /export function AgentInfoDrawer/);
  assert.match(railSource, /event\.key === "Escape"/);
  assert.match(railSource, /returnFocusRef\.current\?\.focus\(\)/);
  assert.match(railStyles, /\.drawer--agent-info/);
  assert.match(railStyles, /@media \(min-width:\s*1280px\)[\s\S]*?\.agent-info-trigger/);
});

test("keeps capability section titles text-only", () => {
  const moduleTitleSource = railSource.slice(
    railSource.indexOf("function ModuleTitle"),
    railSource.indexOf("interface AgentInfoPanelProps"),
  );
  assert.doesNotMatch(moduleTitleSource, /Icon/);
  assert.doesNotMatch(railSource, /ToolCapabilityIcon/);
  assert.doesNotMatch(railSource, /SkillCapabilityIcon/);
  assert.doesNotMatch(railSource, /topo-section-icon/);
  assert.doesNotMatch(railStyles, /\.topo-section-icon/);
  assert.match(railSource, /import \{ Maximize2, X \} from "lucide-react"/);
});

test("mixes session capabilities into the existing lists with custom badges", () => {
  assert.match(railSource, /capabilities\?\.tools/);
  assert.match(railSource, /capabilities\?\.skills/);
  assert.match(railSource, /tool\.custom && <span className="topo-custom-badge">自定义<\/span>/);
  assert.match(railSource, /skill\.custom && <span className="topo-custom-badge">自定义<\/span>/);
  assert.match(railSource, /tool\.custom && \([\s\S]*?topo-remove-capability/);
  assert.match(railSource, /skill\.custom && \([\s\S]*?topo-remove-capability/);
  assert.doesNotMatch(railSource, /本会话添加/);
  assert.match(appSource, /getSessionCapabilities\(appName, userId, sessionId\)/);
  assert.match(
    appSource,
    /sessionCapabilities:\s*requiresSessionCapabilityRunner\(sessionCapabilities\)/,
  );
});

test("offers session-scoped tool and skill controls in the information rail", () => {
  assert.match(railSource, /aria-label="添加内置工具"/);
  assert.match(railSource, /aria-label="添加技能"/);
  assert.match(railSource, /<span>在此对话中添加工具<\/span>/);
  assert.match(railSource, /<span>在此对话中添加技能<\/span>/);
  assert.match(railSource, /className="topo-capability-add-slot"/);
  assert.match(railSource, /<ToolCapabilityDialog/);
  assert.match(railSource, /<SkillCapabilityDialog/);
  assert.doesNotMatch(railSource, /placeholder="Skill Space ID"/);
  assert.match(appSource, /<AgentInfoPanel[\s\S]*?capabilities=\{sessionCapabilities\}/);
  assert.doesNotMatch(appSource, /<AgentInfoDrawer\b/);
  assert.match(railStyles, /\.topo-custom-badge/);
  assert.match(
    railStyles,
    /\.topo-skill-name\s*\{[^}]*font-family:\s*-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;/,
  );
  assert.match(
    railStyles,
    /\.session-skill-option-copy strong\s*\{[^}]*font-family:\s*-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;/,
  );
  assert.match(railStyles, /\.topo-capability-add-slot/);
  assert.match(
    railStyles,
    /\.topo-capability-add-slot\s*\{[^}]*min-height:\s*34px;/,
  );
  assert.equal(
    (railSource.match(/className="topo-capability-add-dock"/g) ?? []).length,
    2,
  );
  assert.match(
    railStyles,
    /\.topo-capability-add-dock\s*\{[^}]*flex:\s*0 0 auto;/,
  );
  assert.match(railStyles, /\.topo-remove-capability/);
});

test("uses searchable dialogs for public Skill Hub and AgentKit Skill Center", () => {
  assert.match(capabilityDialogsSource, /get_city_weather: "城市天气查询"/);
  assert.match(capabilityDialogsSource, /get_location_weather: "位置天气查询"/);
  assert.ok(
    capabilityDialogsSource.includes('return description.replace(/[。.]+$/, "");'),
  );
  assert.match(capabilityDialogsSource, /title="添加内置工具"/);
  assert.match(capabilityDialogsSource, /label="搜索内置工具"/);
  assert.match(capabilityDialogsSource, /title="添加技能"/);
  assert.match(capabilityDialogsSource, /role="tablist" aria-label="技能来源"/);
  assert.match(capabilityDialogsSource, />\s*Skill Hub\s*<span>公域<\/span>/);
  assert.match(capabilityDialogsSource, /AgentKit Skill 中心/);
  assert.match(capabilityDialogsSource, /searchSessionPublicSkills\(appName, publicQuery\.trim\(\)\)/);
  assert.match(capabilityDialogsSource, /skillSourceId: `findskill:\$\{skill\.slug\}`/);
  assert.match(clientSource, /\/harness\/skills\/findskill/);
  assert.match(capabilityDialogsSource, /listSkillSpaces\(\)/);
  assert.match(
    capabilityDialogsSource,
    /listSkillsInSpace\(selectedSpace\.id, selectedSpace\.region\)/,
  );
  assert.doesNotMatch(capabilityDialogsSource, /listSessionSkillSpaces/);
  assert.doesNotMatch(capabilityDialogsSource, /listSessionSkillsInSpace/);
  assert.match(skillspaceClientSource, /"\/web\/skill-spaces\?region=all"/);
  assert.match(capabilityDialogsSource, /label="搜索 Skill Space"/);
  assert.match(capabilityDialogsSource, /label="搜索 AgentKit 技能"/);
  assert.match(capabilityDialogsSource, /skillSourceId: selectedSpace\.id/);
  assert.match(capabilityDialogsSource, /name: skill\.skillName/);
  assert.match(stylesSource, /\.session-skill-browser\s*\{[\s\S]*?grid-template-columns:/);
  assert.match(stylesSource, /\.session-capability-dialog-layer\s*\{[\s\S]*?z-index:\s*110;/);
  assert.match(
    stylesSource,
    /\.session-capability-dialog\.is-wide\s*\{[^}]*height:\s*min\(720px, calc\(100dvh - 48px\)\);/,
  );
  assert.doesNotMatch(capabilityDialogsSource, /SkillCapabilityIcon|SkillSpaceIcon/);
  assert.match(capabilityDialogsSource, /session-capability-dialog-head\$\{icon \? "" : " is-iconless"\}/);
  assert.doesNotMatch(
    stylesSource,
    /\.session-public-skill-head\s*\{[^}]*border-bottom:/,
  );
  assert.doesNotMatch(
    stylesSource,
    /\.session-skill-pane-head\s*\{[^}]*border-bottom:/,
  );
  assert.match(
    stylesSource,
    /\.session-capability-search\s*\{[\s\S]*?flex:\s*0 0 40px;[\s\S]*?height:\s*40px;[\s\S]*?border-radius:\s*6px;/,
  );
});
