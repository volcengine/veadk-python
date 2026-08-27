import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const controlSource = readFileSync(
  new URL("../src/ui/StudioUpdateControl.tsx", import.meta.url),
  "utf8",
);
const controlStyleSource = readFileSync(
  new URL("../src/ui/StudioUpdateControl.css", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);
const featureNoticeSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatFeatureNotice.tsx", import.meta.url),
  "utf8",
);
const releaseNotesSource = readFileSync(
  new URL("../src/ui/releaseNotes.ts", import.meta.url),
  "utf8",
);

test("only administrators see an available Studio update as an immediate action", () => {
  assert.match(
    appSource,
    /<NewChatFeatureNotice canUpdate=\{access\.role === "admin"\} \/>/,
  );
  assert.match(featureNoticeSource, /canUpdate\?: boolean/);
  assert.match(
    featureNoticeSource,
    /查看新特性[\s\S]*?\{canUpdate && <StudioUpdateControl variant="feature-link" \/>\}/,
  );
  assert.match(
    controlSource,
    /variant === "feature-link"[\s\S]*?<span>立即更新<\/span>/,
  );
});

test("available updates replace the feature hover and the dialog contains long text", () => {
  assert.match(
    stylesSource,
    /\.welcome-feature-pill:has\(\.studio-update-trigger--feature\)[\s\S]*?> \.welcome-feature-popover[\s\S]*?display:\s*none/,
  );
  assert.match(
    controlStyleSource,
    /\.studio-update-dialog\s*\{[\s\S]*?width:\s*min\(500px, calc\(100vw - 32px\)\);[\s\S]*?min-width:\s*0;/,
  );
  assert.match(
    controlStyleSource,
    /\.studio-update-dialog > :not\([^}]+\)\s*\{[\s\S]*?min-width:\s*0;/,
  );
  assert.match(
    controlStyleSource,
    /\.studio-update-dialog \.confirm-text[\s\S]*?overflow-wrap:\s*anywhere;/,
  );
  assert.match(controlSource, /import \{ createPortal \} from "react-dom"/);
  assert.match(
    controlSource,
    /dialogOpen && phase !== "idle" &&[\s\S]*?createPortal\([\s\S]*?document\.body/,
  );
});

test("Studio checks the immutable release channel every three minutes", () => {
  assert.match(controlSource, /CHECK_INTERVAL_MS = 3 \* 60 \* 1000/);
  assert.match(controlSource, /window\.setInterval\(check, CHECK_INTERVAL_MS\)/);
  assert.match(clientSource, /apiFetch\(`\/web\/studio-update\$\{query\}`\)/);
});

test("update submission is explicit and survives a revision switch", () => {
  assert.match(clientSource, /"X-VeADK-Studio-Update": "1"/);
  assert.match(clientSource, /body: JSON\.stringify\(\{ version \}\)/);
  assert.match(controlSource, /RELEASE_POLL_INTERVAL_MS = 3_000/);
  assert.match(controlSource, /Replacing the current Revision may briefly interrupt/);
  assert.match(controlSource, /error\.name === "TimeoutError"/);
  assert.match(controlSource, /error\.name === "AbortError"/);
  assert.match(controlSource, /releaseReached\(next\.currentVersion, target\)/);
  assert.match(controlSource, /targetVersionRef\.current = result\.version/);
  assert.match(controlSource, /!target && !next\.available/);
  assert.match(controlSource, /persistUpdateHandoff\(completedTarget\)/);
  assert.match(controlSource, /window\.location\.reload\(\)/);
  assert.match(controlSource, /handoffTargetRef\.current !== completedTarget/);
  assert.match(controlSource, /setDialogOpen\(true\)/);
  assert.match(controlSource, /COMPLETION_LOG_SETTLE_TIMEOUT_MS = 45_000/);
  assert.match(controlSource, /deploymentLogComplete\(next\.updateLogs\)/);
  assert.match(
    controlSource,
    /next\.updateLogsVisible !== false &&[\s\S]*?!deploymentLogComplete\(next\.updateLogs\)/,
  );
  assert.match(controlSource, /line\.includes\("部署应用成功"\)/);
});

test("update state survives refreshes and instance switches", () => {
  assert.match(controlSource, /STUDIO_UPDATE_STORAGE_KEY/);
  assert.match(controlSource, /window\.localStorage\.setItem/);
  assert.match(controlSource, /window\.localStorage\.getItem/);
  assert.match(controlSource, /window\.sessionStorage\.setItem/);
  assert.match(controlSource, /window\.sessionStorage\.getItem/);
  assert.match(controlSource, /persistPendingUpdate\(targetVersion/);
  assert.match(controlSource, /clearPendingUpdate\(\)/);
  assert.match(controlSource, /useState\(Boolean\(initialPending\)\)/);
  assert.match(clientSource, /targetVersion\?: string/);
  assert.match(clientSource, /startedAt\?: number/);
  assert.match(clientSource, /params\.set\("targetVersion", targetVersion\)/);
  assert.match(clientSource, /params\.set\("startedAt", String\(startedAt\)\)/);
  assert.match(controlSource, /current > target/);
});

test("Studio explains the update restart window", () => {
  assert.match(controlSource, /<span>有新版更新<\/span>/);
  assert.match(controlSource, /预计约 3–5 分钟完成更新与发布/);
  assert.match(controlSource, /登录态不会受到影响/);
  assert.match(controlSource, /<span>选择版本<\/span>/);
  assert.match(controlSource, /splitReleaseNotes\(targetRelease\?\.changelog \?\? \[\]\)/);
  assert.match(controlSource, /targetReleaseNotes\.map/);
  assert.match(controlSource, /暂无更新说明/);
  assert.match(
    controlStyleSource,
    /\.studio-update-changelog ul\s*\{[\s\S]*?list-style:\s*disc outside;/,
  );
  assert.match(
    controlStyleSource,
    /\.studio-update-changelog li\s*\{[\s\S]*?display:\s*list-item;/,
  );
  assert.match(controlStyleSource, /background: #1664ff/);
});

test("Studio prechecks every OTA permission before starting cloud changes", () => {
  assert.match(clientSource, /StudioUpdatePermissionStatus/);
  assert.match(clientSource, /\/web\/studio-update\/permissions/);
  assert.match(
    controlSource,
    /const permissions = await getStudioUpdatePermissions\(\);[\s\S]*?startStudioUpdate\(targetVersion\)/,
  );
  assert.match(controlSource, /尚未执行任何云资源变更/);
  assert.match(controlSource, /打开已预填的 IAM 授权页面/);
  assert.match(controlSource, /点击页面中的“发起调试”/);
  assert.match(controlSource, /我已授权，重新检查/);
  assert.match(controlSource, /permissionStatus\.missingActions\.map/);
  assert.match(controlStyleSource, /studio-update-authorization-panel/);
});

test("current and target release notes share semicolon bullet rendering", () => {
  assert.match(releaseNotesSource, /RELEASE_NOTE_SEPARATOR = \/\[;；\]\//);
  assert.match(featureNoticeSource, /VITE_STUDIO_RELEASE_CHANGELOG/);
  assert.match(featureNoticeSource, /parseReleaseNotes/);
  assert.match(featureNoticeSource, /releaseNotes\.map/);
  assert.match(
    stylesSource,
    /\.welcome-feature-popover ul\s*\{[\s\S]*?list-style:\s*disc outside;/,
  );
});

test("Studio exposes detailed update stages that can be reopened", () => {
  assert.match(controlSource, /下载并校验完整更新包/);
  assert.match(controlSource, /准备 VeFaaS Function 代码/);
  assert.match(controlSource, /检查并补齐 Studio 云资源/);
  assert.match(
    controlSource,
    /检查并补齐 Studio 云资源[\s\S]*?更新定时任务调度服务[\s\S]*?提交 Function 更新/,
  );
  assert.match(controlSource, /发布新 Revision 并重启服务/);
  assert.match(clientSource, /\| "scheduler"/);
  assert.match(controlSource, /unknownProgressStage/);
  assert.match(controlSource, /aria-current=\{active \? "step" : undefined\}/);
  assert.match(controlSource, /setDialogOpen\(true\)/);
  assert.match(controlSource, /关闭此窗口不会停止更新/);
  assert.match(controlSource, /后台运行/);
  assert.match(clientSource, /progressStage:/);
  assert.match(controlStyleSource, /studio-update-progress-dot/);
});

test("Studio renders bounded VeFaaS logs without stealing manual scroll", () => {
  assert.match(clientSource, /updateLogs: string\[\]/);
  assert.match(clientSource, /updateLogsVisible: boolean/);
  assert.match(controlSource, /部署进度/);
  assert.doesNotMatch(controlSource, /VeFaaS 实时部署日志/);
  assert.match(controlSource, /role="log"/);
  assert.match(controlSource, /aria-live="off"/);
  assert.match(controlSource, /aria-busy=\{phase === "active"\}/);
  assert.match(controlSource, /if \(lines\.length\) setVisibleLines\(lines\)/);
  assert.match(
    controlSource,
    /root\.scrollHeight - root\.scrollTop - root\.clientHeight < 24/,
  );
  assert.match(
    controlSource,
    /followRef\.current\) root\.scrollTop = root\.scrollHeight/,
  );
  assert.match(controlStyleSource, /font-family: inherit/);
  assert.match(controlSource, /status\.updateLogsVisible !== false/);
  assert.match(
    controlStyleSource,
    /\.studio-update-dialog\.is-progress\s*\{[\s\S]*?height:\s*min\(700px, calc\(100dvh - 32px\)\)/,
  );
  assert.match(
    controlStyleSource,
    /\.studio-update-progress-body\s*\{[\s\S]*?grid-template-rows:[\s\S]*?minmax\(120px, 1fr\)/,
  );
  assert.match(
    controlStyleSource,
    /\.studio-update-progress-body \.studio-update-log-lines,\s*[\s\S]*?\{[\s\S]*?overflow-y:\s*auto/,
  );
});

test("Studio explains how to grant optional VeFaaS log permission", () => {
  assert.match(
    controlSource,
    /\{status\.updateLogsVisible !== false && \([\s\S]*?<StudioUpdateLog/,
  );
  assert.match(controlSource, /status\.updateLogsVisible !== false/g);
  assert.match(controlSource, /status\.updateLogsVisible === false/g);
  assert.match(controlSource, /vefaas:GetApplicationRevisionLog/);
  assert.match(controlSource, /更新会继续/);
  assert.match(controlSource, /前往 IAM 控制台配置权限/);
  assert.match(controlSource, /href=\{status\.permissionConsoleUrl\}/);
  assert.match(clientSource, /permissionConsoleUrl: string/);
  assert.match(controlStyleSource, /studio-update-permission-notice/);
  assert.doesNotMatch(controlSource, /↗/);
});
