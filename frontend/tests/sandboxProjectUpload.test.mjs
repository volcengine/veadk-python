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
const frontendUploadSkillSource = readFileSync(
  new URL(
    "../skills/agentkit-codex-handoff/SKILL.md",
    import.meta.url,
  ),
  "utf8",
);
const pluginUploadSkillSource = readFileSync(
  new URL(
    "../../plugins/agentkit-studio/skills/agentkit-codex-handoff/SKILL.md",
    import.meta.url,
  ),
  "utf8",
);
const uploadScriptSource = readFileSync(
  new URL(
    "../skills/agentkit-codex-handoff/scripts/upload_project.py",
    import.meta.url,
  ),
  "utf8",
);
const pluginUploadScriptSource = readFileSync(
  new URL(
    "../../plugins/agentkit-studio/skills/agentkit-codex-handoff/scripts/upload_project.py",
    import.meta.url,
  ),
  "utf8",
);
const sandboxCommandsSource = readFileSync(
  new URL("../src/ui/sandboxCommands.ts", import.meta.url),
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
  assert.match(sandboxClientSource, /async function responseJson/);
  assert.match(
    sandboxClientSource,
    /Studio 服务响应异常，请刷新后重试/,
  );
  assert.doesNotMatch(
    sandboxClientSource,
    /getCodexProjectHandoffStatus[\s\S]*?recordOf\(await response\.json\(\)\)/,
  );
  assert.match(sandboxClientSource, /typeof value\.agentName === "string"/);
  assert.match(dialogSource, /getCodexProjectHandoffStatus/);
  assert.match(dialogSource, /handoffStatus\.agentName/);
  assert.match(dialogSource, /formatPairingCountdown/);
  assert.match(dialogSource, /配对码有效期剩余/);
  assert.match(dialogSource, /刷新配对码/);
  assert.doesNotMatch(dialogSource, /<dt>Studio 地址<\/dt>/);
});

test("the install step only asks Codex to install the Studio plugin", () => {
  assert.match(dialogSource, /<h3>安装插件<\/h3>/);
  assert.match(dialogSource, /复制安装提示词/);
  assert.match(dialogSource, /不要让我手动打开终端/);
  assert.match(dialogSource, /function installPluginPrompt\(\): string/);
  assert.match(
    dialogSource,
    /codex plugin marketplace add volcengine\/veadk-python/,
  );
  assert.match(dialogSource, /--sparse \.agents\/plugins/);
  assert.match(dialogSource, /--sparse plugins\/agentkit-studio/);
  assert.match(dialogSource, /codex plugin add agentkit-studio@veadk-python/);
  assert.doesNotMatch(dialogSource, /installAndHandoffPrompt/);
  assert.doesNotMatch(dialogSource, /evanlowe\/veadk-python-fork/);
  assert.doesNotMatch(dialogSource, /feat\/codex-project-handoff-plugin/);
  assert.doesNotMatch(dialogSource, /不要新建 Codex 任务/);
  assert.match(frontendUploadSkillSource, /stay in the current Codex task/);
  assert.match(frontendUploadSkillSource, /terse handoff prompt/);
  assert.doesNotMatch(dialogSource, /codex skill install/);
});

test("the frontend and plugin copies of the handoff skill stay synchronized", () => {
  for (const relativePath of [
    "SKILL.md",
    "agents/openai.yaml",
    "scripts/upload_current_dir.sh",
    "scripts/upload_project.py",
  ]) {
    const frontendCopy = readFileSync(
      new URL(`../skills/agentkit-codex-handoff/${relativePath}`, import.meta.url),
      "utf8",
    );
    const pluginCopy = readFileSync(
      new URL(
        `../../plugins/agentkit-studio/skills/agentkit-codex-handoff/${relativePath}`,
        import.meta.url,
      ),
      "utf8",
    );
    assert.equal(frontendCopy, pluginCopy, `${relativePath} must stay synchronized`);
  }
  assert.equal(frontendUploadSkillSource, pluginUploadSkillSource);
  assert.equal(uploadScriptSource, pluginUploadScriptSource);
  assert.match(frontendUploadSkillSource, /name: agentkit-codex-handoff/);
});

