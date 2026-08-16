import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const pageSource = readFileSync(
  new URL("../src/ui/ArtifactLibrary.tsx", import.meta.url),
  "utf8",
);
const modelSource = readFileSync(
  new URL("../src/ui/artifactLibraryModel.ts", import.meta.url),
  "utf8",
);
const pageStyles = readFileSync(
  new URL("../src/ui/ArtifactLibrary.css", import.meta.url),
  "utf8",
);
const iconSource = readFileSync(
  new URL("../src/ui/icons/LibraryIcons.tsx", import.meta.url),
  "utf8",
);

test("collects real chat artifact deltas without mock records", () => {
  assert.match(modelSource, /event\.actions\?\.artifactDelta \?\? event\.actions\?\.artifact_delta/);
  assert.match(modelSource, /collectArtifactLibraryItems/);
  assert.match(modelSource, /sessionTitle\(session\.events\)/);
  assert.match(modelSource, /if \(\/\\\.preview\\\.webp\$\/i\.test\(record\.filename\)\) continue/);
  assert.doesNotMatch(pageSource, /MOCK_ARTIFACTS|MOCK_SESSIONS|downloadMockArtifact/);
});

test("uses the existing ADK preview and download endpoints", () => {
  assert.match(pageSource, /downloadArtifact as downloadAdkArtifact/);
  assert.match(pageSource, /previewArtifact as previewAdkArtifact/);
  assert.match(pageSource, /artifact\.appName,[\s\S]*?userId,[\s\S]*?artifact\.sessionId/);
  assert.match(pageSource, /artifact\.preview\.filename,[\s\S]*?artifact\.preview\.version/);
  assert.match(pageSource, /URL\.revokeObjectURL/);
});

test("keeps one type-filtered view with search, preview and download", () => {
  assert.doesNotMatch(pageSource, /LibraryView|ViewTabs|按会话|按类型/);
  assert.doesNotMatch(pageSource, /role="tablist"|role="tabpanel"/);
  assert.match(pageSource, /placeholder="搜索产物或会话"/);
  assert.match(pageSource, /artifact-library-toolbar library-resource-toolbar/);
  assert.match(pageSource, /artifact-library-toolbar library-resource-toolbar"[\s\S]*?<nav className="artifact-type-pills"[\s\S]*?<label className="artifact-library-search"/);
  assert.doesNotMatch(pageSource, /artifact-library-toolbar__main/);
  assert.doesNotMatch(pageSource, /artifact-library-heading/);
  assert.doesNotMatch(pageSource, /label: "全部"/);
  for (const label of ["文档", "图片", "视频"]) {
    assert.match(pageSource, new RegExp(`label: "${label}"`));
  }
  assert.match(pageSource, /setActiveType\(\(current\) => current === type\.id \? null : type\.id\)/);
  assert.match(pageSource, /<span className="artifact-type-badge">\{ARTIFACT_LABELS\[artifact\.type\]\}<\/span>/);
  assert.match(pageSource, /来自会话：\{artifact\.sessionTitle\}/);
  assert.match(pageSource, /aria-label=\{`预览 \$\{artifact\.name\}`\}/);
  assert.match(pageSource, /aria-label=\{`下载 \$\{artifact\.name\}`\}/);
  assert.match(pageSource, /<img src=\{previewUrl\}/);
  assert.match(pageSource, /<video src=\{previewUrl\} controls/);
  assert.match(pageSource, /<iframe src=\{previewUrl\}/);
});

test("covers loading, failure, retry, empty and unavailable-preview states", () => {
  assert.match(pageSource, /正在加载产物/);
  assert.match(pageSource, /产物加载失败/);
  assert.match(pageSource, /重新加载/);
  assert.match(pageSource, /您还没有任何产物/);
  assert.match(pageSource, /当前格式暂不支持在线预览，请下载查看/);
  assert.match(pageSource, /role="alert"/);
});

test("batches large artifact collections and loads more inside the results scroller", () => {
  assert.match(pageSource, /const ARTIFACT_BATCH_SIZE = 40/);
  assert.match(pageSource, /visibleArtifacts\.slice\(0, visibleCount\)/);
  assert.match(pageSource, /new IntersectionObserver\(/);
  assert.match(pageSource, /rootMargin: "240px 0px"/);
  assert.match(pageSource, /onScroll=\{handleResultsScroll\}/);
  assert.match(pageSource, /activationRevision/);
  assert.match(pageSource, /正在加载更多产物/);
});

test("uses repository icons and responsive reduced-motion styles", () => {
  assert.doesNotMatch(iconSource, /SessionViewIcon|TypeViewIcon/);
  assert.match(iconSource, /export function PreviewArtifactIcon/);
  assert.doesNotMatch(iconSource, /lucide-react/);
  assert.match(pageStyles, /\.artifact-library-results\s*\{[\s\S]*?overflow-y: auto/);
  assert.match(pageStyles, /\.artifact-library-toolbar\.library-resource-toolbar\s*\{[^}]*align-items:\s*center;[^}]*justify-content:\s*space-between;/);
  assert.doesNotMatch(pageStyles, /artifact-view-tabs|artifact-session-/);
  assert.match(pageStyles, /@media \(max-width: 720px\)/);
  assert.match(pageStyles, /@media \(prefers-reduced-motion: reduce\)/);
  assert.doesNotMatch(pageStyles, /font-family/);
});
