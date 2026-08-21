import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const titleSource = readFileSync(
  new URL("../src/ui/documentTitle.ts", import.meta.url),
  "utf8",
);
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const librarySource = readFileSync(
  new URL("../src/ui/LibraryView.tsx", import.meta.url),
  "utf8",
);
const skillCenterSource = readFileSync(
  new URL("../src/ui/SkillCenter.tsx", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(titleSource, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2020,
  },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const { formatStudioDocumentTitle } = await import(moduleUrl);

test("uses the brand alone for the new conversation surface", () => {
  assert.equal(
    formatStudioDocumentTitle("AgentKit Studio", { kind: "home" }),
    "AgentKit Studio",
  );
});

test("uses a conversation title without repeating the brand", () => {
  assert.equal(
    formatStudioDocumentTitle("AgentKit Studio", {
      kind: "conversation",
      title: "部署 AgentKit Runtime",
    }),
    "部署 AgentKit Runtime",
  );
});

test("prefixes named product surfaces with the configured brand", () => {
  assert.equal(
    formatStudioDocumentTitle("我的工作台", { kind: "page", title: "自动化" }),
    "我的工作台 - 自动化",
  );
  assert.equal(
    formatStudioDocumentTitle(" 我的工作台\n", {
      kind: "page",
      title: "  创建技能  ",
    }),
    "我的工作台 - 创建技能",
  );
});

test("falls back to a stable brand for empty dynamic title data", () => {
  assert.equal(
    formatStudioDocumentTitle("", { kind: "conversation", title: "  " }),
    "AgentKit Studio",
  );
});

test("wires main and nested Studio surfaces into the browser title", () => {
  assert.match(appSource, /formatStudioDocumentTitle\(\s*siteBranding\.title/);
  assert.match(appSource, /activeSessionTitle === "新会话"[\s\S]*?kind: "home"/);
  assert.match(appSource, /getAutomation\(applicationsView\)\.name/);
  assert.match(appSource, /cronJobsView[\s\S]*?kind: "page", title: "定时任务"/);
  assert.match(appSource, /onPageTitleChange=\{setLibraryPageTitle\}/);
  assert.match(appSource, /setLibraryPageTitle\("技能库"\)/);
  assert.match(
    appSource,
    /setLibraryPageTitle\(\s*launch\.operation === "create"[\s\S]*?"创建技能"[\s\S]*?`优化 /,
  );
  assert.match(librarySource, /onPageTitleChange\?\.\(activeTitle\)/);
  assert.match(librarySource, /onPageTitleChange=\{setSkillPageTitle\}/);
  assert.match(skillCenterSource, /workspace\.operation === "create"[\s\S]*?"创建技能"/);
  assert.match(skillCenterSource, /if \(active\) onPageTitleChange\?\.\(pageTitle\)/);
});
