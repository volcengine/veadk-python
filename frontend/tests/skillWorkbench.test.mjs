import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const center = readFileSync(new URL("../src/ui/SkillCenter.tsx", import.meta.url), "utf8");
const sidebar = readFileSync(new URL("../src/ui/Sidebar.tsx", import.meta.url), "utf8");
const workbench = readFileSync(
  new URL("../src/ui/skill-workbench/SkillWorkbench.tsx", import.meta.url),
  "utf8",
);
const api = readFileSync(
  new URL("../src/ui/skill-workbench/api.ts", import.meta.url),
  "utf8",
);
const styles = readFileSync(
  new URL("../src/ui/skill-workbench/skill-workbench.css", import.meta.url),
  "utf8",
);


test("adds the workbench without replacing the existing Skill creation flow", () => {
  assert.match(app, /<SkillCreateWorkspace initialJob=\{skillJob\}/);
  assert.match(app, /<SkillWorkbench/);
  assert.match(app, /<SkillCenterView/);
  assert.match(app, /skillWorkbenchOpen/);
});


test("provides unified Create and Optimize paths from the Skill Center", () => {
  assert.match(center, /创建 Skill/);
  assert.match(center, /优化 Skill/);
  assert.match(center, /onOptimize\(\{/);
  assert.match(workbench, /role="tablist"/);
  assert.match(workbench, /aria-selected=\{operation === "create"\}/);
  assert.match(workbench, /aria-selected=\{operation === "optimize"\}/);
  assert.match(workbench, /从技能中心选择/);
  assert.match(workbench, /上传 ZIP/);
});


test("keeps every asynchronous state recoverable and avoids dead ends", () => {
  for (const label of [
    "返回技能中心",
    "取消并清理",
    "修改意图后重试",
    "更换来源",
    "下载 ZIP",
    "继续调整",
    "提交调整",
    "发布为新 Skill",
    "更新原 Skill",
    "安全离开",
    "取消并返回",
  ]) assert.match(workbench, new RegExp(label));
  assert.match(workbench, /StudioConfirmDialog/);
  assert.match(workbench, /role="alert"/);
  assert.match(workbench, /aria-live="polite"/);
  assert.match(workbench, /event\.target\.value = ""/);
});


test("uses server-owned APIs with timeouts and cancellation", () => {
  assert.match(api, /\/web\/skill-workbench/);
  assert.match(api, /requestSignal\(init\.signal, timeout\)/);
  assert.match(api, /TRANSFER_REQUEST_TIMEOUT_MS/);
  assert.match(api, /\/tasks\/from-upload/);
  assert.match(api, /method: "DELETE"/);
  assert.match(api, /URL\.revokeObjectURL/);
});


test("keeps the Skill Center discoverable in the existing sidebar", () => {
  assert.match(sidebar, /show\("skillCenter"\)/);
  assert.match(sidebar, /onClick=\{onSkillCenter\}/);
  assert.match(sidebar, /<SkillSpaceIcon/);
});


test("uses bounded desktop layout and reduced motion support", () => {
  assert.match(styles, /min-height:\s*0/);
  assert.match(styles, /overflow-y:\s*auto/);
  assert.match(styles, /@media \(max-width: 980px\)/);
  assert.match(styles, /prefers-reduced-motion: reduce/);
  assert.match(styles, /hsl\(var\(--border\)\)/);
});
