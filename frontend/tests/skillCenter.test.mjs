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
const skillStylesSource = readFileSync(
  new URL("../src/ui/skills/skills.css", import.meta.url),
  "utf8",
);
const myAgentsStylesSource = readFileSync(
  new URL("../src/ui/MyAgents.css", import.meta.url),
  "utf8",
);
const fileTreeSource = readFileSync(
  new URL("../src/ui/skills/SkillFileTree.tsx", import.meta.url),
  "utf8",
);
const generationSource = readFileSync(
  new URL("../src/ui/skills/SkillGenerationWorkspace.tsx", import.meta.url),
  "utf8",
);
const configSelectSource = readFileSync(
  new URL("../src/ui/skills/SkillConfigSelect.tsx", import.meta.url),
  "utf8",
);
const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);
const skillIconSource = readFileSync(
  new URL("../src/ui/icons/SkillIcon.tsx", import.meta.url),
  "utf8",
);
const managementClientSource = readFileSync(
  new URL("../src/adk/skills.ts", import.meta.url),
  "utf8",
);
const managementDialogsSource = readFileSync(
  new URL("../src/ui/skills/SkillManagementDialogs.tsx", import.meta.url),
  "utf8",
);
const errorDetailsSource = readFileSync(
  new URL("../src/ui/skills/SkillErrorDetails.tsx", import.meta.url),
  "utf8",
);
test("skill center uses the Studio page shell and opens spaces as a detail page", () => {
  assert.doesNotMatch(skillCenterSource, /Find Skill|findskill|SKILL_URL|skill-frame/);
  assert.match(skillCenterSource, /defaultCloudRegion\(cloudProvider\)/);
  assert.match(skillCenterSource, /cloudRegionOptions\(cloudProvider\)/);
  assert.match(skillCenterSource, /Promise\.allSettled\(requests\.map/);
  assert.doesNotMatch(skillCenterSource, /changeRegion\(|skillcenter-region-pills/);
  assert.match(skillCenterSource, /<h1>技能<\/h1>/);
  assert.match(skillCenterSource, /管理您的 Skill 空间，创建、查看和优化技能/);
  assert.match(skillCenterSource, /className="my-agent-search"/);
  assert.match(skillCenterSource, /className="my-agent-grid"/);
  assert.match(skillCenterSource, /className="my-agent-card skillcenter-space-card"/);
  assert.match(skillCenterSource, /className="skillcenter-page-heading skillcenter-page-heading--back"/);
  assert.doesNotMatch(skillCenterSource, /skillcenter-browser|点击 Skill 空间以查看详情/);
  assert.doesNotMatch(skillCenterSource, /items\[0\]/);
  assert.doesNotMatch(skillCenterSource, />Project</);
});

test("space and skill requests are paged server-side without sending browser credentials", () => {
  assert.match(skillspaceSource, /export async function listSkillSpacesPage/);
  assert.match(skillspaceSource, /export async function listSkillsInSpacePage/);
  assert.match(skillspaceSource, /page_size: String\(options\.pageSize\)/);
  assert.match(skillspaceSource, /params\.set\("project", options\.project\)/);
  assert.match(skillCenterSource, /listManagedSkillSpaces\(\{/);
  assert.match(skillCenterSource, /spaceRegions\.map\(\(region\) => \(\{ region, page: 1 \}\)\)/);
  assert.match(skillCenterSource, /new IntersectionObserver\(/);
  assert.match(skillCenterSource, /rootMargin: "240px 0px"/);
  assert.doesNotMatch(skillCenterSource, /<Pager page=\{spacePage\}/);
  assert.match(skillCenterSource, /<Pager page=\{skillPage\}/);
  assert.doesNotMatch(skillCenterSource, /VOLCENGINE_ACCESS_KEY|VOLCENGINE_SECRET_KEY/);
});

test("Skill errors preserve and render upstream error details", () => {
  assert.match(managementClientSource, /readonly originalError\?: SkillApiOriginalError/);
  assert.match(managementClientSource, /readonly rawResponse = ""/);
  assert.match(managementClientSource, /const rawResponse = await response\.text\(\)/);
  assert.match(errorDetailsSource, /原始错误：\{originalMessage\}/);
  assert.match(errorDetailsSource, /HTTP \$\{metadata\.status\}/);
  assert.match(errorDetailsSource, /服务端原始响应/);
  assert.match(errorDetailsSource, /<summary>详细信息<\/summary>/);
  assert.match(skillCenterSource, /errors\.map\(\(\{ region, error \}\) =>/);
  assert.match(skillCenterSource, /<SkillErrorDetails error=\{error\} \/>/);
});

test("SkillSpace downloads prefer full package files over SKILL.md only", () => {
  assert.match(skillspaceSource, /files\?: ProjectFile\[\]/);
  assert.match(
    skillspaceSource,
    /Array\.isArray\(d\.files\) && d\.files\.length > 0\) return d\.files/,
  );
});

test("skill details render external markdown with raw HTML disabled", () => {
  assert.match(markdownSource, /allowRawHtml = true/);
  assert.match(
    markdownSource,
    /rehypePlugins=\{allowRawHtml \? \[rehypeRaw, rehypeHighlight\] : \[rehypeHighlight\]\}/,
  );
  assert.match(skillCenterSource, /<SkillFileTree files=\{files\.map\(/);
  assert.match(skillCenterSource, /skillMarkdownBody\(file\.content\)/);
  assert.match(fileTreeSource, /import \{ parseDocument, stringify \} from "yaml"/);
  assert.match(fileTreeSource, /function parseMarkdownDocument/);
  assert.match(fileTreeSource, /text=\{markdownDocument\.body\} allowRawHtml=\{false\}/);
  assert.match(fileTreeSource, /className="skill-file-preview__frontmatter"/);
  assert.match(skillCenterSource, /function skillMarkdownBody/);
  assert.match(skillCenterSource, /numeric \* 1000/);
  assert.match(skillCenterSource, /detailRequest\.current/);
  assert.match(skillCenterSource, /selectedSpace\?\.region \|\| defaultCloudRegion\(cloudProvider\)/);
});

test("skills navigation sits immediately below agents", () => {
  const agents = sidebarSource.indexOf('className={`new-chat new-chat--agents');
  const skills = sidebarSource.indexOf('className={`new-chat new-chat--skills');
  const search = sidebarSource.indexOf('{show("search")', skills);

  assert.ok(agents >= 0 && skills > agents);
  assert.ok(search > skills);
  assert.match(sidebarSource, /import \{ SkillIcon \} from "\.\/icons\/SkillIcon"/);
  assert.match(sidebarSource.slice(agents, search), /<SkillIcon className="icon" \/>/);
  assert.doesNotMatch(sidebarSource.slice(agents, search), /sidebar-nav-slot/);
  assert.match(skillIconSource, /viewBox="0 0 24 24"/);
  assert.match(skillIconSource, /aria-hidden="true"/);
  assert.match(sidebarSource.slice(agents, search), />技能<\/span>/);
});

test("Skill workbench supports one to three independent model and style groups", () => {
  assert.match(generationSource, /const MAX_GROUPS = 3/);
  assert.match(generationSource, /models\[index % Math\.max\(1, capability\.models\.length\)\]/);
  assert.match(generationSource, /value: "custom", label: "自定义"/);
  assert.match(generationSource, /自定义风格/);
  assert.match(generationSource, /await Promise\.all\(groups\.map\(createRun\)\)/);
  assert.match(generationSource, /const MAX_AUTO_REPAIRS = 2/);
  assert.match(generationSource, /function isFormatValidationFailure/);
  assert.match(generationSource, /正在自动修复（\$\{attempt\}\/\$\{MAX_AUTO_REPAIRS\}）/);
  assert.match(generationSource, /await refineSkillWorkbenchTask\(/);
  assert.match(generationSource, /再次修复/);
  assert.match(generationSource, /pollError: normalizeSkillError\(error, "读取候选方案状态失败，正在重试"\)/);
  assert.match(generationSource, /window\.setTimeout\(\(\) => void poll\(\), POLL_INTERVAL_MS\)/);
  assert.doesNotMatch(generationSource, /window\.setInterval\(\(\) => void poll\(\), POLL_INTERVAL_MS\)/);
  assert.match(generationSource, />生成<\/button>/);
  assert.doesNotMatch(generationSource, /任务中心|恢复任务|task center/i);
});

test("Skill generation setup follows Studio form and select conventions", () => {
  assert.doesNotMatch(generationSource, /<select\b|<option\b/);
  assert.match(generationSource, /<SkillConfigSelect/);
  assert.match(generationSource, /className="skill-generation__add-group"/);
  assert.match(generationSource, /aria-label="返回技能空间"/);
  assert.match(generationSource, /<BackIcon \/>/);
  assert.match(generationSource, /<strong>基本信息<\/strong>/);
  assert.match(generationSource, /<strong>生成方案<\/strong>/);
  assert.match(generationSource, /按不同方案并行生成多个技能，您可以选择最佳结果/);
  assert.doesNotMatch(generationSource, /火山引擎|BytePlus/);
  assert.match(skillStylesSource, /\.skill-generation__add-group\s*\{[^}]*border:\s*1px dashed/);
  assert.match(skillStylesSource, /\.skill-generation__header\s*\{[^}]*padding:\s*32px 32px 0;/);
  assert.doesNotMatch(skillStylesSource, /\.skill-generation__header\s*\{[^}]*border-bottom:/);
  assert.match(skillStylesSource, /\.skill-generation__setup\s*\{[^}]*margin:\s*21px 29px 0;[^}]*padding:\s*3px 3px 48px;/);
  assert.doesNotMatch(skillStylesSource, /\.skill-generation__setup\s*\{[^}]*(?:border|background):/);
  assert.match(skillStylesSource, /\.skill-generation textarea,\s*\.skill-generation input\s*\{[^}]*font-weight:\s*400;/);
  assert.match(skillStylesSource, /\.skill-config-select__trigger\s*\{[^}]*font-weight:\s*400;/);
  assert.match(skillStylesSource, /\.skill-config-select__option\s*\{[^}]*font-weight:\s*400;/);

  assert.match(configSelectSource, /aria-haspopup="listbox"/);
  assert.match(configSelectSource, /role="combobox"/);
  assert.match(configSelectSource, /aria-autocomplete="list"/);
  assert.match(configSelectSource, /nativeEvent\.isComposing/);
  assert.match(generationSource, /allowCustom/);
  assert.match(generationSource, /选择或输入模型 ID/);
  assert.match(generationSource, /function modelNameProblem/);
  assert.match(configSelectSource, /role="listbox"/);
  assert.match(configSelectSource, /role="option"/);
  assert.match(configSelectSource, /event\.key === "Escape"/);
  assert.match(configSelectSource, /event\.key === "ArrowDown"/);
  assert.match(configSelectSource, /addEventListener\("wheel", handleWheel, \{ passive: false \}\)/);
  assert.match(configSelectSource, /event\.preventDefault\(\)/);
  assert.match(configSelectSource, /event\.stopPropagation\(\)/);
  assert.match(skillStylesSource, /\.skill-config-select__menu\s*\{[^}]*overscroll-behavior:\s*contain;/);
});

test("Skill name validation is immediate, specific, and blocks generation", () => {
  assert.match(generationSource, /name\.length > 64/);
  assert.match(generationSource, /Skill 名称不能超过 64 个字符/);
  assert.match(generationSource, /\^\[a-z0-9-\]\+\$/);
  assert.match(generationSource, /Skill 名称只能包含小写字母、数字和连字符/);
  assert.match(generationSource, /aria-invalid=\{Boolean\(nameError\)\}/);
  assert.match(generationSource, /role="alert"/);
  assert.match(generationSource, /&& !nameError/);
});

test("managed Skill APIs cover space creation, archives, deletion, and full files", () => {
  assert.match(managementClientSource, /export async function createSkillSpace/);
  assert.match(managementClientSource, /export async function updateSkillSpace/);
  assert.match(managementClientSource, /export async function deleteSkillSpace/);
  assert.match(managementClientSource, /export async function uploadSkillArchive/);
  assert.match(managementClientSource, /export async function validateSkillArchive/);
  assert.match(managementClientSource, /export async function deleteManagedSkill/);
  assert.match(managementClientSource, /export async function getManagedSkillFiles/);
  assert.match(managementClientSource, /export async function downloadManagedSkillArchive/);
  assert.match(managementDialogsSource, /await validateSkillArchive\(selected\)/);
  assert.match(managementDialogsSource, /export function EditSkillSpaceDialog/);
  assert.match(skillCenterSource, /role="menuitem"[^>]*>编辑空间<\/button>/);
  assert.match(skillCenterSource, /role="menuitem"[^>]*>删除空间<\/button>/);
  assert.match(managementDialogsSource, /不会自动上传/);
  assert.match(managementDialogsSource, /!validation \|\| validating \|\| submitting/);
});

test("skill pages match the Studio page spacing, search, and card grid", () => {
  assert.match(skillStylesSource, /\.skillcenter\s*\{[^}]*overflow:\s*hidden;[^}]*padding:\s*32px 32px 0;/);
  assert.match(skillCenterSource, /import "\.\/MyAgents\.css"/);
  assert.match(skillCenterSource, /className="my-agents-header"/);
  assert.match(skillCenterSource, /className="my-agent-results"[\s\S]{0,120}ref=\{spaceResultsRef\}/);
  assert.match(myAgentsStylesSource, /\.my-agent-grid\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fill, minmax\(min\(280px, 100%\), 1fr\)\);/);
  assert.match(myAgentsStylesSource, /\.my-agent-card-content\s*\{[^}]*border-radius:\s*12px;/);
  assert.match(skillStylesSource, /\.my-agent-card\.skillcenter-space-card:hover\s*\{\s*transform:\s*none;/);
  assert.doesNotMatch(skillStylesSource, /\.my-agent-card\.skillcenter-space-card:hover \.my-agent-card-content/);
  assert.doesNotMatch(stylesSource, /\.skillcenter-browser\s*\{/);
});

test("Skill space cards keep menus usable and load more while scrolling", () => {
  assert.match(skillCenterSource, /onScroll=\{handleSpaceResultsScroll\}/);
  assert.match(skillCenterSource, /results\.scrollHeight - results\.scrollTop - results\.clientHeight <= 240/);
  assert.match(skillCenterSource, /event\.stopPropagation\(\);\s*setOpenSpaceMenuId/);
  assert.match(skillCenterSource, /onPointerDown=\{\(event\) => event\.stopPropagation\(\)\}/);
  assert.match(skillStylesSource, /\.my-agent-card\.skillcenter-space-card\s*\{\s*overflow:\s*visible;/);
  assert.match(skillStylesSource, /\.my-agent-actions\.skillcenter-card-actions\s*\{[^}]*z-index:\s*2;/);
});

test("Skill upload uses a large drag-and-drop target", () => {
  assert.match(managementDialogsSource, /onDragOver=/);
  assert.match(managementDialogsSource, /onDrop=/);
  assert.match(managementDialogsSource, /拖拽 Skill ZIP 到这里/);
  assert.match(skillStylesSource, /\.skill-upload-dropzone\s*\{[^}]*min-height:\s*min\(42vh, 360px\);/);
});

test("Skill pages avoid decorative icons and use a semantic table", () => {
  assert.doesNotMatch(skillCenterSource, /function SkillSpaceIcon|function SkillIcon/);
  assert.doesNotMatch(skillCenterSource, /skillcenter-card-icon|skillcenter-symbol/);
  assert.doesNotMatch(skillCenterSource, /<EmptyMessage\.Icon>/);
  assert.match(skillCenterSource, /<table className="skillcenter-table">/);
  assert.match(skillCenterSource, /<th scope="col">技能<\/th>/);
  assert.doesNotMatch(skillCenterSource, /<th scope="col">版本<\/th>/);
  assert.match(skillCenterSource, /className="skillcenter-table__version-badge"/);
  assert.match(skillCenterSource, /className="skillcenter-detail-facts"/);
  assert.match(skillCenterSource, /<dl className="my-agent-meta">/);
  assert.doesNotMatch(skillCenterSource, /from "lucide-react"/);
});

test("skill space cards expose direct actions and structured metadata", () => {
  assert.match(skillCenterSource, /className="my-agent-actions skillcenter-card-actions"/);
  assert.match(skillCenterSource, />添加技能<\/button>/);
  assert.match(skillCenterSource, />查看详情<\/button>/);
  assert.match(skillCenterSource, /aria-label=\{`更多空间操作：\$\{space\.name\}`\}/);
  assert.match(skillCenterSource, /role="menu" aria-label=\{`\$\{space\.name\}空间操作`\}/);
  assert.doesNotMatch(skillCenterSource, /<small>地域<\/small>/);
  assert.match(skillCenterSource, /<dt>技能数量<\/dt><dd>/);
  assert.match(skillCenterSource, /<dt>更新时间<\/dt><dd>/);
  assert.doesNotMatch(skillCenterSource, /<small>Project<\/small>/);
  assert.doesNotMatch(skillCenterSource, /<span>地域<\/span>/);
  const detailToolbarStart = skillCenterSource.indexOf('className="skillcenter-detail-facts"');
  const detailResultsStart = skillCenterSource.indexOf("{actionError ?", detailToolbarStart);
  const detailToolbar = skillCenterSource.slice(detailToolbarStart, detailResultsStart);
  assert.doesNotMatch(detailToolbar, />编辑空间<\/button>|>删除空间<\/button>/);
  assert.match(detailToolbar, />本地上传<\/button>/);
  assert.match(detailToolbar, />创建技能<\/span>/);
});

test("Skill running states, actions, and candidate loading use the requested visual hierarchy", () => {
  assert.doesNotMatch(skillStylesSource, /\.skillcenter-space-card\s*\{[^}]*min-height:\s*196px/);
  assert.match(skillStylesSource, /\.skillcenter-primary-action,[\s\S]*?height:\s*36px/);
  assert.match(skillStylesSource, /\.skillcenter-primary-action,[\s\S]*?box-sizing:\s*border-box/);
  assert.match(skillStylesSource, /\.my-agent-actions\.skillcenter-card-actions\s*\{[^}]*grid-template-columns:/);
  assert.match(myAgentsStylesSource, /\.my-agent-actions button\s*\{[^}]*min-height:\s*28px/);
  assert.match(generationSource, /className="skill-generation__spinner"/);
  assert.match(generationSource, /className="skill-generation__summary-row"><span>风格<\/span>/);
  assert.match(generationSource, /className="skill-generation__summary-row"><span>模型<\/span>/);
  assert.match(generationSource, /className="skill-generation__summary-row"><span>进度<\/span>/);
  const candidateView = generationSource.slice(generationSource.indexOf('className="skill-generation__candidate-tabs"'));
  assert.doesNotMatch(candidateView, /方案 \{index \+ 1\}|runs\.indexOf\(active\)/);
  assert.doesNotMatch(candidateView, /className="skill-generation__status"/);
  assert.match(skillStylesSource, /\.skill-generation__spinner\s*\{[^}]*animation:/);
  assert.match(skillStylesSource, /@media \(prefers-reduced-motion: reduce\)/);
});

test("Skill detail actions keep their labels on one line", () => {
  assert.match(skillStylesSource, /\.skill-detail-actions\s*\{[^}]*flex:\s*0 0 auto/);
  assert.match(skillStylesSource, /\.skill-detail-actions button\s*\{[^}]*white-space:\s*nowrap/);
});

test("disabled Dev Sandbox actions explain the missing configuration on hover and focus", () => {
  assert.match(skillCenterSource, /function SandboxDisabledAction/);
  assert.match(skillCenterSource, /tabIndex=\{disabled \? 0 : undefined\}/);
  assert.match(skillCenterSource, /aria-describedby=\{disabled \? tooltipId : undefined\}/);
  assert.match(skillCenterSource, /role="tooltip"/);
  assert.match(skillCenterSource, /管理员未配置 Dev Sandbox/);
  assert.doesNotMatch(skillCenterSource, /skillcenter-capability-note/);
  assert.doesNotMatch(skillCenterSource, /Dev Sandbox：管理员未配置/);
  assert.match(skillCenterSource, /<strong>自动创建<\/strong>/);
  assert.doesNotMatch(skillCenterSource, /<strong>Dev Sandbox 创建<\/strong>/);
  assert.match(skillCenterSource, /<span>选择模型和风格，通过对话生成技能<\/span>/);
  assert.match(skillStylesSource, /\.skillcenter-disabled-action\.is-disabled:hover \.skillcenter-disabled-tooltip/);
  assert.match(skillStylesSource, /\.skillcenter-disabled-action\.is-disabled:focus-visible \.skillcenter-disabled-tooltip/);
});

test("Skill file browser and refinement composer reuse clean Studio patterns", () => {
  assert.doesNotMatch(fileTreeSource, /skill-file-tree__mark/);
  assert.match(fileTreeSource, /<FolderIcon \/>/);
  assert.match(fileTreeSource, /<FileIcon \/>/);
  assert.match(skillStylesSource, /\.skill-file-tree__row\s*\{[^}]*white-space:\s*nowrap/);
  assert.match(skillStylesSource, /\.skill-generation__followup\s*\{[^}]*border-radius:\s*18px/);
  assert.match(skillStylesSource, /\.skill-generation__followup textarea\s*\{[^}]*min-height:\s*36px/);
  assert.match(skillStylesSource, /\.skill-generation__followup \.skill-button\s*\{[^}]*height:\s*36px/);
});

test("Skill table keeps version beside the name and uses clear actions", () => {
  assert.match(skillCenterSource, /<strong title=\{skill\.skillName\}>\{skill\.skillName\}<\/strong>/);
  assert.match(skillCenterSource, /<span className="skillcenter-table__version-badge">\{skill\.version\}<\/span>/);
  assert.doesNotMatch(skillCenterSource, /className="skillcenter-table__version"/);
  assert.match(skillStylesSource, /\.skillcenter-table__version-badge\s*\{[^}]*border-radius:\s*999px/);
  assert.match(skillStylesSource, /\.skillcenter-table__actions button,[\s\S]*?color:\s*hsl\(var\(--foreground\)\)/);
  assert.match(skillStylesSource, /\.skill-generation\s*\{[^}]*background:\s*hsl\(var\(--background\)\)/);
});

test("skill descriptions hide legacy YAML block scalar markers", () => {
  assert.match(skillCenterSource, /function skillDescriptionLabel/);
  assert.match(skillCenterSource, /\[">", ">-", "\\|", "\\|-"\]/);
  assert.match(skillCenterSource, /skillDescriptionLabel\(skill\.skillDescription\)/);
});
