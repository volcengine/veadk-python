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

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const blockSource = readFileSync(new URL("../src/blocks.ts", import.meta.url), "utf8");
const iconSource = readFileSync(
  new URL("../src/ui/icons/FeedbackIcons.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

test("assistant feedback is tied to the final ADK event", () => {
  assert.match(blockSource, /eventId\?: string/);
  assert.match(blockSource, /invocationId\?: string/);
  assert.match(appSource, /submitMessageFeedback/);
  assert.match(
    readFileSync(new URL("../src/adk/client.ts", import.meta.url), "utf8"),
    /MESSAGE_FEEDBACK_CACHE_KEY/,
  );
});

test("feedback controls keep only the accessible rating actions", () => {
  assert.match(appSource, /aria-label="赞"/);
  assert.match(appSource, /aria-label="踩"/);
  assert.doesNotMatch(appSource, /aria-label="查看评测案例"/);
  assert.doesNotMatch(appSource, /<ListTodo\b/);
  assert.match(appSource, /aria-pressed=/);
  assert.match(appSource, /filled=\{feedbackRating === "good"\}/);
  assert.match(appSource, /filled=\{feedbackRating === "bad"\}/);
  assert.match(iconSource, /viewBox="0 0 24 24"/);
  assert.match(iconSource, /filled \? "currentColor" : "none"/);
  assert.match(iconSource, /rx="1\.5"/);
  assert.match(iconSource, /strokeLinecap="round"/);
  assert.doesNotMatch(iconSource, /lucide-react/);
});

test("feedback selection updates immediately and uses a neutral solid icon", () => {
  const handler = appSource.slice(
    appSource.indexOf("const rateAssistantTurn"),
    appSource.indexOf("const send = async"),
  );
  assert.ok(
    handler.indexOf('syncStatus: "syncing"') <
      handler.indexOf("await submitMessageFeedback"),
  );
  assert.ok(
    handler.indexOf("upsertCachedAgentFeedbackCase") <
      handler.indexOf("await submitMessageFeedback"),
  );
  assert.match(handler, /feedback: previousFeedback/);
  assert.match(handler, /upsertCachedAgentFeedbackCase\(\{/);
  assert.match(handler, /rating,/);
  assert.match(handler, /rating: feedback\.rating/);
  assert.match(handler, /rating: previousFeedback\?\.rating \?\? null/);
  assert.match(handler, /input,/);
  assert.match(handler, /output,/);
  assert.match(handler, /refreshAgentFeedbackCases\(\{/);
  assert.match(handler, /appName: currentRuntimeAppName/);
  assert.match(stylesSource, /\.feedback-btn--good,[\s\S]*color: hsl\(var\(--foreground\)\)/);
  assert.doesNotMatch(stylesSource, /\.feedback-btn--good[\s\S]{0,120}142/);
  assert.doesNotMatch(stylesSource, /\.feedback-btn--bad[\s\S]{0,120}destructive/);
});

test("chat feedback row has no evaluation case shortcut", () => {
  assert.doesNotMatch(appSource, /const openCurrentAgentCases/);
  assert.match(appSource, /feedbackCasePreview=\{feedbackCasePreview\}/);
  assert.match(appSource, /previousUserTurnText\(turns, i\)/);
  assert.match(appSource, /rateAssistantTurn\(\s*turn,\s*feedbackRating === "good" \? null : "good",\s*feedbackInput,\s*\)/);
  assert.match(appSource, /rateAssistantTurn\(\s*turn,\s*feedbackRating === "bad" \? null : "bad",\s*feedbackInput,\s*\)/);
});
