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
  assert.match(controlSource, /releaseReached\(next\.currentVersion, target\)/);
  assert.match(controlSource, /targetVersionRef\.current = result\.version/);
  assert.match(controlSource, /!target && !next\.available/);
  assert.match(controlSource, /window\.location\.reload\(\)/);
});

test("update state survives refreshes and instance switches", () => {
  assert.match(controlSource, /STUDIO_UPDATE_STORAGE_KEY/);
  assert.match(controlSource, /window\.localStorage\.setItem/);
  assert.match(controlSource, /window\.localStorage\.getItem/);
  assert.match(controlSource, /persistPendingUpdate\(targetVersion/);
  assert.match(controlSource, /clearPendingUpdate\(\)/);
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
  assert.match(controlSource, /targetRelease\.changelog\.map/);
  assert.match(controlSource, /暂无更新说明/);
  assert.match(controlStyleSource, /background: #1664ff/);
});

test("Studio exposes detailed update stages that can be reopened", () => {
  assert.match(controlSource, /下载并校验完整更新包/);
  assert.match(controlSource, /准备 VeFaaS Function 代码/);
  assert.match(controlSource, /检查并补齐 Studio 云资源/);
  assert.match(controlSource, /发布新 Revision 并重启服务/);
  assert.match(controlSource, /setDialogOpen\(true\)/);
  assert.match(controlSource, /关闭此窗口不会停止更新/);
  assert.match(controlSource, /后台运行/);
  assert.match(clientSource, /progressStage:/);
  assert.match(controlStyleSource, /studio-update-progress-dot/);
});

test("Studio renders bounded VeFaaS logs without stealing manual scroll", () => {
  assert.match(clientSource, /updateLogs: string\[\]/);
  assert.match(controlSource, /VeFaaS 更新日志/);
  assert.match(controlSource, /role="log"/);
  assert.match(controlSource, /aria-live="off"/);
  assert.match(
    controlSource,
    /root\.scrollHeight - root\.scrollTop - root\.clientHeight < 24/,
  );
  assert.match(
    controlSource,
    /followRef\.current\) root\.scrollTop = root\.scrollHeight/,
  );
  assert.match(controlStyleSource, /font-family: inherit/);
});
