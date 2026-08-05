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
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);
test("skill center defaults to paged AgentKit Skill Space cards", () => {
  assert.doesNotMatch(skillCenterSource, /Find Skill|findskill|SKILL_URL|skill-frame/);
  assert.match(skillCenterSource, /defaultCloudRegion\(cloudProvider\)/);
  assert.match(skillCenterSource, /cloudRegionOptions\(cloudProvider\)/);
  assert.match(skillCenterSource, /changeRegion\(option\.value\)/);
  assert.match(
    skillCenterSource,
    /focus\?\.region \?\? defaultCloudRegion\(cloudProvider\)/,
  );
  assert.doesNotMatch(skillCenterSource, /changeRegion\("all"\)/);
  assert.match(skillCenterSource, /<h1>\{selectedSpace\?\.name \|\| "技能中心"\}<\/h1>/);
  assert.match(skillCenterSource, /className="skillcenter-space-grid"/);
  assert.match(skillCenterSource, /className="skillcenter-space-card"/);
  assert.match(skillCenterSource, /查看技能/);
  assert.match(skillCenterSource, /返回技能空间/);
  assert.match(
    skillCenterSource,
    /items\.find\(\(space\) => space\.id === current\?\.id\)\s*\|\| null/,
  );
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

test("SkillSpace downloads prefer full package files over SKILL.md only", () => {
  assert.match(skillspaceSource, /files\?: ProjectFile\[\]/);
  assert.match(
    skillspaceSource,
    /Array\.isArray\(d\.files\) && d\.files\.length > 0\) return d\.files/,
  );
});

test("ZIP selection rejects files above the server-advertised upload limit", () => {
  assert.match(
    skillCenterSource,
    /nextFile\.size > capability\.maxUploadBytes/,
  );
  assert.match(skillCenterSource, /Skill ZIP 不能超过/);
  assert.match(skillCenterSource, /setComposerError/);
});

test("skill details show the complete package in a read-only file browser", () => {
  assert.match(skillCenterSource, /<CodeBrowserWorkspace/);
  assert.match(skillCenterSource, /detail\.files\?\.length/);
  assert.match(skillCenterSource, /\[\{ path: "SKILL\.md", content: detail\.skillMd \}\]/);
  assert.match(skillCenterSource, /readOnly/);
  assert.doesNotMatch(skillCenterSource, /allowRawHtml/);
  assert.match(skillCenterSource, /numeric \* 1000/);
  assert.match(skillCenterSource, /detailRequest\.current/);
  assert.match(skillCenterSource, /closeDetail\(\);\s*setRegion/);
});

test("skill browser uses bounded card grids and resilient long text", () => {
  assert.match(stylesSource, /\.skillcenter\s*\{[^}]*padding:\s*32px 32px 0;/);
  assert.match(stylesSource, /\.skillcenter-results\s*\{[^}]*overflow-y:\s*auto;/);
  assert.match(stylesSource, /\.skillcenter-space-grid\s*\{[^}]*display:\s*grid;/);
  assert.match(stylesSource, /\.skillcenter-space-card\s*\{[^}]*border-radius:\s*8px;/);
  assert.match(stylesSource, /\.skillcenter-skill-grid\s*\{[^}]*display:\s*grid;/);
  assert.match(stylesSource, /\.skillcenter-pager\s*\{[^}]*flex:\s*0 0 44px;/);
  assert.match(stylesSource, /\.skillcenter-item-title\s*\{[^}]*text-overflow:\s*ellipsis;/);
  assert.match(stylesSource, /\.skillcenter-item-description\s*\{[^}]*overflow-wrap:\s*anywhere;/);
  assert.match(stylesSource, /@media \(max-width: 760px\)/);
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
