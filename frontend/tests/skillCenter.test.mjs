import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const skillCenterSource = readFileSync(
  new URL("../src/ui/SkillCenter.tsx", import.meta.url),
  "utf8",
);
const skillspaceSource = readFileSync(
  new URL("../src/create/skills/skillspace.ts", import.meta.url),
  "utf8",
);
const markdownSource = readFileSync(
  new URL("../src/ui/Markdown.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);
const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);

test("skill center defaults to paged AgentKit Skill space browsing", () => {
  assert.match(appSource, /AgentKit Skill 空间/);
  assert.doesNotMatch(skillCenterSource, /Find Skill|findskill|SKILL_URL|skill-frame/);
  assert.match(skillCenterSource, /useState<SkillRegion>\("cn-beijing"\)/);
  assert.match(skillCenterSource, /changeRegion\("cn-shanghai"\)/);
  assert.doesNotMatch(skillCenterSource, /changeRegion\("all"\)/);
  assert.match(appSource, /\[\{ label: "技能中心" \}, \{ label: "AgentKit Skill 空间" \}\]/);
  assert.match(
    skillCenterSource,
    /<h2>技能空间<\/h2>\s*<span className="skillcenter-count-badge">\{spaceTotal\}<\/span>[\s\S]*?<div className="skillcenter-regions"/,
  );
  assert.match(skillCenterSource, /点击 Skill 空间以查看详情/);
  assert.doesNotMatch(skillCenterSource, /items\[0\]/);
});

test("space and skill requests are paged server-side without exposing credentials", () => {
  assert.match(skillspaceSource, /export async function listSkillSpacesPage/);
  assert.match(skillspaceSource, /export async function listSkillsInSpacePage/);
  assert.match(skillspaceSource, /page_size: String\(options\.pageSize\)/);
  assert.match(skillspaceSource, /params\.set\("project", options\.project\)/);
  assert.match(skillCenterSource, /<Pager page=\{spacePage\}/);
  assert.match(skillCenterSource, /<Pager page=\{skillPage\}/);
  assert.doesNotMatch(skillCenterSource, /VOLCENGINE_ACCESS_KEY|VOLCENGINE_SECRET_KEY/);
});

test("skill details render external markdown with raw HTML disabled", () => {
  assert.match(markdownSource, /allowRawHtml = true/);
  assert.match(
    markdownSource,
    /rehypePlugins=\{allowRawHtml \? \[rehypeRaw, rehypeHighlight\] : \[rehypeHighlight\]\}/,
  );
  assert.match(
    skillCenterSource,
    /text=\{skillMarkdownBody\(detail\.skillMd\)\}/,
  );
  assert.match(skillCenterSource, /function skillMarkdownBody/);
  assert.match(skillCenterSource, /numeric \* 1000/);
  assert.match(skillCenterSource, /detailRequest\.current/);
  assert.match(skillCenterSource, /closeDetail\(\);\s*setRegion/);
});

test("skill browser uses adjacent bounded panels and stacks on narrow screens", () => {
  assert.match(stylesSource, /\.skillcenter-browser\s*\{[^}]*display:\s*grid;/);
  assert.match(stylesSource, /\.skillcenter-browser\s*\{[^}]*gap:\s*0;/);
  assert.match(stylesSource, /\.skillcenter\s*\{[^}]*padding:\s*0;/);
  assert.match(stylesSource, /\.skillcenter-panel\s*\{[^}]*min-height:\s*0;[^}]*overflow:\s*hidden;/);
  assert.match(stylesSource, /\.skillcenter-panel \+ \.skillcenter-panel\s*\{[^}]*border-left:/);
  assert.doesNotMatch(stylesSource, /\.skillcenter-panel\s*\{[^}]*border-radius:/);
  assert.match(stylesSource, /\.skillcenter-listwrap\s*\{[^}]*flex:\s*1;[^}]*min-height:\s*0;[^}]*overflow-y:\s*auto;/);
  assert.match(stylesSource, /\.skillcenter-pager\s*\{[^}]*flex:\s*0 0 44px;/);
  assert.match(
    stylesSource,
    /@media \(max-width: 760px\)[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\);/,
  );
  assert.match(stylesSource, /\.skillcenter-item-title\s*\{[^}]*text-overflow:\s*ellipsis;/);
  assert.match(stylesSource, /\.skillcenter-item-description\s*\{[^}]*overflow-wrap:\s*anywhere;/);
  assert.match(
    stylesSource,
    /\.skillcenter-space-item\.active\s*\{[^}]*border-color:\s*transparent;[^}]*background:\s*hsl\(var\(--muted\)/,
  );
  assert.match(
    stylesSource,
    /\.skillcenter-space-item:focus-visible,[\s\S]*?outline:\s*none;[\s\S]*?border-color:\s*transparent;/,
  );
});

test("Skill Space and Skill marks are local SVGs", () => {
  assert.match(skillCenterSource, /function SkillSpaceIcon/);
  assert.match(skillCenterSource, /function SkillIcon/);
  assert.doesNotMatch(
    skillCenterSource,
    /className="skillcenter-skill-item"[\s\S]{0,250}skillcenter-symbol/,
  );
  assert.doesNotMatch(
    skillCenterSource,
    /className=\{`skillcenter-space-item[\s\S]{0,250}skillcenter-symbol/,
  );
  assert.doesNotMatch(skillCenterSource, /skillcenter-panel-head">\s*<div><Skill/);
  assert.doesNotMatch(skillCenterSource, /from "lucide-react"/);
});
