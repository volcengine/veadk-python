import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

const sources = {
  agents: read("../src/ui/MyAgents.tsx"),
  library: read("../src/ui/LibraryView.tsx"),
  skills: read("../src/ui/SkillCenter.tsx"),
  knowledge: read("../src/ui/KnowledgeLibrary.tsx"),
  workspaces: read("../src/ui/WorkspaceCenter.tsx"),
  environments: read("../src/ui/EnvironmentCenter.tsx"),
  cronjobs: read("../src/cronjobs/CronJobs.tsx"),
  artifacts: read("../src/ui/ArtifactLibrary.tsx"),
  sharedCard: read("../src/ui/LibraryResourceCard.tsx"),
};

const resourceStyles = read("../src/ui/ResourceCollection.css");
const resourceSource = read("../src/ui/ResourceCollection.tsx");

const domainStyles = [
  read("../src/ui/MyAgents.css"),
  read("../src/ui/LibraryView.css"),
  read("../src/ui/skills/skills.css"),
  read("../src/ui/KnowledgeLibrary.css"),
  read("../src/ui/EnvironmentCenter.css"),
  read("../src/cronjobs/CronJobs.css"),
].join("\n");

test("resource list pages compose the same shared layout and card primitives", () => {
  for (const component of ["ResourcePageShell", "ResourceToolbar", "ResourceTabs", "ResourceResults", "ResourceGrid", "ResourceCard"]) {
    assert.match(sources.agents, new RegExp(`<${component}`));
  }
  assert.match(sources.library, /<ResourcePageShell/);
  assert.match(sources.library, /<ResourceTabs/);
  for (const source of [sources.skills, sources.knowledge]) {
    for (const component of ["ResourceToolbar", "ResourceResults", "ResourceGrid", "LibraryResourceCard"]) {
      assert.match(source, new RegExp(`<${component}`));
    }
  }
  for (const component of ["ResourcePageShell", "ResourceToolbar", "ResourceResults", "ResourceGrid", "LibraryResourceCard"]) {
    assert.match(sources.environments, new RegExp(`<${component}`));
  }
  for (const component of ["ResourcePageShell", "ResourceToolbar", "ResourceTabs", "ResourceResults", "ResourceGrid", "LibraryResourceCard"]) {
    assert.match(sources.cronjobs, new RegExp(`<${component}`));
  }
  assert.match(sources.skills, /className=\{`skillcenter\$\{selectedSpace \? " is-space" : " resource-collection"\}`\}/);
  assert.match(sources.knowledge, /selected \? " is-detail" : " resource-collection"/);
  assert.match(sources.artifacts, /className="artifact-library-page resource-collection"/);
  assert.match(sources.artifacts, /<ResourceResults/);
  assert.match(sources.sharedCard, /<ResourceIdentityMark seed=\{title\} \/>/);
  assert.match(sources.sharedCard, /<ResourceCardRevealAction/);
  assert.doesNotMatch(sources.sharedCard, /<StudioActionMenu|<ResourceCardAction/);
  assert.match(sources.agents, /<ResourceFilterSelect/);
  assert.match(sources.library, /<ResourceFilterSelect/);
  assert.match(sources.artifacts, /<ResourceFilterSelect/);
});

