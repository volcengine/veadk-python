// Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const helperSource = readFileSync(
  new URL("../src/ui/responseAnnotation.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(helperSource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
});
const helperUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const {
  canSubmitResponseAnnotation,
  formatResponseAnnotationComment,
  prepareResponseAnnotationSelection,
  RESPONSE_ANNOTATION_COMMENT_MAX_LENGTH,
} = await import(helperUrl);

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const componentSource = readFileSync(
  new URL("../src/ui/ResponseAnnotationPopover.tsx", import.meta.url),
  "utf8",
);
const componentStyles = readFileSync(
  new URL("../src/ui/ResponseAnnotationPopover.css", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);

test("formats selected answer text and the annotation as one feedback comment", () => {
  assert.equal(
    formatResponseAnnotationComment("  第一段\n  第二段  ", "  这里的结论缺少依据。  "),
    "选中片段：第一段\n  第二段\n\n批注：这里的结论缺少依据。",
  );
});

test("keeps the persisted feedback comment within the server limit", () => {
  const selectedText = "片".repeat(2_000);
  const annotation = "注".repeat(2_000);
  const comment = formatResponseAnnotationComment(selectedText, annotation);

  assert.ok(comment.length <= RESPONSE_ANNOTATION_COMMENT_MAX_LENGTH);
  assert.ok(prepareResponseAnnotationSelection(selectedText).endsWith("…"));
});

test("requires a non-empty annotation", () => {
  assert.equal(canSubmitResponseAnnotation("   \n"), false);
  assert.equal(canSubmitResponseAnnotation("需要修正"), true);
});

test("assistant selections open an accessible Apps SDK annotation popover", () => {
  assert.match(appSource, /document\.addEventListener\("mouseup", queueSelection/);
  assert.match(appSource, /document\.addEventListener\("keyup", queueSelection/);
  assert.match(appSource, /document\.removeEventListener\("mouseup", queueSelection/);
  assert.match(appSource, /document\.removeEventListener\("keyup", queueSelection/);
  assert.match(appSource, /tabIndex=\{canAnnotate \? 0 : undefined\}/);
  assert.match(appSource, /window\.requestAnimationFrame/);
  assert.match(appSource, /onStreamComplete=/);
  assert.match(componentSource, /@openai\/apps-sdk-ui\/components\/Popover/);
  assert.doesNotMatch(appSource, /onMouseUp=\{\(\) => queueResponseAnnotation/);
  assert.match(componentSource, /@openai\/apps-sdk-ui\/components\/Textarea/);
  assert.match(componentSource, /aria-label="批注选中的模型回复"/);
  assert.match(componentSource, /role="alert"/);
  assert.match(helperSource, /selection\.isCollapsed/);
  assert.match(helperSource, /container\.contains\(anchorElement\)/);
  assert.match(helperSource, /closest\("\.bubble"\)/);
  assert.match(helperSource, /height: rect\.height/);
  assert.match(componentSource, /height: anchor\.height/);
  assert.match(componentStyles, /--response-annotation-surface/);
  assert.match(componentStyles, /--response-annotation-excerpt/);
  assert.match(componentStyles, /\[data-theme="dark"\]/);
});

test("annotation submission uses the explicit action without a keyboard shortcut", () => {
  assert.match(
    componentSource,
    /<Button[\s\S]*?type="submit"[\s\S]*?>[\s\S]*?加入 Bad Case[\s\S]*?<\/Button>/,
  );
  assert.doesNotMatch(componentSource, /将保存为 Bad case/);
  assert.doesNotMatch(componentSource, />\s*加入评测集\s*</);
  assert.doesNotMatch(componentSource, /isImeCompositionEvent/);
  assert.doesNotMatch(componentSource, /onKeyDown=/);
  assert.doesNotMatch(componentSource, /event\.metaKey|event\.ctrlKey/);
  assert.doesNotMatch(componentSource, /requestSubmit\(/);
  assert.doesNotMatch(componentSource, /⌘\s*Enter|Ctrl\s*Enter/);
});

test("repeated selections remount a fresh annotation form after submission", () => {
  const targetType = appSource.slice(
    appSource.indexOf("interface ResponseAnnotationTarget"),
    appSource.indexOf("interface ResponseAnnotationContext"),
  );
  const selectionHandler = appSource.slice(
    appSource.indexOf("const openResponseAnnotation"),
    appSource.indexOf("const conversationAutoFollowRef"),
  );
  const popoverRender = appSource.slice(
    appSource.indexOf("{responseAnnotationTarget && sessionId && ("),
    appSource.indexOf("{traceOpen && sessionId && ("),
  );

  // The form owns submitted/note/error state. Selecting the same text twice
  // must still create a new component instance instead of reusing the first
  // submission's success state.
  assert.match(componentSource, /const \[submitted, setSubmitted\] = useState\(false\)/);
  assert.match(componentSource, /setSubmitted\(true\)/);
  assert.match(targetType, /selectionId:\s*number/);
  assert.match(appSource, /responseAnnotationSelectionIdRef\s*=\s*useRef\(0\)/);
  assert.match(
    selectionHandler,
    /selectionId:\s*\+\+responseAnnotationSelectionIdRef\.current/,
  );
  assert.match(
    popoverRender,
    /key=\{responseAnnotationTarget\.selectionId\}/,
  );
  assert.match(
    popoverRender,
    /current\?\.selectionId === responseAnnotationTarget\.selectionId\s*\? null\s*:\s*current/,
  );
  assert.doesNotMatch(
    popoverRender,
    /key=\{`\$\{responseAnnotationTarget\.eventId\}:\$\{responseAnnotationTarget\.selectedText\}`\}/,
  );
  assert.match(
    appSource,
    /responseAnnotationContextsRef\s*=\s*useRef<\s*WeakMap<HTMLDivElement, ResponseAnnotationContext>/,
  );
  assert.match(
    selectionHandler,
    /closest<HTMLDivElement>\("\.turn--assistant"\)/,
  );
  assert.doesNotMatch(
    appSource,
    /responseAnnotationContextsRef\.current\.delete/,
  );
});

test("submits the annotation as a bad-case feedback sample", () => {
  assert.match(appSource, /rateAssistantTurn\(\s*target\.turn,\s*"bad"/);
  assert.match(
    appSource,
    /rateAssistantTurn\([\s\S]*?formatResponseAnnotationComment\(target\.selectedText, note\)/,
  );
  assert.match(appSource, /cloudProvider !== "byteplus"/);
  assert.match(
    appSource,
    /const turnIsStreaming = isLast && \([\s\S]*?activeConversationBusy \|\| presentingStream/,
  );
  assert.match(appSource, /!turnIsStreaming/);
  assert.match(clientSource, /const comment = args\.comment \?\? ""/);
  assert.match(clientSource, /const isAnnotatedBadCase = args\.rating === "bad"/);
  assert.match(clientSource, /source: "user"/);
  assert.match(clientSource, /score: isAnnotatedBadCase \? 0 : null/);
  assert.match(clientSource, /reason: isAnnotatedBadCase \? comment : ""/);
});
