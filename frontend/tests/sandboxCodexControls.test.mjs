import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const appSource = source("../src/App.tsx");
const blocksSource = source("../src/blocks.ts");
const composerSource = source("../src/ui/SandboxComposer.tsx");
const controlsSource = source("../src/ui/SandboxControls.tsx");
const sidebarSource = source("../src/ui/Sidebar.tsx");
const commandHookSource = source("../src/ui/useSandboxCodexCommands.ts");
const confirmDialogSource = source("../src/ui/StudioConfirmDialog.tsx");
const commandsSource = source("../src/ui/sandboxCommands.ts");
const controlIconsSource = source("../src/ui/icons/SandboxControlIcons.tsx");
const sessionStylesSource = source("../src/ui/SandboxSession.css");

test("Codex sessions use the dedicated composer and expose sandbox tools", () => {
  assert.match(appSource, /<SandboxComposer/);
  assert.match(composerSource, /上传图片/);
  assert.match(composerSource, /上传文档或 PDF/);
  assert.match(composerSource, /actions\.onOpenTerminal\(\)/);
  assert.match(composerSource, /actions\.onOpenBrowser\(\)/);
  assert.match(composerSource, /actions\.onOpenPermissions/);
  assert.match(composerSource, /actions\.onOpenWorkspace/);
});

test("Codex commands and Skills are wired through the current session", () => {
  for (const command of [
    "model", "models", "skill", "skills", "new", "resume", "fork",
    "compact", "archive", "status", "clear", "help",
  ]) {
    assert.match(commandsSource, new RegExp(`name: "${command}"`));
  }
  assert.match(appSource, /useSandboxCodexCommands\(/);
  assert.match(appSource, /skillIds: selectedSkills\.map/);
  assert.match(composerSource, /aria-label=\{menuLabel\}/);
  assert.match(composerSource, /isImeCompositionEvent/);
  assert.match(composerSource, /className="composer-input-stack sandbox-composer-input"/);
  assert.match(composerSource, /skillPrefix="\$"/);
  assert.doesNotMatch(composerSource, /onSubmit\(`\/\$\{item\.command\.name\}`\)/);
  assert.match(composerSource, /updateValue\(`\/\$\{item\.command\.name\}`\)/);
  assert.match(composerSource, /updateValue\(`\/model \$\{item\.model\.id\}`\)/);
  assert.match(commandsSource, /label: model\.id === currentModel \? "当前模型" : "可用模型"/);
  assert.match(commandsSource, /displayName !== model\.id/);
  assert.match(composerSource, /index === activeIndex \? <kbd>↵<\/kbd> : null/);
  assert.doesNotMatch(composerSource, /<kbd>\{index === activeIndex \? "↵" : ""\}<\/kbd>/);
  assert.match(
    sessionStylesSource,
    /\.sandbox-composer-input > \.comp-input\s*\{[^}]*min-height:\s*28px[^}]*padding:\s*4px 0[^}]*line-height:\s*20px/,
  );
});