test("resource list pages share the same centered initial loading state", () => {
  assert.match(resourceSource, /export function ResourceLoadingState/);
  assert.match(resourceSource, /<LoadingIndicator size=\{20\} \/>/);
  assert.match(resourceSource, /资源加载中，请稍候/);
  assert.match(
    resourceStyles,
    /\.resource-loading-state\s*\{[\s\S]*?height:\s*100%;[\s\S]*?align-items:\s*center;[\s\S]*?justify-content:\s*center;/,
  );

  for (const source of [
    sources.agents,
    sources.skills,
    sources.knowledge,
    sources.workspaces,
    sources.environments,
    sources.cronjobs,
    sources.artifacts,
  ]) {
    assert.match(source, /<ResourceLoadingState \/>/);
  }
});

test("resource detail pages reuse the shared detail layout", () => {
  const detailComponents = [
    "ResourceDetail",
    "ResourceDetailHeader",
    "ResourceDetailHeading",
    "ResourceDetailActions",
    "ResourceDetailBody",
    "ResourceDetailSummary",
    "ResourceDetailSectionHeader",
  ];

  for (const component of detailComponents) {
    assert.match(resourceSource, new RegExp(`export function ${component}`));
  }

  assert.match(resourceSource, /export function ResourceDetailLayout/);
  assert.match(resourceSource, /export interface ResourceDetailSection/);
  assert.match(resourceSource, /<ResourceDetailHeading/);
  assert.match(resourceSource, /<ResourceDetailActions/);
  assert.match(resourceSource, /<ResourceDetailBody/);
  assert.match(resourceSource, /className="resource-detail__navigation"/);
  assert.match(resourceSource, /className="resource-detail__content"/);
  assert.match(resourceSource, /sections\?\.find\(\(section\) => section\.key === activeSectionKey\)\?\.content/);
  assert.doesNotMatch(resourceSource, /selected=\{section\.key === activeSectionKey\}/);
  assert.match(sources.skills, /<ResourceDetailLayout/);
  assert.match(sources.knowledge, /<ResourceDetailLayout/);
  assert.doesNotMatch(sources.skills, /<ResourceDetail(?:Header|Heading|Actions|Body)\b/);
  assert.doesNotMatch(sources.knowledge, /<ResourceDetail(?:Header|Heading|Actions|Body)\b/);

  assert.match(resourceStyles, /\.resource-detail\s*\{/);
  assert.match(resourceStyles, /\.resource-detail__header\s*\{/);
  assert.match(resourceStyles, /\.resource-detail__body\s*\{/);
  assert.match(resourceStyles, /\.resource-detail__body\.is-split\s*\{/);
  assert.match(resourceStyles, /\.resource-detail__navigation\s*\{/);
  assert.match(resourceStyles, /\.resource-detail__navigation-label\s*\{[\s\S]*?text-align:\s*left;/);
  assert.match(resourceStyles, /\.resource-detail__content\s*\{/);
  assert.match(resourceStyles, /\.resource-detail__summary\s*\{/);
  assert.match(resourceStyles, /\.resource-detail__section-header\s*\{/);
});

test("shared resource data table owns search, primary action, and overflow actions", () => {
  assert.match(resourceSource, /export function ResourceDataTable/);
  assert.match(resourceSource, /<Input[\s\S]*?placeholder=\{searchPlaceholder\}/);
  assert.match(resourceSource, /<Button[\s\S]*?color="primary"/);
  assert.doesNotMatch(resourceSource, /<Input[^>]*(?:className|size|gutterSize|pill|variant|startAdornment|endAdornment)=/);
  assert.doesNotMatch(resourceSource, /<Button[^>]*color="primary"[^>]*(?:className|size|gutterSize|iconSize|pill|variant)=/);
  assert.match(resourceSource, /<table className="resource-data-table__table">/);
  assert.match(resourceSource, /<StudioActionMenu/);
  assert.doesNotMatch(resourceSource, /type="checkbox"/);
  assert.match(resourceStyles, /\.resource-data-table__toolbar\s*\{[\s\S]*?justify-content:\s*space-between;/);
  assert.doesNotMatch(resourceStyles, /\.resource-data-table__search\s*>/);
  assert.match(resourceStyles, /\.resource-data-table__frame\s*\{[\s\S]*?border:\s*1px solid hsl\(var\(--border\)\);/);
});

test("domain styles do not reimplement shared tabs, grids, cards, or hover actions", () => {
  assert.doesNotMatch(domainStyles, /(^|\n)\s*\.(?:resource-tabs|resource-grid|resource-card(?:__actions|__target)?|my-agent-actions|my-agent-card-target|library-resource-card__actions|cronjobs-table)(?:\s|\{|:)/);
  assert.doesNotMatch(
    domainStyles,
    /\.(?:skillcenter-results|knowledge-library__results|artifact-library-results)\s*\{[\s\S]*?(?:flex:|margin-top:|padding-bottom:|overflow-y:)/,
  );
  assert.match(
    resourceStyles,
    /\.resource-page \.resource-collection\s*\{[\s\S]*?display: flex;[\s\S]*?flex-direction: column;[\s\S]*?padding: 0;[\s\S]*?background: transparent;/,
  );
  assert.doesNotMatch(domainStyles, /\.resource-collection\s*\{[\s\S]*?background:/);
  assert.doesNotMatch(
    resourceStyles,
    /\.resource-card:(?:hover|focus-within) \.resource-card__metadata\s*\{[\s\S]*?opacity:\s*0/,
  );
  assert.match(
    resourceStyles,
    /\.resource-card__actions\s*\{[\s\S]*?position:\s*relative;[\s\S]*?opacity:\s*0;/,
  );
  assert.match(
    resourceStyles,
    /\.resource-results\s*\{[\s\S]*?margin:\s*4px -8px 0;[\s\S]*?padding:\s*8px 8px 56px;/,
  );
});

test("shared filters use the borderless Apps SDK select treatment", () => {
  assert.match(
    resourceSource,
    /<Select[\s\S]*?size="md"[\s\S]*?variant="ghost"[\s\S]*?pill=\{false\}[\s\S]*?block=\{false\}[\s\S]*?listMinWidth=\{160\}/,
  );
  assert.match(
    resourceStyles,
    /\.resource-filter-select__trigger\s*\{[\s\S]*?--select-control-font-size: 14px;[\s\S]*?--select-control-font-weight: 400;[\s\S]*?--select-control-gap: 8px;/,
  );
  assert.match(resourceSource, /RESOURCE_FILTER_HOVER_OPEN_DELAY = 150/);
  assert.match(resourceSource, /RESOURCE_FILTER_HOVER_CLOSE_DELAY = 200/);
  assert.match(resourceSource, /window\.matchMedia\("\(hover: hover\) and \(pointer: fine\)"\)/);
  assert.match(resourceSource, /onMouseEnter=\{handleMouseEnter\}/);
  assert.match(resourceSource, /new PointerEvent\("pointerdown"/);
  assert.match(resourceSource, /menu\?\.contains\(target\)/);
});

test("nested resource collections do not clip the shared card hover ring", () => {
  const collectionRule = resourceStyles.match(/\.resource-collection\s*\{([\s\S]*?)\}/)?.[1] ?? "";
  assert.doesNotMatch(collectionRule, /overflow:\s*hidden/);
  assert.match(
    resourceStyles,
    /\.resource-card:hover,[\s\S]*?\.resource-card:focus-within\s*\{[\s\S]*?box-shadow:\s*0 0 0 4px/,
  );
});

test("stacked resource toolbars align their action row to the content edge", () => {
  assert.match(
    resourceStyles,
    /@media \(min-width: 721px\) and \(max-width: 1180px\) \{[\s\S]*?\.resource-toolbar__actions\s*\{[\s\S]*?width: 100%;[\s\S]*?justify-content: flex-start;[\s\S]*?margin-left: 0;/,
  );
});

test("shared reveal actions expose domain-specific icons without forking card markup", () => {
  assert.match(resourceSource, /icon\?: "arrow" \| "play" \| "plus"/);
  assert.match(resourceSource, /icon === "play"[\s\S]*?<PlaySm/);
  assert.match(resourceSource, /icon === "plus"[\s\S]*?<PlusLg18pxAdd/);
  assert.match(sources.sharedCard, /icon=\{action\.icon\}/);
  assert.match(sources.environments, /icon: "play"/);
  assert.match(sources.environments, /title: "构建"/);
  assert.match(sources.skills, /label: "添加技能", icon: "plus"/);
  assert.match(sources.knowledge, /label: invalidProviderKey[\s\S]*?icon: "plus"/);
});