test("the dialog does not expose plugin maintenance details", () => {
  assert.doesNotMatch(dialogSource, /codex plugin marketplace upgrade/);
  assert.doesNotMatch(dialogSource, /codex plugin list --json/);
  assert.doesNotMatch(dialogSource, /0\.1\.0/);
  assert.doesNotMatch(dialogSource, /\+codex\./);
  assert.doesNotMatch(dialogSource, /\$agentkit-codex-handoff Skill/);
});

test("the handoff step generates a short cloud continuation prompt", () => {
  assert.match(dialogSource, /<h3>任务接力<\/h3>/);
  assert.match(dialogSource, /复制接力提示词/);
  assert.match(dialogSource, /使用 AgentKit Studio Plugin 端云接力当前会话、项目和任务/);
  assert.match(dialogSource, /Studio：\$\{studioUrl\}/);
  assert.match(dialogSource, /配对码：\$\{pairing\.pairingCode\}/);
  assert.match(dialogSource, /插件安装完成后复制/);
  assert.doesNotMatch(dialogSource, /authorization_code/);
  assert.doesNotMatch(dialogSource, /repo: 当前工作目录/);
});

test("the dialog uses the requested copy and normal body typography", () => {
  assert.match(
    dialogSource,
    /按顺序复制两段提示词，Codex 会安装插件并将当前任务接力到云端/,
  );
  assert.match(dialogSource, /复制安装提示词/);
  assert.match(dialogSource, /复制接力提示词/);
  assert.match(
    dialogStyles,
    /\.sandbox-project-upload-prompt code\s*\{[\s\S]*?font-family:\s*inherit/,
  );
  assert.doesNotMatch(dialogStyles, /ui-monospace|SFMono-Regular|Consolas/);
});

test("the dialog title shows the Apps SDK UI Beta badge", () => {
  assert.match(
    dialogSource,
    /import \{ Badge \} from "@openai\/apps-sdk-ui\/components\/Badge"/,
  );
  assert.match(
    dialogSource,
    /className="sandbox-project-upload-title-row"[\s\S]*?<h2 id="sandbox-project-upload-title">接力到云端继续执行<\/h2>[\s\S]*?<Badge[\s\S]*?className="sandbox-project-upload-beta"[\s\S]*?color="discovery"[\s\S]*?size="sm"[\s\S]*?pill[\s\S]*?>[\s\S]*?Beta[\s\S]*?<\/Badge>/,
  );
  assert.match(
    dialogStyles,
    /\.sandbox-project-upload-title-row\s*\{[\s\S]*?display: flex;[\s\S]*?align-items: center;[\s\S]*?gap: 8px;/,
  );
  assert.match(
    dialogStyles,
    /\.sandbox-project-upload-title-row \.sandbox-project-upload-beta\s*\{[\s\S]*?height: 18px;[\s\S]*?font-size: 10px;[\s\S]*?font-weight: 600;/,
  );
});

test("handoff progress can open the completed Codex session", () => {
  assert.match(dialogSource, /等待端侧请求/);
  assert.match(dialogSource, /创建云端 Session/);
  assert.match(dialogSource, /恢复项目/);
  assert.match(dialogSource, /发送续跑任务/);
  assert.match(dialogSource, /进入 Codex/);
  assert.match(sandboxClientSource, /\| "running"/);
  assert.match(dialogSource, /handoffStatus\?\.state === "running"/);
  assert.match(dialogSource, /return "云端执行中"/);
  assert.match(dialogSource, /onOpenSession/);
  assert.match(appSource, /async function openCodexHandoffSession/);
  assert.match(appSource, /await sandboxClient\.listSessions\(\)/);
  assert.match(appSource, /await sandboxClient\.readThread\(/);
  assert.match(appSource, /await sandboxClient\.listThreads\(/);
  assert.match(appSource, /return sandboxClient\.resumeThread\(/);
  assert.match(appSource, /setSandboxTurns\(sandboxSnapshotTurns\(snapshot\)\)/);
  assert.match(appSource, /await openSandboxAgent\(session, "my_agents"\)/);
  assert.match(appSource, /onOpenSession=\{openCodexHandoffSession\}/);
});

test("handoff upload and restore failures stop on the restore step", () => {
  assert.match(sandboxClientSource, /\| "uploading-project"/);
  assert.match(sandboxClientSource, /\| "restoring-project"/);
  assert.match(
    dialogSource,
    /status\.failedStage === "uploading-project"[\s\S]*?status\.failedStage === "restoring-project"[\s\S]*?return 2/,
  );
  assert.match(dialogSource, /value\.state === "failed" \? 3000 : 1500/);
  assert.doesNotMatch(
    dialogSource,
    /value\.state === "completed" \|\| value\.state === "failed"/,
  );
});

test("GitHub credential handling stays in the upload skill instead of the dialog", () => {
  assert.doesNotMatch(dialogSource, /gh auth login/);
  assert.doesNotMatch(dialogSource, /GitHub CLI 凭据/);
  assert.doesNotMatch(dialogSource, /GitHub 凭据安装结果/);
  assert.match(frontendUploadSkillSource, /verify `gh auth token --hostname github\.com` succeeds/);
  assert.match(frontendUploadSkillSource, /GitHub authentication is transferred separately/);
  assert.match(frontendUploadSkillSource, /temporary Studio Sandbox/);
  assert.match(frontendUploadSkillSource, /completed visible conversation/);
  assert.match(frontendUploadSkillSource, /thread\/inject_items/);
  assert.match(frontendUploadSkillSource, /otherwise use exactly `继续`/);
  assert.match(uploadScriptSource, /"thread\/inject_items"|"history": history/);
  assert.match(frontendUploadSkillSource, /codexDelegation\.input/);
  assert.match(frontendUploadSkillSource, /"schemaVersion":2/);
});

test("imported Codex history renders image attachments in the transcript", () => {
  assert.match(sandboxClientSource, /images\?: SandboxThreadImage\[\]/);
  assert.match(sandboxClientSource, /mimeType: image\.mimeType/);
  assert.match(sandboxCommandsSource, /kind: "attachment"/);
  assert.match(sandboxCommandsSource, /data: image\.data/);
});

test("install and handoff are fixed sequential steps with independent copy actions", () => {
  assert.doesNotMatch(dialogSource, /PluginStatus|pluginStatus|type="radio"/);
  assert.doesNotMatch(dialogSource, /是否已经安装 AgentKit Studio Plugin/);
  assert.match(dialogSource, /type CopyTarget = "install" \| "handoff" \| ""/);
  assert.match(dialogSource, /copy\(installPrompt, "install"\)/);
  assert.match(dialogSource, /copy\(handoffPrompt, "handoff"\)/);
  assert.equal(
    dialogSource.match(/className="sandbox-project-upload-stage"/g)?.length,
    2,
  );
  assert.match(
    dialogSource,
    /<h3>安装插件<\/h3>[\s\S]*?<h3>任务接力<\/h3>/,
  );
  assert.match(dialogStyles, /\.sandbox-project-upload-prompt\s*\{[\s\S]*?min-height:\s*92px/);
  assert.match(dialogSource, /className="sandbox-project-upload-prompt"/);
});

test("handoff progress labels stay on one line without connector pressure", () => {
  assert.match(
    dialogStyles,
    /\.sandbox-project-upload-progress li > span:last-child\s*\{[\s\S]*?white-space:\s*nowrap/,
  );
  assert.match(
    dialogStyles,
    /\.sandbox-project-upload-progress li:not\(:last-child\)::after\s*\{[\s\S]*?position:\s*absolute/,
  );
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
