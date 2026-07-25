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
  assert.doesNotMatch(railSource, /getAgentInfo|useState/);
});

test("shows Agent tools and skills before the optional topology", () => {
  assert.match(railSource, /Agent 信息/);
  assert.match(railSource, /title="工具"/);
  assert.match(railSource, /title="技能"/);
  assert.match(railSource, /未配置/);
  assert.match(railSource, /const hasTopology = graph\.children\.length > 0/);
  assert.match(railSource, /className="topo-module-card topo-tools-card"/);
  assert.match(railSource, /className="topo-module-card topo-skills-card"/);
  assert.match(railSource, /className="topo-module-card topo-topology"/);
  assert.match(railSource, /单 Agent，无协作拓扑/);
  assert.doesNotMatch(railSource, /className="topo-kicker"/);
  assert.match(railSource, /className="topo-module-scroll topo-tools-scroll"/);
  assert.match(railSource, /className="topo-module-scroll topo-skills-scroll"/);
  assert.match(railSource, /className="topo-module-scroll topo-topology-scroll"/);
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
    appSource.indexOf(") : (\n              <>\n                <div className=\"transcript\""),
  );
  assert.doesNotMatch(emptyState, /<AgentInfoPanel/);
  assert.match(appSource, /turns\.length > 0[\s\S]*?className="agent-info-trigger"/);
  assert.match(appSource, /agentInfoOpen && turns\.length > 0/);
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
  assert.match(railStyles, /\.topo-topology-scroll\s*\{\s*max-height:/);
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

test("opens the same Agent information from a narrow-screen title trigger", () => {
  assert.match(navbarSource, /titleLeading\?: ReactNode/);
  assert.match(navbarSource, /\{titleLeading\}/);
  assert.match(appSource, /className="agent-info-trigger"/);
  assert.match(appSource, /aria-label="查看 Agent 信息"/);
  assert.match(appSource, /<AgentInfoDrawer[\s\S]*?info=\{agentInfo\}/);
  assert.match(railSource, /export function AgentInfoDrawer/);
  assert.match(railSource, /event\.key === "Escape"/);
  assert.match(railSource, /returnFocusRef\.current\?\.focus\(\)/);
  assert.match(appSource, /onClose=\{closeAgentInfo\}/);
  assert.match(railStyles, /\.drawer--agent-info/);
  assert.match(railStyles, /@media \(min-width:\s*1280px\)[\s\S]*?\.agent-info-trigger/);
});

test("uses repository-owned capability icons in the updated rail", () => {
  assert.match(railSource, /AgentIdentityIcon/);
  assert.match(railSource, /ToolCapabilityIcon/);
  assert.match(railSource, /SkillCapabilityIcon/);
  assert.doesNotMatch(railSource, /from "lucide-react"/);
});
