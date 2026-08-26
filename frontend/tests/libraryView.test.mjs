import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const librarySource = readFileSync(
  new URL("../src/ui/LibraryView.tsx", import.meta.url),
  "utf8",
);
const libraryStyles = readFileSync(
  new URL("../src/ui/LibraryView.css", import.meta.url),
  "utf8",
);
const resourceSource = readFileSync(
  new URL("../src/ui/ResourceCollection.tsx", import.meta.url),
  "utf8",
);
const resourceStyles = readFileSync(
  new URL("../src/ui/ResourceCollection.css", import.meta.url),
  "utf8",
);
const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);

test("moves the Skill entry into the Library shell", () => {
  assert.match(sidebarSource, /\| "library"/);
  assert.doesNotMatch(sidebarSource, /\| "skills"/);
  assert.match(
    sidebarSource,
    /new-chat--library\$\{[\s\S]*?activePage === "library" \? " is-active" : ""/,
  );
  assert.match(sidebarSource, /onClick=\{onLibrary\}/);
  assert.match(sidebarSource, /aria-label="资源库"/);
  assert.match(sidebarSource, />资源库<\/span>/);
  assert.match(
    appSource,
    /const sidebarActivePage: SidebarPage =[\s\S]*?: skillCenter\s*\? "library"/,
  );
  assert.match(appSource, /<LibraryView[\s\S]*?cloudProvider=\{cloudProvider\}/);
});

test("renders the three Library sections with the shared resource tabs", () => {
  assert.match(librarySource, /<ResourcePageHeader[\s\S]*?title="资源库"/);
  assert.match(librarySource, /id: "skills", label: "技能库"/);
  assert.match(librarySource, /id: "knowledge", label: "知识库"/);
  assert.match(librarySource, /id: "artifacts", label: "产物"/);
  assert.match(librarySource, /<ResourceTabs[\s\S]*?idPrefix="library"[\s\S]*?items=\{LIBRARY_TABS\}/);
  assert.match(librarySource, /<ResourceFilterSelect[\s\S]*?ariaLabel="区域"[\s\S]*?value=\{region\}[\s\S]*?onChange=\{setRegion\}/);
  assert.match(appSource, /<LibraryView[\s\S]*?studioRegion=\{studioRegion \|\| defaultCloudRegion\(cloudProvider\)\}/);
  assert.match(resourceSource, /className=\{joinClassNames\("resource-tabs"/);
  assert.match(resourceSource, /role="tablist"/);
  assert.match(resourceSource, /aria-selected=\{value === item\.id\}/);
  assert.match(librarySource, /<SkillCenterView/);
  assert.match(
    librarySource,
    /<KnowledgeLibrary[\s\S]*?cloudProvider=\{cloudProvider\}[\s\S]*?active=\{activeTab === "knowledge"\}[\s\S]*?activationRevision=\{activationRevisions\.knowledge\}/,
  );
  assert.match(
    librarySource,
    /<ArtifactLibrary[\s\S]*?items=\{artifactItems\}[\s\S]*?userId=\{artifactUserId\}[\s\S]*?active=\{activeTab === "artifacts"\}[\s\S]*?activationRevision=\{activationRevisions\.artifacts\}/,
  );
  assert.match(
    appSource,
    /artifactSources=\{appName[\s\S]*?appName,[\s\S]*?agentName: labelOf\(appName\),[\s\S]*?sessions/,
  );
  assert.match(appSource, /onArtifactActivate=\{\(\) => \{[\s\S]*?refreshSessions\(appName\)/);
  assert.match(resourceStyles, /\.resource-tabs button\s*\{[\s\S]*?font-size:\s*14px/);
  assert.match(resourceStyles, /\.resource-toolbar\s*\{[\s\S]*?min-height:\s*32px/);
  assert.doesNotMatch(libraryStyles, /\.library-tabs|\.library-resource-toolbar/);
});

test("hides the outer Library heading while a nested resource detail is active", () => {
  assert.match(
    librarySource,
    /const detailActive = activeTab === "skills"[\s\S]*?skillPageTitle !== "技能库"[\s\S]*?: activeTab === "knowledge" && knowledgeDetailActive/,
  );
  assert.match(
    librarySource,
    /<ResourcePageShell className=\{`library-view\$\{detailActive \? " is-detail" : ""\}`\}[\s\S]*?\{!detailActive \? \([\s\S]*?<ResourcePageHeader[\s\S]*?title="资源库"[\s\S]*?\) : null\}/,
  );
  assert.match(librarySource, /<SkillCenterView[\s\S]*?onPageTitleChange=\{setSkillPageTitle\}/);
  assert.match(librarySource, /<KnowledgeLibrary[\s\S]*?onDetailChange=\{setKnowledgeDetailActive\}/);
});

test("refreshes the active Library resource on initial open and every tab activation", () => {
  assert.match(librarySource, /Record<LibraryTab, number>/);
  assert.match(librarySource, /\[tab\]: current\[tab\] \+ 1/);
  assert.match(librarySource, /active=\{activeTab === "skills"\}/);
  assert.match(librarySource, /activationRevision=\{activationRevisions\.skills\}/);
  assert.match(librarySource, /if \(activeTab === "artifacts"\)/);
  assert.match(librarySource, /artifactActivateRef\.current\?\.\(\)/);
  assert.match(appSource, /sessionRefreshRequestRef\.current !== request/);
});

test("keeps artifact candidates stable across unrelated App renders", () => {
  assert.match(librarySource, /const artifactCandidateSnapshot = useMemo\(/);
  assert.match(librarySource, /JSON\.stringify\(candidates\)/);
  assert.match(librarySource, /const artifactCandidateCache = useRef\(artifactCandidateSnapshot\)/);
  assert.match(
    librarySource,
    /artifactCandidateCache\.current\.key !== artifactCandidateSnapshot\.key/,
  );
  assert.match(librarySource, /const artifactCandidates = artifactCandidateCache\.current\.candidates/);
  assert.doesNotMatch(appSource, /const artifactSources = useMemo\(/);
});

test("keeps Library tab selection keyboard accessible", () => {
  assert.match(resourceSource, /\["ArrowLeft", "ArrowRight", "Home", "End"\]/);
  assert.match(resourceSource, /tabIndex=\{value === item\.id \? 0 : -1\}/);
  assert.match(resourceSource, /document\.getElementById\(`\$\{idPrefix\}-\$\{next\.id\}-tab`\)\?\.focus\(\)/);
  assert.match(librarySource, /role="tabpanel"/);
  assert.match(librarySource, /aria-labelledby="library-skills-tab"/);
  assert.match(librarySource, /aria-labelledby="library-knowledge-tab"/);
  assert.match(librarySource, /aria-labelledby="library-artifacts-tab"/);
});
