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
const resourceStyles = readFileSync(
  new URL("../src/ui/ResourceCollection.css", import.meta.url),
  "utf8",
);
const resourceSource = readFileSync(
  new URL("../src/ui/ResourceCollection.tsx", import.meta.url),
  "utf8",
);
const iconSource = readFileSync(
  new URL("../src/ui/icons/LibraryIcons.tsx", import.meta.url),
  "utf8",
);
const actionMenuSource = readFileSync(
  new URL("../src/ui/StudioActionMenu.tsx", import.meta.url),
  "utf8",
);
const editDialogSource = readFileSync(
  new URL("../src/ui/ArtifactEditDialog.tsx", import.meta.url),
  "utf8",
);

test("collects real chat artifact deltas without mock records", () => {
  assert.match(modelSource, /event\.actions\?\.artifactDelta \?\? event\.actions\?\.artifact_delta/);
  assert.match(modelSource, /collectArtifactLibraryItems/);
  assert.match(modelSource, /sessionTitle\(session\.events\)/);
  assert.match(modelSource, /if \(\/\\\.preview\\\.webp\$\/i\.test\(record\.filename\)\) continue/);
  assert.doesNotMatch(pageSource, /MOCK_ARTIFACTS|MOCK_SESSIONS|downloadMockArtifact/);
});

test("extracts generated image and video URLs with tool provenance", () => {
  assert.match(modelSource, /toolName === "image_generate"/);
  assert.match(modelSource, /\["video_generate", "video_task_query"\]/);
  assert.match(modelSource, /const successList = payload\.success_list/);
  assert.match(modelSource, /const directUrl = payload\.video_url/);
  assert.match(modelSource, /taskId: output\.taskId/);
  assert.match(modelSource, /invocationId: event\.invocationId \?\? event\.invocation_id/);
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
  assert.match(pageSource, /<ResourceToolbar className="artifact-library-toolbar library-resource-toolbar">[\s\S]*?<ResourceFilterSelect[\s\S]*?id="artifact-type-filter"[\s\S]*?\{toolbarFilters\}[\s\S]*?<ResourceSearch/);
  assert.doesNotMatch(pageSource, /artifact-library-toolbar__main/);
  assert.doesNotMatch(pageSource, /artifact-library-heading/);
  for (const label of ["全部类型", "文档", "图片", "视频"]) {
    assert.match(pageSource, new RegExp(`label: "${label}"`));
  }
  assert.match(pageSource, /onChange=\{setActiveType\}/);
  assert.doesNotMatch(pageSource, /artifact-type-pills|artifact-type-pill/);
  assert.doesNotMatch(pageSource, /artifact-type-badge/);
  assert.match(pageSource, /<table className="artifact-library-table">/);
  for (const heading of ["名称", "来源", "修改时间", "操作"]) {
    assert.match(pageSource, new RegExp(`>${heading}<`));
  }
  assert.doesNotMatch(pageSource, /<th[^>]*>大小<\/th>/);
  assert.doesNotMatch(pageSource, /artifact-library-table__size-column/);
  assert.doesNotMatch(pageSource, /artifact-library-table__version-column/);
  assert.match(pageSource, /\{artifact\.agentName\} \/ \{artifact\.sessionTitle\}/);
  assert.match(pageSource, /className="library-artifact-preview-trigger"/);
  assert.match(pageSource, /onClick=\{\(\) => onPreview\(artifact\)\}/);
  assert.match(pageSource, /className="library-artifact-row-size"/);
  assert.match(pageSource, /label: downloadPending \? "下载中" : "下载"/);
  assert.match(pageSource, /label: "编辑信息"/);
  assert.match(pageSource, /label: "删除产物"/);
  assert.doesNotMatch(pageSource, /className="library-artifact-action"/);
  assert.match(pageSource, /<img src=\{previewUrl\}/);
  assert.match(pageSource, /<video src=\{previewUrl\} controls/);
  assert.match(pageSource, /<iframe src=\{previewUrl\}/);
});

test("supports managed artifacts and preserves their source provenance", () => {
  assert.match(pageSource, /onEdit\?:/);
  assert.match(pageSource, /onDelete\?:/);
  assert.match(pageSource, /onOpenSource\?:/);
  assert.match(pageSource, /<StudioConfirmDialog/);
  assert.match(pageSource, /<ArtifactEditDialog/);
  assert.match(pageSource, /<dt>Agent<\/dt>/);
  assert.match(pageSource, /<dt>会话<\/dt>/);
  assert.match(pageSource, /<dt>生成工具<\/dt>/);
  assert.match(modelSource, /agentId\?: string/);
  assert.match(modelSource, /runtimeId\?: string/);
  assert.match(modelSource, /eventId\?: string/);
  assert.match(modelSource, /invocationId\?: string/);
});

test("shared artifact controls are keyboard accessible", () => {
  assert.match(actionMenuSource, /from "@openai\/apps-sdk-ui\/components\/Menu"/);
  assert.match(actionMenuSource, /<Menu\.Trigger>/);
  assert.match(actionMenuSource, /<Menu\.Item/);
  assert.match(actionMenuSource, /aria-label=\{label\}/);
  assert.match(editDialogSource, /event\.key !== "Tab"/);
  assert.match(pageSource, /event\.key !== "Tab"/);
  assert.match(pageSource, /document\.body\.style\.overflow = "hidden"/);
});

test("covers loading, failure, retry, empty and unavailable-preview states", () => {
  assert.match(pageSource, /<ResourceLoadingState \/>/);
  assert.match(resourceSource, /资源加载中，请稍候/);
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
  assert.match(pageSource, /<ResourceResults[\s\S]*?className="artifact-library-results"/);
  assert.match(resourceStyles, /\.resource-results\s*\{[\s\S]*?overflow-y: auto/);
  assert.doesNotMatch(pageStyles, /\.artifact-library-toolbar\.library-resource-toolbar\s*\{[^}]*justify-content:/);
  assert.doesNotMatch(pageStyles, /artifact-view-tabs|artifact-session-/);
  assert.match(pageStyles, /@media \(max-width: 720px\)/);
  assert.match(pageStyles, /@media \(prefers-reduced-motion: reduce\)/);
  assert.doesNotMatch(pageStyles, /font-family/);
  assert.match(pageStyles, /\.library-artifact-thumbnail\s*\{[\s\S]*?width:\s*32px;[\s\S]*?height:\s*32px;[\s\S]*?flex:\s*0 0 32px;/);
});
