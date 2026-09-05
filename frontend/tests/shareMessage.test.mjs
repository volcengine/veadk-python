// Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const dialogSource = readFileSync(
  new URL("../src/ui/ShareMessageDialog.tsx", import.meta.url),
  "utf8",
);
const dialogStyles = readFileSync(
  new URL("../src/ui/ShareMessageDialog.css", import.meta.url),
  "utf8",
);
const conversationEnglish = JSON.parse(readFileSync(
  new URL("../src/i18n/resources/en-US/conversation.json", import.meta.url),
  "utf8",
));
const conversationChinese = JSON.parse(readFileSync(
  new URL("../src/i18n/resources/zh-CN/conversation.json", import.meta.url),
  "utf8",
));

test("assistant messages expose the Apps SDK share action after copy", () => {
  assert.match(
    appSource,
    /import\s*\{[^}]*\bShare\b[^}]*\}\s*from\s*["']@openai\/apps-sdk-ui\/components\/Icon["']/,
  );
  assert.match(appSource, /<CopyButton\b[^>]*\/>\s*<ShareMessageButton\b/);
  assert.match(appSource, /<Share\b/);
});

test("the share action passes the selected assistant turn to the dialog", () => {
  assert.match(
    appSource,
    /interface\s+ShareMessageTarget\s*\{[\s\S]*?targetTurn:\s*HTMLElement[\s\S]*?\}/,
  );
  assert.match(
    appSource,
    /<ShareMessageButton[\s\S]*?closest<HTMLElement>\([\s\S]*?\[data-share-message-source\][\s\S]*?setShareMessageTarget\(\{\s*targetTurn\s*\}\)/,
  );
  assert.match(
    appSource,
    /<ShareMessageDialog\s+targetTurn=\{shareMessageTarget\.targetTurn\}/,
  );
});

test("the dialog exports every user and assistant turn through the selected reply", () => {
  assert.match(dialogSource, /function\s+conversationTurnsThrough\s*\(/);
  assert.match(
    dialogSource,
    /targetTurn\.closest\(\s*["']\.transcript["']\s*\)/,
  );
  assert.match(dialogSource, /transcript\.children/);
  assert.match(
    dialogSource,
    /\.matches\(\s*["']\.turn--user,\s*\.turn--assistant["']\s*\)/,
  );
  assert.match(dialogSource, /\.indexOf\(\s*targetTurn\s*\)/);
  assert.match(dialogSource, /\.slice\(\s*0\s*,\s*targetIndex\s*\+\s*1\s*\)/);
});

test("conversation export excludes controls and removes its temporary container", () => {
  assert.match(dialogSource, /function\s+createConversationExport\s*\(/);
  assert.match(dialogSource, /\.cloneNode\(\s*true\s*\)/);
  assert.match(
    dialogSource,
    /querySelectorAll(?:<[^>]+>)?\(\s*["']\[data-share-image-exclude\]["']\s*\)/,
  );
  assert.match(dialogSource, /document\.body\.append\(\s*exportRoot\s*\)/);
  assert.match(
    dialogSource,
    /try\s*\{[\s\S]*?toBlob\(\s*exportChunk\s*,[\s\S]*?\}\s*finally\s*\{[\s\S]*?exportChunk\.remove\(\s*\)[\s\S]*?exportRoot\.remove\(\s*\)/,
  );
});

test("conversation export expands retained activity and tool details", () => {
  assert.match(dialogSource, /function\s+expandConversationExportContent\s*\(/);
  assert.match(
    dialogSource,
    /\.block-tool,\s*\.block-thinking,\s*\.block-progress,\s*\.block-plan[\s\S]*?opacity\s*=\s*["']1["'][\s\S]*?transform\s*=\s*["']none["']/,
  );
  assert.match(
    dialogSource,
    /querySelectorAll(?:<[^>]+>)?\(\s*["']\.think-collapse["']\s*\)[\s\S]*?classList\.add\(\s*["']open["']\s*\)[\s\S]*?gridTemplateRows\s*=\s*["']1fr["']/,
  );
  assert.match(
    dialogSource,
    /\.codex-sandbox-run__stream,\s*\.think-body,\s*\.tool-result/,
  );
  assert.match(
    dialogSource,
    /maxHeight\s*=\s*["']none["'][\s\S]*?overflow\s*=\s*["']visible["'][\s\S]*?scrollTop\s*=\s*0/,
  );
  assert.match(
    dialogSource,
    /querySelectorAll(?:<[^>]+>)?\(\s*["']\.tool-args["']\s*\)[\s\S]*?overflowWrap\s*=\s*["']anywhere["'][\s\S]*?whiteSpace\s*=\s*["']pre-wrap["']/,
  );
  assert.match(
    dialogSource,
    /querySelectorAll(?:<[^>]+>)?\(\s*["']\.think-collapse-inner["']\s*\)[\s\S]*?overflow\s*=\s*["']visible["']/,
  );
  assert.match(dialogSource, /expandConversationExportContent\(\s*clone\s*\)/);
});

test("conversation export removes only the raw payload duplicated beneath Codex activity cards", () => {
  assert.match(
    dialogSource,
    /function\s+removeDuplicateCodexExportPayloads\s*\(/,
  );
  assert.match(
    dialogSource,
    /querySelectorAll(?:<[^>]+>)?\(\s*["']\.codex-sandbox-run["']\s*\)/,
  );
  assert.match(
    dialogSource,
    /parentElement[\s\S]*?\?\.querySelector\(\s*["']:scope\s*>\s*\.tool-detail["']\s*\)[\s\S]*?\?\.remove\(\)/,
  );
  assert.match(
    dialogSource,
    /removeDuplicateCodexExportPayloads\(\s*clone\s*\)/,
  );
});

test("conversation export ends with the AgentKit Studio disclaimer", () => {
  assert.match(
    dialogSource,
    /className\s*=\s*["']share-message-export-note["'][\s\S]*?share\.exportNote/,
  );
  assert.match(
    dialogStyles,
    /\.share-message-export-note\s*\{[\s\S]*?color:\s*hsl\(var\(--muted-foreground\)\)/,
  );
  assert.match(
    dialogStyles,
    /\.share-message-export\s*>\s*\.turn:last-of-type\s*\{[\s\S]*?margin-bottom:\s*0/,
  );
});

test("conversation capture resets the offscreen export position", () => {
  assert.match(
    dialogSource,
    /style:\s*\{[\s\S]*?position:\s*"static"[\s\S]*?top:\s*"auto"[\s\S]*?left:\s*"auto"/,
  );
});

test("the share action has an accessible localized name", () => {
  const combinedSource = `${appSource}\n${dialogSource}`;
  assert.match(combinedSource, /aria-label=\{appText\("actions\.exportConversation"\)\}/);
  assert.match(combinedSource, /aria-label=\{t\("share\.close"\)\}/);
  assert.equal(conversationChinese.share.title, "导出会话");
  assert.equal(conversationEnglish.share.title, "Export conversation");
});

test("the share dialog covers image generation, preview, and failures", () => {
  assert.match(dialogSource, /(?:generating|isGenerating|生成中|正在生成)/i);
  assert.match(dialogSource, /aria-busy=/);
  assert.match(dialogSource, /<img\b[^>]*\bsrc=/);
  assert.match(
    dialogSource,
    /alt=\{t\("share\.previewAlt", \{ count: imagePages\.length \}\)\}/,
  );
  assert.match(dialogSource, /role=["']alert["']/);
});

test("the dialog paints its loading state before starting an expensive export", () => {
  assert.match(dialogSource, /function\s+waitForDialogPaint\s*\(/);
  assert.match(dialogSource, /await\s+waitForDialogPaint\s*\(/);
  assert.match(dialogSource, /t\("share\.generatingContent"\)/);
});

test("the generated PNG can be copied or downloaded", () => {
  assert.match(dialogSource, /new\s+ClipboardItem\s*\(/);
  assert.match(dialogSource, /navigator\.clipboard\.write\s*\(/);
  assert.match(dialogSource, /["']image\/png["']/);
  assert.match(dialogSource, /\.download\s*=/);
  assert.match(dialogSource, /\.click\s*\(\s*\)/);
  assert.match(dialogSource, /\.png["'`]/i);
});

test("the export format can switch between PNG and PDF", () => {
  assert.match(
    dialogSource,
    /type\s+ExportFormat\s*=\s*["']png["']\s*\|\s*["']pdf["']/,
  );
  assert.match(dialogSource, /role=["']radiogroup["']/);
  assert.match(dialogSource, /role=["']radio["']/);
  assert.match(
    dialogSource,
    /\(\[\s*["']png["']\s*,\s*["']pdf["']\s*\]\s+as\s+const\)/,
  );
  assert.match(dialogSource, /aria-checked=\{exportFormat\s*===\s*format\}/);
  assert.match(dialogSource, /t\("share\.downloadFormat", \{ format: exportFormat\.toUpperCase\(\) \}\)/);
});

test("conversation export renders fixed-height readable image pages", () => {
  assert.match(dialogSource, /const\s+EXPORT_PAGE_HEIGHT\s*=\s*[\d_]+/);
  assert.match(
    dialogSource,
    /const\s+EXPORT_MAX_LAST_PAGE_HEIGHT\s*=\s*EXPORT_PAGE_HEIGHT\s*\*\s*1\.12/,
  );
  assert.match(dialogSource, /const\s+EXPORT_CHUNK_HEIGHT\s*=\s*[\d_]+/);
  assert.match(
    dialogSource,
    /function\s+createConversationExportPageRanges\s*\(/,
  );
  assert.match(dialogSource, /function\s+createConversationExportChunks\s*\(/);
  assert.match(dialogSource, /function\s+measureConversationExport\s*\(/);
  assert.match(dialogSource, /function\s+pruneConversationExportClone\s*\(/);
  assert.match(dialogSource, /function\s+createConversationExportPage\s*\(/);
  assert.match(dialogSource, /async\s+function\s+splitExportChunk\s*\(/);
  assert.match(dialogSource, /async\s+function\s+generateShareImages\s*\(/);
  assert.match(dialogSource, /Promise<ShareImagePage\[\]>/);
  assert.match(
    dialogSource,
    /for\s*\(const\s+\[chunkIndex,\s*chunk\]\s+of\s+exportChunks\.entries\(\)\)/,
  );
  assert.match(dialogSource, /toBlob\(\s*exportChunk\s*,/);
  assert.match(dialogSource, /pixelRatio:\s*1/);
  assert.match(dialogSource, /cloneChild\.replaceChildren\(\)/);
  assert.match(
    dialogSource,
    /if\s*\(source\.matches\(EXPORT_BREAK_SELECTOR\)\)\s*return/,
  );
  assert.match(dialogSource, /pruneConversationExportClone\(/);
  assert.match(
    dialogSource,
    /pages\.push\([\s\S]*?\.\.\.\(await\s+splitExportChunk\(/,
  );
});

test("conversation pagination keeps readable blocks together and avoids a tiny final page", () => {
  assert.match(dialogSource, /interface\s+ExportBreakMetrics\s*\{/);
  assert.match(
    dialogSource,
    /remainingHeight\s*<=\s*EXPORT_MAX_LAST_PAGE_HEIGHT/,
  );
  assert.match(dialogSource, /block\.top\s*>=\s*minimumBottom/);
  assert.match(dialogSource, /block\.bottom\s*>\s*idealBottom/);
  assert.match(dialogSource, /block\.height\s*<=\s*EXPORT_PAGE_HEIGHT/);
  assert.match(dialogSource, /containingBlockTop\s*\?\?/);
});

test("PNG download packages every page with numbered filenames", () => {
  assert.match(dialogSource, /function\s+sharePageFileName\s*\(/);
  assert.match(
    dialogSource,
    /page-\$\{String\(pageNumber\)\.padStart\(digits,\s*["']0["']\)\}/,
  );
  assert.match(dialogSource, /async\s+function\s+createPngArchive\s*\(/);
  assert.match(
    dialogSource,
    /for\s*\(const\s+\[pageIndex,\s*page\]\s+of\s+imagePages\.entries\(\)\)/,
  );
  assert.match(
    dialogSource,
    /sharePageFileName\(\s*pageIndex\s*\+\s*1,\s*imagePages\.length/,
  );
  assert.match(dialogSource, /type:\s*["']application\/zip["']/);
  assert.match(
    dialogSource,
    /await\s+createPngArchive\(\s*imagePages,\s*timestamp\s*\)/,
  );
  assert.match(dialogSource, /-png-pages\.zip/);
});

test("PDF export uses the readable image pages directly", () => {
  assert.match(dialogSource, /import\(\s*["']jspdf["']\s*\)/);
  assert.match(dialogSource, /new\s+jsPDF\s*\(/);
  assert.match(dialogSource, /\.addImage\s*\(/);
  assert.match(dialogSource, /\.addPage\s*\(/);
  assert.match(dialogSource, /generateSharePdf\(imagePages\)/);
  assert.match(
    dialogSource,
    /for\s*\(const\s+\[pageIndex,\s*page\]\s+of\s+imagePages\.entries\(\)\)/,
  );
  assert.match(
    dialogSource,
    /async\s+function\s+generateSharePdf[\s\S]*?new\s+Uint8Array\(await\s+page\.blob\.arrayBuffer\(\)\)[\s\S]*?pdf\.addImage\(\s*imageBytes/,
  );
  assert.doesNotMatch(dialogSource, /function\s+findPageBreak\s*\(/);
  assert.doesNotMatch(dialogSource, /rowIsBlank/);
  assert.match(dialogSource, /application\/pdf/);
  assert.match(dialogSource, /\.pdf["'`]/i);
});

test("preview and copy labels explain the first page of a multi-page export", () => {
  assert.match(
    dialogSource,
    /t\("share\.previewPage", \{ count: imagePages\.length \}\)/,
  );
  assert.match(
    dialogSource,
    /imagePages\.length\s*>\s*1\s*\?\s*t\("share\.copiedFirst"\)/,
  );
  assert.match(
    dialogSource,
    /alt=\{t\("share\.previewAlt", \{ count: imagePages\.length \}\)\}/,
  );
  assert.match(dialogStyles, /\.share-message-preview-meta\s*\{/);
});

test("the selected export format controls the available actions", () => {
  assert.match(
    dialogSource,
    /exportFormat\s*===\s*["']png["'][\s\S]*?copyImage/,
  );
  assert.match(dialogSource, /downloadExport/);
  assert.match(dialogSource, /downloadState\s*===\s*["']downloading["']/);
  assert.match(dialogSource, /aria-live=["']polite["']/);
  assert.doesNotMatch(dialogSource, />\s*取消\s*</);
});

test("the dialog closes with Escape and releases object URLs", () => {
  assert.match(dialogSource, /["']keydown["']/);
  assert.match(dialogSource, /event\.key\s*===\s*["']Escape["']/);
  assert.match(dialogSource, /aria-label=\{t\("share\.close"\)\}/);
  assert.match(dialogSource, /URL\.createObjectURL\s*\(/);
  assert.match(dialogSource, /URL\.revokeObjectURL\s*\(/);
  assert.match(dialogSource, /removeEventListener\s*\(\s*["']keydown["']/);
});

test("long conversation capture stays bounded and keeps actions visible", () => {
  assert.match(dialogSource, /const\s+EXPORT_CHUNK_HEIGHT\s*=\s*12_000/);
  assert.match(
    dialogSource,
    /pageBottom\s*-\s*current\.top\s*<=\s*EXPORT_CHUNK_HEIGHT/,
  );
  assert.match(dialogSource, /pixelRatio:\s*1/);
  assert.match(
    dialogStyles,
    /\.share-message-body\s*\{[\s\S]*?overflow-y:\s*auto\s*;/,
  );
  assert.match(
    dialogStyles,
    /\.share-message-actions\s*\{[\s\S]*?flex:\s*0\s+0\s+auto\s*;/,
  );
  assert.match(
    dialogSource,
    /<div\s+className=["']share-message-body["'][\s\S]*?<\/div>\s*<footer\s+className=["']share-message-actions["']/,
  );
});

test("share controls retain visible focus and respect reduced motion", () => {
  assert.match(dialogStyles, /:focus-visible/);
  assert.match(
    dialogStyles,
    /@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)/,
  );
});
