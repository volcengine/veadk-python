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

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const appSource = read("../src/App.tsx");
const clientSource = read("../src/adk/client.ts");
const reportSource = read("../src/adk/issueFeedback.ts");
const traceDrawerSource = read("../src/ui/TraceDrawer.tsx");
const appStyles = read("../src/styles.css");
const dialogSource = read("../src/ui/IssueFeedbackDialog.tsx");
const dialogStyles = read("../src/ui/IssueFeedbackDialog.css");
const iconSource = read("../src/ui/icons/FeedbackIcons.tsx");
const sidebarSource = read("../src/ui/Sidebar.tsx");
const platformSource = read("../src/ui/PlatformFeedback.tsx");
const platformStyles = read("../src/ui/PlatformFeedback.css");

test("assistant action row opens issue feedback for the selected turn", () => {
  assert.match(appSource, /aria-label="问题反馈"/);
  assert.match(appSource, /<IssueFeedbackIcon/);
  assert.match(appSource, /setIssueFeedbackTarget\(\{/);
  assert.match(appSource, /input: previousUserTurnText\(turns, i\)/);
  assert.match(appSource, /<IssueFeedbackDialog/);
  assert.match(iconSource, /export function IssueFeedbackIcon/);
  assert.doesNotMatch(iconSource, /lucide-react/);
});

test("dialog explains privacy, supports issue chips, and shows success feedback", () => {
  assert.match(
    dialogSource,
    /您的对话数据将会上报到 AgentKit 团队，请注意隐私保护。/,
  );
  assert.match(dialogSource, /执行速度慢/);
  assert.match(dialogSource, /运行崩溃/);
  assert.match(dialogSource, /工具调用失败/);
  assert.match(dialogSource, /aria-pressed=\{selectedIssues\.has\(issue\.value\)\}/);
  assert.match(dialogSource, /<textarea/);
  assert.match(dialogSource, /role="alert"/);
  assert.match(dialogSource, /上报成功，感谢您的反馈/);
  assert.doesNotMatch(dialogSource, /navigator\.clipboard/);
  assert.doesNotMatch(dialogSource, /Trace ID/);
  assert.match(
    dialogSource,
    /aria-describedby=\{submitted \? `\$\{descriptionId\}-success` : descriptionId\}/,
  );
  assert.match(dialogStyles, /color:\s*hsl\(var\(--destructive\)\)/);
  assert.match(dialogStyles, /:focus-visible/);
  assert.match(dialogStyles, /prefers-reduced-motion:\s*reduce/);
});

test("report includes the full turn details and invocation trace", () => {
  assert.match(reportSource, /block\.kind === "tool"/);
  assert.match(reportSource, /args:\s*block\.args/);
  assert.match(reportSource, /response:\s*block\.response/);
  assert.match(reportSource, /attributes\["invocation\.id"\]/);
  assert.match(reportSource, /matchingTraceIds\.has\(span\.trace_id\)/);
  assert.match(reportSource, /return matchingSpans\.length > 0 \? matchingSpans : spans/);
  assert.match(clientSource, /\/web\/issue-feedback/);
  assert.match(reportSource, /runtimeId: string/);
  assert.match(clientSource, /Promise<\{ submitted: true \}>/);
  assert.equal(
    (appSource.match(/runtimeId: connectedRuntimeId/g) ?? []).length,
    2,
  );
  assert.match(appSource, /source: "agent_exec"/);
  assert.match(appSource, /connectedRuntimeId\s*\?\s*\[\]/);
  assert.match(appSource, /region: currentRuntime\?\.region \?\? "cn-beijing"/);
});

test("remote runtime trace 404 explains that tracing must be enabled", () => {
  assert.match(clientSource, /if \(ep\.runtimeId\)/);
  assert.match(clientSource, /\/web\/runtime-trace/);
  assert.match(clientSource, /String\(Math\.round\(endTimeMs\)\)/);
  assert.match(
    clientSource,
    /该 Agent 暂未开启链路观测，请到控制台打开后使用。/,
  );
});

test("trace loading state is centered in the drawer content area", () => {
  assert.match(traceDrawerSource, /className="drawer-loading"/);
  assert.match(
    appStyles,
    /\.drawer-loading\s*\{[^}]*flex:\s*1;[^}]*justify-content:\s*center;/s,
  );
});

test("sidebar opens a platform feedback page with suggested issue pills", () => {
  assert.match(sidebarSource, /className="sidebar-footer"/);
  assert.match(sidebarSource, /onIssueFeedback/);
  assert.match(sidebarSource, /系统信息[\s\S]*?问题反馈[\s\S]*?退出登录/);
  assert.match(sidebarSource, /<AgentKitPromoCard cloudProvider=\{cloudProvider\}/);
  assert.match(sidebarSource, /className="sidebar-beta-badge">Beta/);
  assert.match(appSource, /initialModule=\{issueFeedbackModuleForPage\(platformFeedbackOrigin\)\}/);
  assert.match(appSource, /source: "platform"/);
  assert.match(appSource, /module: feedback\.module/);
  assert.match(appSource, /contextTurns\.flatMap\(issueFeedbackToolCalls\)/);
  assert.match(platformSource, /<h1>问题反馈<\/h1>/);
  assert.match(platformSource, /所属模块/);
  assert.match(platformSource, /module === option\.value/);
  assert.doesNotMatch(platformSource, /请简要说明您遇到的问题/);
  assert.doesNotMatch(platformSource, /const \[problem, setProblem\]/);
  assert.match(platformSource, /页面加载慢/);
  assert.match(platformSource, /功能无法使用/);
  assert.match(platformSource, /快捷补充/);
  assert.match(platformSource, /问题描述推荐/);
  assert.match(platformSource, /您的数据将会上报到 AgentKit 团队，请注意隐私保护。/);
  assert.match(platformSource, /上报成功，感谢您的反馈/);
  assert.doesNotMatch(platformSource, /navigator\.clipboard/);
  assert.doesNotMatch(platformSource, /Trace ID/);
  assert.match(platformStyles, /color:\s*hsl\(var\(--destructive\)\)/);
  assert.match(platformStyles, /:focus-visible/);
  assert.match(platformStyles, /box-shadow:\s*inset 0 0 0 1px/);
  assert.match(platformStyles, /prefers-reduced-motion:\s*reduce/);
  assert.match(
    platformStyles,
    /\.platform-feedback-form,\s*\.platform-feedback-success\s*\{\s*width:/,
  );
});
