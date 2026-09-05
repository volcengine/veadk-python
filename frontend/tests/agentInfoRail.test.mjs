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
  new URL("../src/ui/StudioToolDialog.tsx", import.meta.url),
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
  assert.match(railSource, /useTranslation\("workspaceTools"\)/);
  assert.match(railSource, /title=\{t\("agentTopology\.tools"\)\}/);
  assert.match(railSource, /title=\{t\("agentTopology\.skills"\)\}/);
  assert.match(railSource, /t\("agentTopology\.notConfigured"\)/);
  assert.doesNotMatch(railSource, /const hasTopology/);
  assert.match(railSource, /className="topo-module-card topo-tools-card"/);
  assert.match(railSource, /className="topo-module-card topo-skills-card"/);
  assert.match(railSource, /className="topo-module-card topo-topology" aria-label=\{t\("agentTopology\.agentCanvas"\)\}/);
  assert.match(railSource, /<ModuleTitle title=\{t\("agentTopology\.topology"\)\} count=\{totalNodes\(graph\)\} \/>/);
  assert.match(
    railSource,
    /<AgentBuildCanvas[\s\S]*?direction="horizontal"[\s\S]*?readOnly[\s\S]*?interactivePreview/,
  );
  assert.match(railSource, /aria-label=\{t\("agentTopology\.viewCanvasFullscreen"\)\}/);
  assert.match(railSource, /createPortal\([\s\S]*?role="dialog"[\s\S]*?aria-label=\{t\("agentTopology\.fullscreenExecutionCanvas"\)\}/);
  assert.match(railSource, /event\.key === "Escape"/);
  assert.match(railStyles, /\.topo-canvas-preview[\s\S]*?border-radius:\s*12px/);
  assert.match(railStyles, /\.topo-canvas-dialog\s*\{[\s\S]*?position:\s*fixed;[\s\S]*?inset:\s*0;/);
  assert.doesNotMatch(railSource, /className="topo-kicker"/);
  assert.match(railSource, /className="topo-module-scroll topo-tools-scroll"/);
  assert.match(railSource, /className="topo-module-scroll topo-skills-scroll"/);
  assert.match(railSource, /aria-label=\{t\("agentTopology\.toolList"\)\}[\s\S]*?tabIndex=\{0\}/);
  assert.match(railSource, /aria-label=\{t\("agentTopology\.skillList"\)\}[\s\S]*?tabIndex=\{0\}/);
  assert.match(railSource, /className="topo-skill-name"/);
  assert.doesNotMatch(railSource, /<strong>\{skill\.name\}<\/strong>/);
  assert.match(
    railSource,
    /className="topo-module-label"[\s\S]*?className="topo-section-count"[\s\S]*?\{count\}/,
  );
  assert.match(railSource, /aria-label=\{t\("agentTopology\.itemCount", \{ count \}\)\}/);
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

  const toolsIndex = railSource.indexOf('title={t("agentTopology.tools")}');
  const skillsIndex = railSource.indexOf('title={t("agentTopology.skills")}');
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

test("keeps global errors above the conversation information rail", () => {
  assert.match(
    stylesSource,
    /\.error\s*\{[^}]*position:\s*relative;[^}]*z-index:\s*3;[^}]*overflow-wrap:\s*anywhere;/,
  );
  assert.match(railStyles, /\.topo\s*\{[\s\S]*?z-index:\s*2;/);
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

test("mixes selected Studio tools into the existing tool list", () => {
  assert.match(railSource, /const selectedStudioTools = studioTools/);
  assert.match(
    railSource,
    /INTERNAL_AGENT_TOOL_NAMES = new Set\(\["StudioExternalToolset"\]\)/,
  );
  assert.match(
    railSource,
    /\.filter\(\(name\) => !INTERNAL_AGENT_TOOL_NAMES\.has\(name\)\)/,
  );
  assert.match(railSource, /selectedIds\.has\(tool\.id\)/);
  assert.match(railSource, /tool\.custom && <span className="topo-custom-badge">\{t\("agentTopology\.studioTool"\)\}<\/span>/);
  assert.match(railSource, /tool\.custom && tool\.removable && \([\s\S]*?topo-remove-capability/);
  assert.doesNotMatch(railSource, /skill\.custom/);
  assert.match(appSource, /studioTools=\{visibleStudioTools\}/);
  assert.match(appSource, /selectedStudioToolIds=\{selectedStudioToolIds\}/);
  assert.doesNotMatch(appSource, /SessionCapabilities|sessionCapabilities/);
});

test("offers only the Studio BFF tool control in the information rail", () => {
  assert.match(railSource, /t\("agentTopology\.addStudioToolHere"\)/);
  assert.doesNotMatch(railSource, /t\("agentTopology\.addSkill"\)/);
  assert.match(railSource, /className="topo-capability-add-slot"/);
  assert.match(railSource, /<StudioToolDialog/);
  assert.doesNotMatch(railSource, /<SkillCapabilityDialog/);
  assert.match(appSource, /<AgentInfoPanel[\s\S]*?onStudioToolsChange=/);
  assert.doesNotMatch(appSource, /<AgentInfoDrawer\b/);
  assert.match(railStyles, /\.topo-custom-badge/);
  assert.match(
    railStyles,
    /\.topo-skill-name\s*\{[^}]*font-family:\s*-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;/,
  );
  assert.doesNotMatch(railStyles, /\.session-skill-option-copy/);
  assert.match(railStyles, /\.topo-capability-add-slot/);
  assert.match(
    railStyles,
    /\.topo-capability-add-slot\s*\{[^}]*min-height:\s*34px;/,
  );
  assert.equal(
    (railSource.match(/className="topo-capability-add-dock"/g) ?? []).length,
    1,
  );
  assert.match(
    railStyles,
    /\.topo-capability-add-dock\s*\{[^}]*flex:\s*0 0 auto;/,
  );
  assert.match(railStyles, /\.topo-remove-capability/);
});

test("uses a searchable Studio BFF tool dialog without dynamic Skills", () => {
  assert.match(capabilityDialogsSource, /get_city_weather: "studioTools\.labels\.get_city_weather"/);
  assert.match(capabilityDialogsSource, /get_location_weather: "studioTools\.labels\.get_location_weather"/);
  assert.match(capabilityDialogsSource, /<h2 id=\{titleId\.current\}>\{t\("studioTools\.title"\)\}<\/h2>/);
  assert.match(capabilityDialogsSource, /aria-label=\{t\("studioTools\.searchAria"\)\}/);
  assert.match(capabilityDialogsSource, /t\("studioTools\.description", \{ agentName \}\)/);
  assert.match(capabilityDialogsSource, /onChange\(\[\.\.\.next\]\)/);
  assert.doesNotMatch(capabilityDialogsSource, /Skill Hub|SkillCapabilityDialog/);
  assert.doesNotMatch(clientSource, /SessionCapabilities|sessionCapabilitiesPath/);
  assert.match(skillspaceClientSource, /"\/web\/skill-spaces"/);
  assert.doesNotMatch(skillspaceClientSource, /"\/web\/skill-spaces\?region=all"/);
  assert.match(stylesSource, /\.studio-tool-dialog-layer\s*\{[\s\S]*?z-index:\s*110;/);
  assert.match(
    stylesSource,
    /\.studio-tool-search\s*\{[\s\S]*?flex:\s*0 0 40px;[\s\S]*?height:\s*40px;[\s\S]*?border-radius:\s*6px;/,
  );
});
