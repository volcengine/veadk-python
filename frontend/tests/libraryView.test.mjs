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
  assert.match(sidebarSource, /aria-label="库"/);
  assert.match(sidebarSource, />库<\/span>/);
  assert.match(
    appSource,
    /const sidebarActivePage: SidebarPage =[\s\S]*?: skillCenter\s*\? "library"/,
  );
  assert.match(appSource, /<LibraryView[\s\S]*?cloudProvider=\{cloudProvider\}/);
});

test("renders the three Library sections with Agent detail style tabs", () => {
  assert.match(librarySource, /<h1>库<\/h1>/);
  assert.match(librarySource, /<p>管理您的资源和产物<\/p>/);
  assert.match(librarySource, /id: "skills", label: "技能库"/);
  assert.match(librarySource, /id: "knowledge", label: "知识库"/);
  assert.match(librarySource, /id: "artifacts", label: "产物"/);
  assert.match(librarySource, /className="aw-agent-tabs library-tabs"/);
  assert.match(librarySource, /role="tablist"/);
  assert.match(librarySource, /aria-selected=\{activeTab === tab\.id\}/);
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
  assert.match(libraryStyles, /\.library-tabs button\s*\{[\s\S]*?font-size:\s*15px/);
  assert.match(libraryStyles, /\.library-resource-toolbar\s*\{[\s\S]*?justify-content:\s*space-between/);
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
  assert.match(librarySource, /\["ArrowLeft", "ArrowRight", "Home", "End"\]/);
  assert.match(librarySource, /tabIndex=\{activeTab === tab\.id \? 0 : -1\}/);
  assert.match(librarySource, /document\.getElementById\(`library-\$\{nextTab\.id\}-tab`\)\?\.focus\(\)/);
  assert.match(librarySource, /role="tabpanel"/);
  assert.match(librarySource, /aria-labelledby="library-skills-tab"/);
  assert.match(librarySource, /aria-labelledby="library-knowledge-tab"/);
  assert.match(librarySource, /aria-labelledby="library-artifacts-tab"/);
});
