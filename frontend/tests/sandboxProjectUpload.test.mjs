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
const zhSandbox = JSON.parse(readFileSync(
  new URL("../src/i18n/resources/zh-CN/sandbox.json", import.meta.url),
  "utf8",
));
const enSandbox = JSON.parse(readFileSync(
  new URL("../src/i18n/resources/en-US/sandbox.json", import.meta.url),
  "utf8",
));

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
  assert.match(sandboxClientSource, /adkT\("common\.fallbackWithHttpStatus"/);
  assert.match(sandboxClientSource, /adkT\("common\.fallbackWithDetail"/);
  assert.doesNotMatch(
    sandboxClientSource,
    /getCodexProjectHandoffStatus[\s\S]*?recordOf\(await response\.json\(\)\)/,
  );
  assert.match(sandboxClientSource, /typeof value\.agentName === "string"/);
  assert.match(dialogSource, /getCodexProjectHandoffStatus/);
  assert.match(dialogSource, /handoffStatus\.agentName/);
  assert.match(dialogSource, /formatPairingCountdown/);
  assert.match(dialogSource, /t\("handoff\.pairingRemaining"/);
  assert.match(dialogSource, /t\("handoff\.refreshPairing"\)/);
  assert.doesNotMatch(dialogSource, /<dt>Studio 地址<\/dt>/);
});

test("the install step only asks Codex to install the Studio plugin", () => {
  assert.match(dialogSource, /t\("handoff\.installTitle"\)/);
  assert.match(dialogSource, /t\("handoff\.copyInstallPrompt"\)/);
  assert.match(dialogSource, /t\("handoff\.copyInstallCommand"\)/);
  assert.match(zhSandbox.handoff.installPrompt, /不要让我手动打开终端/);
  assert.match(enSandbox.handoff.installPrompt, /do not ask me to open a terminal manually/);
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

test("the install step switches between Codex conversation and terminal tabs", () => {
  assert.match(dialogSource, /type InstallMethod = "conversation" \| "terminal"/);
  assert.match(dialogSource, /role="tablist"/);
  assert.match(dialogSource, /aria-label=\{t\("handoff\.installMethodAria"\)\}/);
  assert.match(dialogSource, /t\("handoff\.conversationInstall"\)/);
  assert.match(dialogSource, /t\("handoff\.terminalInstall"\)/);
  assert.match(dialogSource, /role="tabpanel"/);
  assert.match(dialogSource, /ArrowRight/);
  assert.match(dialogSource, /ArrowLeft/);
  assert.match(dialogSource, /event\.key === "Home"/);
  assert.match(dialogSource, /event\.key === "End"/);
  assert.match(dialogSource, /installMethod === "conversation" \? installPrompt : installCommand/);
  assert.match(
    dialogStyles,
    /\.sandbox-project-upload-install-tabs\s*\{[\s\S]*?grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/,
  );
  assert.match(
    dialogStyles,
    /\.sandbox-project-upload-prompt\.is-command code\s*\{[\s\S]*?font-family: ui-monospace/,
  );
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
  assert.match(dialogSource, /t\("handoff\.taskTitle"\)/);
  assert.match(dialogSource, /t\("handoff\.copyHandoffPrompt"\)/);
  assert.match(dialogSource, /sandboxT\("handoff\.prompt"/);
  assert.match(zhSandbox.handoff.prompt, /使用 AgentKit Studio Plugin 端云接力当前会话、项目和任务/);
  assert.match(zhSandbox.handoff.prompt, /Studio：\{\{studioUrl\}\}/);
  assert.match(zhSandbox.handoff.prompt, /配对码：\{\{pairingCode\}\}/);
  assert.match(zhSandbox.handoff.taskDescription, /插件安装完成后复制/);
  assert.match(enSandbox.handoff.prompt, /Pairing code: \{\{pairingCode\}\}/);
  assert.doesNotMatch(dialogSource, /authorization_code/);
  assert.doesNotMatch(dialogSource, /repo: 当前工作目录/);
});

test("the dialog uses the requested copy and normal body typography", () => {
  assert.match(
    dialogSource,
    /t\("handoff\.description"\)/,
  );
  assert.match(dialogSource, /t\("handoff\.copyInstallPrompt"\)/);
  assert.match(dialogSource, /t\("handoff\.copyHandoffPrompt"\)/);
  assert.match(
    dialogStyles,
    /\.sandbox-project-upload-prompt code\s*\{[\s\S]*?font-family:\s*inherit/,
  );
  assert.match(
    dialogStyles,
    /\.sandbox-project-upload-prompt\.is-command code\s*\{[\s\S]*?font-family:\s*ui-monospace/,
  );
});

test("the dialog title shows the Apps SDK UI Beta badge", () => {
  assert.match(
    dialogSource,
    /import \{ Badge \} from "@openai\/apps-sdk-ui\/components\/Badge"/,
  );
  assert.match(
    dialogSource,
    /className="sandbox-project-upload-title-row"[\s\S]*?<h2 id="sandbox-project-upload-title">\{t\("handoff\.title"\)\}<\/h2>[\s\S]*?<Badge[\s\S]*?className="sandbox-project-upload-beta"[\s\S]*?color="discovery"[\s\S]*?size="sm"[\s\S]*?pill[\s\S]*?>[\s\S]*?Beta[\s\S]*?<\/Badge>/,
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

test("handoff progress can open the Codex session as soon as it is running", () => {
  assert.match(dialogSource, /t\(`handoff\.steps\.\$\{step\.id\}`\)/);
  assert.deepEqual(Object.keys(zhSandbox.handoff.steps), [
    "request", "session", "restore", "continue",
  ]);
  assert.match(dialogSource, /t\("handoff\.enterCodex"\)/);
  assert.match(sandboxClientSource, /\| "running"/);
  assert.match(
    dialogSource,
    /\(handoffStatus\?\.state === "running" \|\|[\s\S]*?handoffStatus\?\.state === "completed"\)[\s\S]*?handoffStatus\.sessionId/,
  );
  assert.match(dialogSource, /return sandboxT\("handoff\.status\.running"\)/);
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
  assert.match(
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
  assert.match(frontendUploadSkillSource, /complete visible conversation/);
  assert.match(frontendUploadSkillSource, /thread\/inject_items/);
  assert.match(frontendUploadSkillSource, /otherwise use exactly `继续`/);
  assert.match(uploadScriptSource, /"thread\/inject_items"|"history": history/);
  assert.match(frontendUploadSkillSource, /codexDelegation\.input/);
  assert.match(frontendUploadSkillSource, /"schemaVersion":2/);
});

test("the handoff skill preserves all prior visible messages exactly", () => {
  assert.match(frontendUploadSkillSource, /Exclude that entire turn only/);
  assert.match(frontendUploadSkillSource, /do not exclude any older turn based on `completed`, `interrupted`, failed, or other status/);
  assert.match(frontendUploadSkillSource, /page\.nextCursor/);
  assert.match(frontendUploadSkillSource, /whenever `page\.hasMore` is true/);
  assert.match(frontendUploadSkillSource, /Reassemble pages and turns oldest-to-newest/);
  assert.match(frontendUploadSkillSource, /keep every `userMessage` and every `agentMessage` exactly once/);
  assert.match(frontendUploadSkillSource, /including progress commentary before a final answer/);
  assert.match(frontendUploadSkillSource, /do not merge, summarize, deduplicate, or replace them with the final answer/);
  assert.match(frontendUploadSkillSource, /never on turn status or `agentMessage\.phase`/);
  assert.match(frontendUploadSkillSource, /compare the JSON message count with the number of eligible `userMessage` and `agentMessage` items/);
  assert.doesNotMatch(frontendUploadSkillSource, /Exclude commentary-only agent messages/);
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
  assert.match(
    dialogSource,
    /type CopyTarget = "install-conversation" \| "install-terminal" \| "handoff" \| ""/,
  );
  assert.match(dialogSource, /\? "install-conversation"[\s\S]*?: "install-terminal"/);
  assert.match(dialogSource, /copy\(handoffPrompt, "handoff"\)/);
  assert.equal(
    dialogSource.match(/className="sandbox-project-upload-stage"/g)?.length,
    2,
  );
  assert.match(
    dialogSource,
    /t\("handoff\.installTitle"\)[\s\S]*?t\("handoff\.taskTitle"\)/,
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

test("the Codex project handoff entry remains in the toolbar only", () => {
  assert.doesNotMatch(myAgentsSource, /本地Codex项目上传/);
  assert.equal(myAgentsSource.match(/t\("myAgents\.handoff"\)/g)?.length, 1);
  assert.match(
    myAgentsStyles,
    /\.my-agent-create-secondary\s*\{[\s\S]*?height:\s*32px[\s\S]*?display:\s*inline-flex/,
  );
  assert.match(
    myAgentsSource,
    /<ResourceCreateCard[\s\S]*?className="my-agent-create-card"/,
  );
  assert.doesNotMatch(myAgentsStyles, /\.my-agent-create-card\s*\{/);
});
