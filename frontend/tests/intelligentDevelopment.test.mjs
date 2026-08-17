import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const require = createRequire(import.meta.url);

async function importTsxBundle(relativePath) {
  const bundled = await build({
    entryPoints: [fileURLToPath(new URL(relativePath, import.meta.url))],
    bundle: true,
    external: ["react"],
    format: "cjs",
    loader: { ".css": "empty" },
    platform: "node",
    write: false,
  });
  const module = { exports: {} };
  Function("require", "module", "exports", bundled.outputFiles[0].text)(
    require,
    module,
    module.exports,
  );
  return module.exports;
}

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
}

globalThis.window = {
  location: {
    search: "",
    pathname: "/",
    hash: "",
    origin: "http://localhost",
  },
  history: { replaceState() {} },
};
globalThis.sessionStorage = memoryStorage();
globalThis.localStorage = memoryStorage();

const result = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/adk/sandbox.ts", import.meta.url)),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(
  result.outputFiles[0].contents,
).toString("base64")}`;
const { intelligentDevelopmentClient, sandboxClient } = await import(moduleUrl);

const sandboxSource = readFileSync(
  new URL("../src/adk/sandbox.ts", import.meta.url),
  "utf8",
);
const blocksSource = readFileSync(
  new URL("../src/blocks.ts", import.meta.url),
  "utf8",
);
const blocksUiSource = readFileSync(
  new URL("../src/ui/Blocks.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const deploymentSource = readFileSync(
  new URL("../src/create/IntelligentDeployment.tsx", import.meta.url),
  "utf8",
);
const deploymentClientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const intelligentReleaseClientSource = readFileSync(
  new URL("../src/adk/intelligentDevelopment.ts", import.meta.url),
  "utf8",
);
const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const createSource = readFileSync(
  new URL("../src/create/IntelligentCreate.tsx", import.meta.url),
  "utf8",
);
const createStyles = readFileSync(
  new URL("../src/create/IntelligentCreate.css", import.meta.url),
  "utf8",
);
const sharedStyles = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);
const sandboxSessionSource = readFileSync(
  new URL("../src/ui/SandboxSession.tsx", import.meta.url),
  "utf8",
);
const sandboxSessionStyles = readFileSync(
  new URL("../src/ui/SandboxSession.css", import.meta.url),
  "utf8",
);
const deliveryIconSource = readFileSync(
  new URL("../src/ui/icons/DeliveryVerifiedIcon.tsx", import.meta.url),
  "utf8",
);
const codeBrowserSource = readFileSync(
  new URL("../src/ui/CodeBrowserDialog.tsx", import.meta.url),
  "utf8",
);
const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);

function sseResponse(frames) {
  return new Response(frames.join("\n\n") + "\n\n", {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

function deliveryEvent(delivery) {
  return [
    "event: development.succeeded",
    `data: ${JSON.stringify({ payload: { delivery } })}`,
  ].join("\n");
}

function sourceReadyEvent(delivery) {
  return [
    "event: development.source_ready",
    `data: ${JSON.stringify({ payload: { delivery } })}`,
  ].join("\n");
}

const delivery = {
  sessionId: "dev/session-1",
  artifactSha256: "a".repeat(64),
  validationReportSha256: "b".repeat(64),
  agentName: "sales-agent",
  entryPoint: "agent.py",
  fileCount: 4,
  artifactSize: 2048,
  validatedAt: "2026-08-14T10:00:00Z",
  gateSummary: ["ruff", "pytest"],
  deployable: true,
  verified: true,
  validationSummary: "云端验证已通过",
};

test("text-only intelligent client uses its fixed endpoint and omits skills", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  const requests = [];
  globalThis.fetch = async (url, init) => {
    requests.push({ url, method: init.method, body: init.body && JSON.parse(init.body) });
    if (url.endsWith("/sessions")) {
      return Response.json({ sessionId: "dev-1", status: "Creating" });
    }
    return sseResponse(["event: delta\ndata: {\"text\":\"ok\"}"]);
  };

  await intelligentDevelopmentClient.startSession({
    displayName: "Build an agent",
    persistent: true,
  });
  await intelligentDevelopmentClient.sendMessage({
    sessionId: "dev/1",
    text: "continue",
    skillIds: ["must-not-leak"],
  });

  assert.deepEqual(requests, [
    {
      url: "/web/intelligent-development/sessions",
      method: "POST",
      body: { displayName: "Build an agent" },
    },
    {
      url: "/web/intelligent-development/sessions/dev%2F1/messages",
      method: "POST",
      body: { message: "continue" },
    },
  ]);
});

test("intelligent reconnect parses the restored conversation snapshot", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  globalThis.fetch = async () => Response.json({
    sessionId: "dev-1",
    status: "Ready",
    toolName: "intelligent-development",
    threadId: "thread-restored",
    conversation: {
      thread: {
        id: "thread-restored",
        preview: "创建销售 Agent",
        cwd: "/home/gem/workspace/project-1",
        modelProvider: "openai",
        createdAt: 1,
        updatedAt: 2,
        status: "idle",
      },
      threadId: "thread-restored",
      messages: [
        {
          id: "message-1",
          role: "user",
          content: "创建销售 Agent",
          timestamp: 1_000,
        },
        {
          id: "message-2",
          role: "assistant",
          content: "已完成",
          timestamp: 2_000,
        },
      ],
      cwd: "/home/gem/workspace/project-1",
      workspaceLocked: true,
      permissions: {
        approvalPolicy: "never",
        approvalsReviewer: "auto_review",
        sandboxMode: "danger-full-access",
        networkAccess: true,
      },
    },
  });

  const connected = await intelligentDevelopmentClient.connectSession("dev-1");

  assert.equal(connected.restoredConversation.threadId, "thread-restored");
  assert.deepEqual(
    connected.restoredConversation.messages.map((message) => message.content),
    ["创建销售 Agent", "已完成"],
  );
});

test("current intelligent release can be absent or restored", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  const { fetchCurrentIntelligentDevelopmentRelease } = await importTsxBundle(
    "../src/adk/intelligentDevelopment.ts",
  );
  globalThis.fetch = async () => new Response(null, { status: 204 });
  assert.equal(
    await fetchCurrentIntelligentDevelopmentRelease("dev-1"),
    null,
  );

  const restoredDelivery = { ...delivery, sessionId: "dev-1", files: [] };
  globalThis.fetch = async () => Response.json(restoredDelivery);
  assert.deepEqual(
    await fetchCurrentIntelligentDevelopmentRelease("dev-1"),
    restoredDelivery,
  );

  globalThis.fetch = async () => Response.json({
    ...restoredDelivery,
    files: undefined,
  });
  await assert.rejects(
    fetchCurrentIntelligentDevelopmentRelease("dev-1"),
    /源码快照的响应格式无效/,
  );
});

test("normal sandbox client keeps the existing endpoint and skill payload", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  let request;
  globalThis.fetch = async (url, init) => {
    request = { url, body: JSON.parse(init.body) };
    return sseResponse(["event: delta\ndata: {\"text\":\"ok\"}"]);
  };

  await sandboxClient.sendMessage({
    sessionId: "sandbox/1",
    text: "use it",
    skillIds: ["skill-1"],
  });

  assert.deepEqual(request, {
    url: "/web/sandbox/sessions/sandbox%2F1/messages",
    body: { message: "use it", skillIds: ["skill-1"] },
  });
});

test("source-ready delivery is upgraded in place only by the verified event", async (t) => {
  const previousFetch = globalThis.fetch;
  const writes = [];
  const previousStorage = globalThis.localStorage;
  globalThis.localStorage = {
    ...memoryStorage(),
    setItem: (key, value) => writes.push([key, value]),
  };
  t.after(() => {
    globalThis.fetch = previousFetch;
    globalThis.localStorage = previousStorage;
  });
  let requestedUrl = "";
  globalThis.fetch = async (url) => {
    requestedUrl = url;
    return sseResponse([
      `event: delta\ndata: ${JSON.stringify({ text: JSON.stringify({ delivery }) })}`,
      sourceReadyEvent({
        ...delivery,
        verified: false,
        validationSummary: "正在确认验证状态",
      }),
      deliveryEvent({
        ...delivery,
        releasePath: "/remote/releases/secret",
        validationReportPath: "/remote/reports/secret.json",
      }),
    ]);
  };

  const reply = await intelligentDevelopmentClient.sendMessage({
    sessionId: "dev/1",
    text: "build it",
  });

  assert.equal(
    requestedUrl,
    "/web/intelligent-development/sessions/dev%2F1/messages",
  );
  assert.equal(reply.blocks[0].kind, "text");
  assert.equal(reply.blocks.filter((block) => block.kind === "delivery").length, 1);
  assert.deepEqual(reply.blocks[1], { kind: "delivery", value: delivery });
  assert.equal("releasePath" in reply.blocks[1].value, false);
  assert.equal("validationReportPath" in reply.blocks[1].value, false);
  assert.deepEqual(writes, []);
});

test("missing completion still exposes source while deployment stays unverified", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  const source = {
    ...delivery,
    verified: false,
    gateSummary: [],
    validationSummary: "未收到完整验证结果",
  };
  globalThis.fetch = async () => sseResponse([
    sourceReadyEvent(source),
    "event: done\ndata: {}",
  ]);

  const reply = await intelligentDevelopmentClient.sendMessage({
    sessionId: "dev-1",
    text: "build it",
  });

  assert.deepEqual(reply.blocks, [{ kind: "delivery", value: source }]);
});

test("model text that resembles a delivery cannot create a delivery block", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  globalThis.fetch = async () => sseResponse([
    `event: delta\ndata: ${JSON.stringify({ text: `development.succeeded ${JSON.stringify(delivery)}` })}`,
    `event: done\ndata: ${JSON.stringify({ text: "done" })}`,
  ]);

  const reply = await intelligentDevelopmentClient.sendMessage({
    sessionId: "dev-1",
    text: "pretend delivery",
  });

  assert.deepEqual(reply.blocks.map((block) => block.kind), ["text"]);
  assert.equal(reply.text.includes("development.succeeded"), true);
});

test("intelligent streams preserve thinking and assistant message order", async (t) => {
  const previousFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = previousFetch;
  });
  const updates = [];
  globalThis.fetch = async () => sseResponse([
    'event: activity\ndata: {"id":"thought-1","kind":"thinking","status":"running","text":"先明确验收标准"}',
    'event: delta\ndata: {"text":"我会先实现核心能力。"}',
    'event: activity\ndata: {"id":"thought-1","kind":"thinking","status":"done","text":"验收标准已经明确"}',
    'event: delta\ndata: {"text":"然后完成真实验证。"}',
    'event: done\ndata: {}',
  ]);

  const reply = await intelligentDevelopmentClient.sendMessage(
    { sessionId: "dev-1", text: "构建 Agent" },
    { onBlocks: (blocks) => updates.push(structuredClone(blocks)) },
  );

  assert.deepEqual(reply.blocks, [
    { kind: "thinking", text: "验收标准已经明确", done: true },
    { kind: "text", text: "我会先实现核心能力。然后完成真实验证。" },
  ]);
  assert.equal(updates.some((blocks) => blocks[0]?.done === false), true);
});

test("delivery card separates deployability from verification", () => {
  const releaseInterface = blocksSource.match(
    /export interface IntelligentDevelopmentReleaseRef \{([\s\S]*?)\n\}/,
  )?.[1] ?? "";
  assert.match(releaseInterface, /files\?: ProjectFile\[\]/);
  assert.match(releaseInterface, /deployable: boolean/);
  assert.match(releaseInterface, /verified: boolean/);
  assert.match(releaseInterface, /validationSummary: string/);
  assert.doesNotMatch(releaseInterface, /releasePath|validationReportPath|url|localStorage/i);
  assert.match(blocksUiSource, /查看源码/);
  assert.match(blocksUiSource, /下载源码/);
  assert.match(blocksUiSource, /手动部署到 Runtime/);
  assert.match(blocksUiSource, /busyAction === "download"/);
  assert.match(
    blocksUiSource,
    /async function download\(\)[\s\S]*?catch[\s\S]*?finally \{[\s\S]*?setBusyAction\(null\)/,
  );
  assert.match(blocksUiSource, /disabled=\{\s*!value\.deployable/);
  assert.match(blocksUiSource, /源码已准备好，可查看、下载或部署/);
  assert.doesNotMatch(blocksUiSource, /验证尚未确认：/);
  assert.match(
    blocksUiSource,
    /value\.verified \? <DeliveryVerifiedIcon \/> : <DeliverySourceIcon \/>/,
  );
  assert.match(blocksUiSource, /<CodeBrowserDialog[\s\S]*?readOnly/);
  assert.match(codeBrowserSource, /readOnly\?: boolean/);
  assert.match(codeBrowserSource, /readOnly=\{readOnly\}/);
  assert.match(appSource, /onDeployDelivery=\{setIntelligentDeployment\}/);
  assert.match(appSource, /onResolveDelivery=\{resolveIntelligentDelivery\}/);
  assert.match(appSource, /onDownloadDelivery=\{downloadIntelligentDelivery\}/);
  assert.match(
    appSource,
    /downloadIntelligentDelivery[\s\S]*?beginAgentSourceDownload[\s\S]*?operation\.succeed[\s\S]*?operation\.fail/,
  );
  assert.match(appSource, /<IntelligentDeployment[\s\S]*?delivery=\{intelligentDeployment\}/);
  assert.match(deploymentSource, /<ProjectPreview/);
  assert.match(deploymentSource, /acknowledgeUnverified: true/);
  assert.match(
    deploymentClientSource,
    /acknowledgeUnverified\?: true/,
  );
  assert.match(deploymentSource, /可部署源码/);
  assert.doesNotMatch(deploymentSource, /部署未完整验证的源码|完整验证尚未确认/);
  assert.doesNotMatch(sharedStyles, /\.trusted-source-pane__badge\.is-warning/);
  assert.match(appSource, /if \(!delivery\.deployable\)/);
  assert.doesNotMatch(appSource, /if \(!delivery\.verified\)/);
  assert.doesNotMatch(deploymentSource, /localStorage|releasePath|validationReportPath/);
});

test("successful intelligent deployment opens a fresh agent chat", () => {
  assert.match(
    projectPreviewSource,
    /await onAgentAdded\(agentId, deployResult\.agentName\)/,
  );
  assert.match(
    appSource,
    /const refreshCurrentAgentAndStartNewChat = async \(id: string\) => \{[\s\S]*?setIntelligentDeployment\(null\);[\s\S]*?startNewChat\(\);[\s\S]*?\};/,
  );
  assert.match(
    appSource,
    /const talkToWorkspaceAgent = async \(agent: AgentEntry\) => \{[\s\S]*?await refreshCurrentAgentAndStartNewChat\(/,
  );
  assert.match(
    appSource,
    /<IntelligentDeployment[\s\S]*?onAgentAdded=\{openIntelligentDeploymentChat\}/,
  );
});

test("delivery card clears browser download handoff feedback", () => {
  assert.match(blocksUiSource, /const DOWNLOAD_STATUS_DURATION_MS = 3_000/);
  assert.match(
    blocksUiSource,
    /busyAction === "download" \? "正在准备…" : "下载源码"/,
  );
  assert.match(
    blocksUiSource,
    /setDownloadStatus\(\{ message: "已开始下载" \}\)/,
  );
  assert.match(
    blocksUiSource,
    /if \(!downloadStatus\) return;[\s\S]*?window\.setTimeout\([\s\S]*?setDownloadStatus\(null\)[\s\S]*?DOWNLOAD_STATUS_DURATION_MS/,
  );
  assert.match(
    blocksUiSource,
    /return \(\) => window\.clearTimeout\(timer\);[\s\S]*?\}, \[downloadStatus\]\)/,
  );
  assert.doesNotMatch(blocksUiSource, /源码 ZIP 已开始下载。/);
});

test("intelligent release client downloads the exact server archive", async () => {
  const { downloadIntelligentDevelopmentRelease } = await importTsxBundle(
    "../src/adk/intelligentDevelopment.ts",
  );
  const originalFetch = globalThis.fetch;
  const archive = Uint8Array.from([0x50, 0x4b, 0x03, 0x04]);
  globalThis.fetch = async (url, options) => {
    const request = new URL(String(url), "http://localhost");
    assert.equal(request.pathname, "/web/intelligent-development/releases/download");
    assert.equal(request.searchParams.get("sessionId"), "dev-1");
    assert.equal(request.searchParams.get("artifactSha256"), "a".repeat(64));
    assert.equal(request.searchParams.get("validationReportSha256"), "b".repeat(64));
    assert.equal(new Headers(options?.headers).get("Accept"), "application/zip");
    return new Response(archive, {
      headers: {
        "Content-Type": "application/zip",
        "Content-Disposition": 'attachment; filename="weather-source-aaaaaaaaaaaa.zip"',
      },
    });
  };
  try {
    const result = await downloadIntelligentDevelopmentRelease({
      sessionId: "dev-1",
      artifactSha256: "a".repeat(64),
      validationReportSha256: "b".repeat(64),
      agentName: "weather",
      entryPoint: "app.py",
      fileCount: 2,
      artifactSize: archive.byteLength,
      validatedAt: "",
      gateSummary: [],
      deployable: true,
      verified: false,
      validationSummary: "验证结果尚未确认",
    });
    assert.equal(result.filename, "weather-source-aaaaaaaaaaaa.zip");
    assert.deepEqual(
      new Uint8Array(await result.blob.arrayBuffer()),
      archive,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("intelligent release requests recover an expired Studio login", () => {
  assert.match(
    intelligentReleaseClientSource,
    /import \{ studioFetch \} from "\.\/client"/,
  );
  assert.equal(
    intelligentReleaseClientSource.match(/await studioFetch\(/g)?.length,
    3,
  );
  assert.doesNotMatch(
    intelligentReleaseClientSource,
    /fetch\(\s*withAuth\(\/web\/intelligent-development\/releases/,
  );
});

test("intelligent release download rejects invalid responses and remains retryable", async () => {
  const { downloadIntelligentDevelopmentRelease } = await importTsxBundle(
    "../src/adk/intelligentDevelopment.ts",
  );
  const originalFetch = globalThis.fetch;
  const candidate = { ...delivery, artifactSize: 3 };
  let call = 0;
  globalThis.fetch = async () => {
    call += 1;
    if (call === 1) {
      return new Response(Uint8Array.from([1, 2, 3]), {
        headers: { "Content-Type": "application/octet-stream" },
      });
    }
    if (call === 2) {
      return new Response(Uint8Array.from([1, 2, 3, 4]), {
        headers: { "Content-Type": "application/zip" },
      });
    }
    if (call === 3) {
      return Response.json({ detail: "交付物已不是当前发布版本。" }, { status: 409 });
    }
    return new Response(Uint8Array.from([1, 2, 3]), {
      headers: { "Content-Type": "application/zip" },
    });
  };
  try {
    await assert.rejects(
      downloadIntelligentDevelopmentRelease(candidate),
      /不是 ZIP 文件/,
    );
    await assert.rejects(
      downloadIntelligentDevelopmentRelease(candidate),
      /大小与发布记录不一致/,
    );
    await assert.rejects(
      downloadIntelligentDevelopmentRelease(candidate),
      /交付物已不是当前发布版本/,
    );
    const result = await downloadIntelligentDevelopmentRelease(candidate);
    assert.equal(
      result.filename,
      `sales-agent-source-${"a".repeat(12)}.zip`,
    );
    assert.equal(result.blob.size, 3);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("trusted deployment previews verified files but never deploys browser file bytes", () => {
  assert.match(
    deploymentSource,
    /const \[project, setProject\] = useState<AgentProject>\(\(\) => \(\{[\s\S]*?name: generateRuntimeName\(delivery\.agentName\),[\s\S]*?files: delivery\.files \?\? \[\]/,
  );
  assert.doesNotMatch(deploymentSource, /EMPTY_FILES/);
  assert.match(deploymentSource, /deployAgentkitProject\([\s\S]*?candidate\.name,\s*\[\],/);
  assert.match(
    deploymentSource,
    /source:\s*\{?[\s\S]*?kind: "intelligentDevelopment"/,
  );
});

test("intelligent goal input shares IME handling and semantic responsive styles", () => {
  assert.match(createSource, /isImeCompositionEvent\(event\.nativeEvent\)/);
  assert.match(createSource, /event\.key === "Enter"[\s\S]*?!event\.shiftKey/);
  assert.match(createStyles, /background: hsl\(var\(--canvas\)\)/);
  assert.match(createStyles, /background: hsl\(var\(--panel\)\)/);
  assert.match(createStyles, /color: hsl\(var\(--foreground\)\)/);
  assert.match(createStyles, /@media \(max-width: 640px\)/);
  assert.match(createStyles, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(sharedStyles, /:root\s*\{[\s\S]*?--canvas:[\s\S]*?--panel:/);
  assert.match(sharedStyles, /\.delivery-card[\s\S]*?hsl\(var\(--border\)\)/);
  assert.match(
    sharedStyles,
    /@media \(max-width: 640px\)[\s\S]*?\.delivery-card-grid[\s\S]*?grid-template-columns: minmax\(0, 1fr\)/,
  );
  assert.doesNotMatch(createSource, /<main className="ic-main"/);
  assert.match(createSource, /className="ic-primary"[\s\S]*?aria-busy=\{creating\}/);
  assert.match(createStyles, /\.ic-root \{[\s\S]*?overflow: hidden/);
  assert.match(createStyles, /\.ic-main \{[\s\S]*?flex: 1[\s\S]*?min-height: 0/);
  assert.match(createStyles, /\.ic-actions > span \{[^}]*font-size: 12px/);
});

test("intelligent preparation acknowledges the goal and exposes cancellable progress", async () => {
  const React = require("react");
  const { renderToStaticMarkup } = require("react-dom/server");
  const { IntelligentCreate } = await importTsxBundle(
    "../src/create/IntelligentCreate.tsx",
  );
  const render = (preparationStage) => renderToStaticMarkup(
    React.createElement(IntelligentCreate, {
      capabilities: { enabled: true, reason: "" },
      loading: false,
      preparationStage,
      error: "",
      onBack() {},
      onCancel() {},
      async onCreate() {},
    }),
  );

  const idle = render(null);
  assert.match(
    appSource,
    /描述目标，按你的意图构建、调试并验证 Agent。/,
  );
  assert.match(
    idle,
    /描述目标后，沙箱中的 Codex 会判断你的意图，完成构建、调试和临时云端验证。/,
  );
  assert.match(
    idle,
    /只需说明 Agent 要解决的问题；如有影响结果的关键信息，会在开始前向你确认。/,
  );
  assert.match(idle, /开发环境最多保留 8 小时，可在当前任务中持续优化。/);
  assert.match(
    idle,
    /placeholder="例如：创建一个能读取销售数据、生成周报并校验输出格式的 Agent"/,
  );
  assert.doesNotMatch(
    createSource,
    /描述目标后，AI|VeADK Agent|开发会话|同一 Thread/,
  );

  const preparing = render("preparing");
  assert.match(preparing, /role="status"/);
  assert.match(preparing, /aria-live="polite"/);
  assert.match(preparing, /目标已收到，马上开始实现/);
  assert.match(preparing, /正在创建任务环境/);
  assert.match(preparing, /接下来会先梳理目标和实现方式，再编写、运行和验证 Agent/);
  assert.match(preparing, />取消</);
  assert.match(preparing, /<textarea[^>]*disabled/);

  const starting = render("starting");
  assert.match(starting, /环境已就绪，正在启动 Codex/);
});

test("intelligent preparation ends before the first build turn and resets on navigation", () => {
  assert.match(
    appSource,
    /function cancelIntelligentPreparation\(\)[\s\S]*?intelligentCreateAbortRef\.current\?\.abort\(\)[\s\S]*?setIntelligentPreparationStage\(null\)/,
  );
  assert.match(
    appSource,
    /function openNewChat\(\)[\s\S]*?cancelIntelligentPreparation\(\)/,
  );
  assert.match(
    appSource,
    /onBack=\{\(\) => \{[\s\S]*?cancelIntelligentPreparation\(\)[\s\S]*?setCreateView\(null\)/,
  );
  assert.match(
    appSource,
    /setIntelligentPreparationStage\("preparing"\)[\s\S]*?startSession\([\s\S]*?setIntelligentPreparationStage\("starting"\)[\s\S]*?connectSession\(/,
  );
  assert.match(
    appSource,
    /setSandboxSession\(connected\)[\s\S]*?setIntelligentPreparationStage\(null\)[\s\S]*?await sendSandboxMessage\(goal, \[\], \[\], connected\)/,
  );
  assert.doesNotMatch(appSource, /function sendIntelligentInitialMessage\(/);
  assert.match(createSource, /const submitDisabled = loading \|\| creating \|\| unavailable \|\| !goal\.trim\(\)/);
  assert.match(appSource, /onCancel=\{cancelIntelligentPreparation\}/);
});

test("intelligent conversation keeps the Studio visual language and stable controls", () => {
  assert.match(
    appSource,
    /sandboxSession\?\.intelligentDevelopment\s*\?\s*" is-intelligent-development"\s*:\s*""/,
  );
  assert.match(
    sandboxSessionStyles,
    /\.main\.is-sandbox-session\.is-intelligent-development \{[^}]*background: hsl\(var\(--panel\)\)/,
  );
  assert.match(
    sandboxSessionStyles,
    /\.main\.is-sandbox-session\.is-intelligent-development::before \{[^}]*display: none/,
  );
  assert.match(
    sandboxSessionStyles,
    /\.sandbox-session-warning\.is-expiring \{[\s\S]*?grid-template-columns: minmax\(0, 1fr\) auto/,
  );
  assert.match(
    sandboxSessionStyles,
    /\.sandbox-session-warning button \{[^}]*white-space: nowrap/,
  );
  assert.match(sandboxSessionSource, /exitLabel = "退出当前智能体"/);
  assert.match(
    sandboxSessionSource,
    /`远端开发环境最长保留 8 小时，将于 \$\{expiryLabel\} 到期（\$\{remaining\}）；到期后清除对话和文件。`/,
  );
  assert.doesNotMatch(sandboxSessionSource, /Thread 与文件/);
  assert.match(
    appSource,
    /exitLabel=\{[\s\S]*?sandboxSession\.intelligentDevelopment[\s\S]*?\? "退出开发环境"[\s\S]*?: undefined[\s\S]*?\}/,
  );
});

test("intelligent builds join history and restore conversation plus delivery", () => {
  assert.match(appSource, /const \[intelligentSessions, setIntelligentSessions\]/);
  assert.match(
    appSource,
    /intelligentDevelopmentClient\.listSessions\([\s\S]*?setIntelligentSessions/,
  );
  assert.match(
    appSource,
    /setIntelligentSessions\(\(current\) =>[\s\S]*?created/,
  );
  assert.match(sidebarSource, /intelligentHistory\?: SidebarIntelligentHistory/);
  assert.match(
    sidebarSource,
    /kind: "intelligent"[\s\S]*?createdAt[\s\S]*?sort/,
  );
  assert.match(
    appSource,
    /async function openIntelligentDevelopmentSession[\s\S]*?connectSession\([\s\S]*?restoredConversation[\s\S]*?sandboxSnapshotTurns/,
  );
  assert.match(
    appSource,
    /intelligentOpenAbortRef\.current\?\.abort\(\)[\s\S]*?connectSession\([\s\S]*?signal: controller\.signal/,
  );
  assert.match(
    appSource,
    /fetchCurrentIntelligentDevelopmentRelease\([\s\S]*?appendIntelligentDelivery/,
  );
  assert.match(
    appSource,
    /function requestIntelligentNavigation[\s\S]*?sandboxSession\?\.intelligentDevelopment && sandboxBusy[\s\S]*?setIntelligentLeaveOpen\(true\)/,
  );
  assert.match(appSource, /离开将停止本轮构建；当前会话仍会保留，可稍后从历史会话重新进入。/);
  assert.match(appSource, /title="删除构建会话"[\s\S]*?删除后无法恢复/);
  assert.match(
    appSource,
    /deleteSession\(session\.id\)[\s\S]*?exitSandboxSession\(false\)/,
  );
  assert.match(
    sidebarSource,
    /!intelligentHistory\?\.error[\s\S]*?combinedHistory\.length === 0/,
  );
});

test("verified delivery uses repository-owned visuals and user-facing copy", () => {
  assert.match(deliveryIconSource, /export function DeliveryVerifiedIcon/);
  assert.match(deliveryIconSource, /viewBox="0 0 24 24"/);
  assert.match(deliveryIconSource, /aria-hidden="true"/);
  assert.doesNotMatch(deliveryIconSource, /lucide-react|<img|data:image/);
  assert.match(blocksUiSource, /<DeliveryVerifiedIcon \/>/);
  assert.match(blocksUiSource, /<dt>文件数<\/dt>/);
  assert.match(blocksUiSource, /项检查通过/);
});

// Keep the construction under test explicit: intelligent mode is configured once,
// while the normal client remains the unchanged default.
test("client exports remain separately configured", () => {
  assert.match(sandboxSource, /export const sandboxClient = createSandboxClient\(SANDBOX_API\)/);
  assert.match(
    sandboxSource,
    /export const intelligentDevelopmentClient = createSandboxClient\(\s*"\/web\/intelligent-development\/sessions",\s*\{[\s\S]*?textOnly: true,[\s\S]*?messageTimeoutMs: 3_600_000,[\s\S]*?interruptTimeoutMs: 45_000/,
  );
  assert.doesNotMatch(sandboxSource, /verifyDelivery\(/);
  assert.doesNotMatch(appSource, /验证并生成交付物|verifyIntelligentDevelopment/);
  assert.match(
    appSource,
    /!sandboxSession\?\.intelligentDevelopment\s*&&\s*await sandboxCommands\.executeSlash\(value\)/,
  );
});
