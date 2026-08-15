import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const sandboxClientSource = readFileSync(
  new URL("../src/adk/sandbox.ts", import.meta.url),
  "utf8",
);
const dialogSource = readFileSync(
  new URL("../src/ui/SandboxProjectUploadDialog.tsx", import.meta.url),
  "utf8",
);
const dialogStyles = readFileSync(
  new URL("../src/ui/SandboxProjectUploadDialog.css", import.meta.url),
  "utf8",
);
const myAgentsSource = readFileSync(
  new URL("../src/ui/MyAgents.tsx", import.meta.url),
  "utf8",
);
const myAgentsStyles = readFileSync(
  new URL("../src/ui/MyAgents.css", import.meta.url),
  "utf8",
);
const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const uploadSkillSource = readFileSync(
  new URL(
    "../../plugins/agentkit-studio/skills/codex-sandbox-upload/SKILL.md",
    import.meta.url,
  ),
  "utf8",
);

test("codex project handoff pairing code supports countdown, refresh, and status polling", () => {
  assert.match(
    sandboxClientSource,
    /CODEX_PROJECT_HANDOFF_PAIRING_TTL_SECONDS = 60 \* 60/,
  );
  assert.match(
    sandboxClientSource,
    /body: JSON\.stringify\(\{[\s\S]*?ttlSeconds: CODEX_PROJECT_HANDOFF_PAIRING_TTL_SECONDS/,
  );
  assert.match(dialogSource, /createCodexProjectHandoffPairing/);
  assert.match(sandboxClientSource, /getCodexProjectHandoffStatus/);
  assert.match(sandboxClientSource, /typeof value\.agentName === "string"/);
  assert.match(dialogSource, /getCodexProjectHandoffStatus/);
  assert.match(dialogSource, /handoffStatus\.agentName/);
  assert.match(dialogSource, /formatPairingCountdown/);
  assert.match(dialogSource, /配对码有效期剩余/);
  assert.match(dialogSource, /刷新配对码/);
  assert.doesNotMatch(dialogSource, /<dt>Studio 地址<\/dt>/);
});

test("the uninstalled path asks Codex to install the Studio plugin", () => {
  assert.match(dialogSource, /未安装或不确定/);
  assert.match(dialogSource, /不要让我手动打开终端/);
  assert.match(
    dialogSource,
    /codex plugin marketplace add evanlowe\/veadk-python-fork/,
  );
  assert.match(dialogSource, /--ref feat\/codex-project-handoff-plugin/);
  assert.match(dialogSource, /--sparse \.agents\/plugins/);
  assert.match(dialogSource, /--sparse plugins\/agentkit-studio/);
  assert.match(dialogSource, /codex plugin add agentkit-studio@veadk-python/);
  assert.doesNotMatch(dialogSource, /不要新建 Codex 任务/);
  assert.match(uploadSkillSource, /stay in the current Codex task/);
  assert.match(uploadSkillSource, /terse handoff prompt/);
  assert.doesNotMatch(dialogSource, /codex skill install/);
});

test("the installed path generates a short cloud continuation prompt", () => {
  assert.match(dialogSource, /已经安装/);
  assert.match(dialogSource, /端云接力当前项目和任务/);
  assert.match(dialogSource, /Studio：\$\{studioUrl\}/);
  assert.match(dialogSource, /配对码：\$\{pairing\.pairingCode\}/);
  assert.match(dialogSource, /复制后粘贴到当前 Codex 任务中/);
  assert.doesNotMatch(dialogSource, /authorization_code/);
  assert.doesNotMatch(dialogSource, /repo: 当前工作目录/);
});

test("the dialog uses the requested copy and normal body typography", () => {
  assert.match(
    dialogSource,
    /复制 Prompt 到你的 Codex，它会迁移项目并在云端继续您的任务/,
  );
  assert.match(dialogSource, /<span>提示词<\/span>/);
  assert.match(dialogSource, /复制提示词/);
  assert.match(
    dialogStyles,
    /\.sandbox-project-upload-command code\s*\{[\s\S]*?font-family:\s*inherit/,
  );
  assert.doesNotMatch(dialogStyles, /ui-monospace|SFMono-Regular|Consolas/);
});

test("handoff progress can open the completed Codex session", () => {
  assert.match(dialogSource, /等待端侧请求/);
  assert.match(dialogSource, /创建云端 Session/);
  assert.match(dialogSource, /恢复项目/);
  assert.match(dialogSource, /发送续跑任务/);
  assert.match(dialogSource, /进入 Codex/);
  assert.match(dialogSource, /onOpenSession/);
  assert.match(appSource, /async function openCodexHandoffSession/);
  assert.match(appSource, /await sandboxClient\.listSessions\(\)/);
  assert.match(appSource, /await openSandboxAgent\(session, "my_agents"\)/);
  assert.match(appSource, /onOpenSession=\{openCodexHandoffSession\}/);
});

test("GitHub credential handling stays in the upload skill instead of the dialog", () => {
  assert.doesNotMatch(dialogSource, /gh auth login/);
  assert.doesNotMatch(dialogSource, /GitHub CLI 凭据/);
  assert.doesNotMatch(dialogSource, /GitHub 凭据安装结果/);
  assert.match(uploadSkillSource, /verify `gh auth token --hostname github\.com` succeeds/);
  assert.match(uploadSkillSource, /GitHub authentication is transferred separately/);
  assert.match(uploadSkillSource, /temporary Studio Sandbox/);
  assert.match(uploadSkillSource, /send the continuation message/);
});

test("handoff choices and prompt content reserve stable space", () => {
  assert.match(dialogStyles, /\.sandbox-project-upload-status-options\s*\{[\s\S]*?grid-auto-rows:\s*1fr/);
  assert.match(dialogStyles, /\.sandbox-project-upload-status-options label\s*\{[\s\S]*?min-height:\s*68px/);
  assert.match(dialogStyles, /\.sandbox-project-upload-command-content\s*\{[\s\S]*?height:\s*clamp\(/);
  assert.match(dialogSource, /className="sandbox-project-upload-command-content"/);
  assert.doesNotMatch(dialogSource, /pluginStatus === "installed" \? "云端接力 Prompt"/);
});

test("the Codex project handoff entry is named 接力", () => {
  assert.doesNotMatch(myAgentsSource, /本地Codex项目上传/);
  assert.equal(myAgentsSource.match(/接力/g)?.length, 2);
  assert.match(
    myAgentsStyles,
    /\.my-agent-create-secondary\s*\{[\s\S]*?height:\s*32px[\s\S]*?display:\s*inline-flex/,
  );
  assert.match(
    myAgentsStyles,
    /\.my-agent-create-primary\s*\{[\s\S]*?height:\s*32px[\s\S]*?display:\s*inline-flex/,
  );
});