test("active Codex Sandbox threads replace normal history in the Sidebar", () => {
  assert.match(sidebarSource, /export interface SidebarSandboxHistory/);
  assert.match(sidebarSource, /sandboxHistory\?: SidebarSandboxHistory/);
  assert.match(sidebarSource, /sandboxHistory \? \(/);
  assert.match(sidebarSource, /sandboxHistory\.threads\.map/);
  assert.match(sidebarSource, /sandboxHistory\.currentThreadId/);
  assert.match(sidebarSource, /onNew: \(\) => void/);
  assert.match(sidebarSource, /newDisabled: boolean/);
  assert.match(sidebarSource, /sandboxHistory\?\.onNew \?\? onNewChat/);
  assert.match(sidebarSource, /disabled=\{sandboxHistory\?\.newDisabled\}/);
  assert.match(sidebarSource, /sandboxHistory\.onSelect\(thread\.id\)/);
  assert.match(sidebarSource, /sandboxHistory\.onDelete\(thread\)/);
  assert.match(sidebarSource, /sandboxHistory\.onLoadMore/);
  assert.match(sidebarSource, /加载更多/);
  assert.match(sidebarSource, /role="alert"/);
  assert.match(commandHookSource, /const \[threadsNextCursor, setThreadsNextCursor\]/);
  assert.match(commandHookSource, /loadMoreThreads/);
  assert.match(commandHookSource, /async function newThread\(\)/);
  assert.match(commandHookSource, /requestNewThread/);
  assert.match(commandHookSource, /deleteThread/);
  assert.match(commandHookSource, /client\.deleteThread/);
  assert.match(commandHookSource, /threadsRequestRef\.current \+= 1/);
  assert.match(commandHookSource, /threadsAbortRef\.current\?\.abort\(\)/);
  assert.match(
    commandHookSource,
    /client\.listThreads\([\s\S]*?signal: controller\.signal/,
  );
  assert.match(appSource, /void sandboxCommands\.refreshThreads\(\)/);
  assert.match(appSource, /sandboxHistory=\{sandboxSession/);
  assert.match(appSource, /onNew: \(\) => void sandboxCommands\.newThread\(\)/);
  assert.match(appSource, /newDisabled: sandboxBusy \|\| sandboxCommands\.commandBusy/);
  assert.match(appSource, /<StudioConfirmDialog/);
  assert.match(appSource, /删除 Codex 历史会话/);
  assert.match(confirmDialogSource, /role="alertdialog"/);
});

test("a running handoff session is opened with live busy-state recovery", () => {
  assert.match(appSource, /setSandboxBusy\(connected\.busy\)/);
  assert.match(appSource, /sandboxSnapshotTurnsForStatus\(snapshot, connected\.busy\)/);
  assert.match(
    appSource,
    /const backgroundClient = activeSession\.intelligentDevelopment[\s\S]*?intelligentDevelopmentClient[\s\S]*?: sandboxClient/,
  );
  assert.match(appSource, /backgroundClient\.getStatus\(activeSession\.id/);
  assert.match(appSource, /backgroundClient\.readThread\(activeSession\.id, status\.threadId/);
  assert.match(appSource, /setSandboxBusy\(status\.busy\)/);
  assert.match(appSource, /window\.setTimeout\(syncBackgroundTurn, 1500\)/);
});

test("Codex token usage and approvals are presented per assistant turn", () => {
  assert.match(blocksSource, /sandboxUsage\?: SandboxTokenUsage/);
  assert.match(appSource, /onUsage: \(update\) =>/);
  assert.match(appSource, /<SandboxTokenUsageRow/);
  assert.match(appSource, /onApproval: \(approval\) =>/);
  assert.match(appSource, /<SandboxApprovalDialog/);
  assert.match(controlsSource, /title="Codex 权限"/);
  assert.match(controlsSource, /保存权限/);
});

test("Codex image attachments keep their preview until the transcript is cleared", () => {
  assert.match(blocksSource, /previewUrl\?: string/);
  assert.match(
    appSource,
    /files: readyAttachments\.map[\s\S]*?previewUrl: attachment\.previewUrl/,
  );
  assert.match(appSource, /sandboxPreviewUrlsRef/);
  assert.match(appSource, /releaseAllSandboxPreviews\(\)/);
  assert.doesNotMatch(appSource, /releaseAttachmentPreviews\(messageAttachments\)/);
});

test("sandbox dialogs provide explicit loading error and keyboard states", () => {
  assert.match(controlsSource, /role="dialog"/);
  assert.match(controlsSource, /if \(event\.key === "Escape"\)/);
  assert.match(controlsSource, /打开失败/);
  assert.match(controlsSource, /重试/);
  assert.match(controlsSource, /disabled=\{busy/);
  assert.match(controlsSource, /previousFocusRef\.current\?\.focus\(\)/);
  assert.match(controlsSource, /role="radiogroup"/);
  assert.match(controlsSource, /role="radio"/);
  assert.match(controlsSource, /event\.key === "ArrowRight"/);
});

test("new sandbox product icons are repository-owned SVG components", () => {
  assert.doesNotMatch(composerSource, /lucide-react/);
  assert.doesNotMatch(controlsSource, /lucide-react/);
  assert.doesNotMatch(controlIconsSource, /lucide-react|<img|data:image/);
  assert.match(controlIconsSource, /export function SandboxTerminalIcon/);
  assert.match(controlIconsSource, /export function SandboxPermissionsIcon/);
  assert.match(controlIconsSource, /viewBox="0 0 24 24"/);
});
