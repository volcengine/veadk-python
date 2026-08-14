import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";
import { readFileSync } from "node:fs";

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const agentSelectorSource = readFileSync(
  new URL("../src/ui/AgentSelector.tsx", import.meta.url),
  "utf8",
);
const projectPreviewSource = readFileSync(
  new URL("../src/ui/ProjectPreview.tsx", import.meta.url),
  "utf8",
);
const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const feishuIntegrationSource = readFileSync(
  new URL(
    "../src/automations/feishu/FeishuBotIntegration.tsx",
    import.meta.url,
  ),
  "utf8",
);
const adkClientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);

const result = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/telemetry/runtime.ts", import.meta.url)),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(result.outputFiles[0].contents).toString("base64")}`;
const { TelemetryRuntime } = await import(moduleUrl);

const privacyResult = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/telemetry/privacy.ts", import.meta.url)),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const privacyModuleUrl = `data:text/javascript;base64,${Buffer.from(privacyResult.outputFiles[0].contents).toString("base64")}`;
const { classifyTelemetryError } = await import(privacyModuleUrl);

const clientResult = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/telemetry/client.ts", import.meta.url)),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const clientModuleUrl = `data:text/javascript;base64,${Buffer.from(clientResult.outputFiles[0].contents).toString("base64")}`;
const { TeaClient } = await import(clientModuleUrl);

function harness() {
  const events = [];
  const identities = [];
  let id = 0;
  let now = 100;
  const runtime = new TelemetryRuntime({
    sink: {
      emit(name, payload) {
        events.push({ name, payload });
      },
      identify(userUniqueId) {
        identities.push(userUniqueId);
      },
    },
    createId: () => `id-${++id}`,
    now: () => now,
  });
  runtime.setContext({
    userPoolId: "pool-1",
    studioDeployId: "deploy-1",
    applicationId: "app-1",
    functionId: "function-1",
    studioRegion: "cn-beijing",
    studioProject: "studio",
    studioVersion: "1.2.3",
    environment: "staging",
    cloudProvider: "volcengine",
    accountId: "2100123456",
  });
  runtime.identify({
    userUniqueId: " user-1 ",
    accountId: " 2100123456 ",
    userRole: "member",
    userSource: "sso",
  });
  return {
    events,
    identities,
    runtime,
    setNow(value) {
      now = value;
    },
  };
}

test("bootstraps the documented TEA queue and flushes pre-init events", async () => {
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const scripts = [];
  globalThis.window = {};
  globalThis.document = {
    createElement: () => ({}),
    head: {
      appendChild: (script) => scripts.push(script),
    },
  };

  try {
    const client = new TeaClient();
    client.identify("user-1");
    const initializing = client.init({ enabled: true, environment: "prod" });
    client.emit("studio_session_started", { event_id: "queued-event" });
    await initializing;

    const calls = globalThis.window.collectEvent.q.map((args) =>
      Array.from(args)
    );
    assert.equal(globalThis.window.LogAnalyticsObject, "collectEvent");
    assert.equal(typeof globalThis.window.collectEvent.l, "number");
    assert.equal(scripts.length, 1);
    assert.match(scripts[0].src, /lf-static\.applogcdn\.com/);
    assert.deepEqual(calls.map(([command]) => command), [
      "init",
      "config",
      "config",
      "start",
      "studio_session_started",
    ]);
    assert.deepEqual(calls[0][1], {
      app_id: 1050062,
      channel: "cn",
      disable_auto_pv: 1,
    });
    assert.deepEqual(calls[1][1], { user_unique_id: "user-1" });
    assert.deepEqual(calls[2][1], { _staging_flag: 0 });
    assert.deepEqual(calls[4][1], { event_id: "queued-event" });

    const liveCalls = [];
    globalThis.window.collectEvent = (...args) => liveCalls.push(args);
    client.identify("user-2");
    client.emit("studio_session_started", { event_id: "live-event" });
    assert.deepEqual(liveCalls, [
      ["config", { user_unique_id: "user-2" }],
      ["studio_session_started", { event_id: "live-event" }],
    ]);
  } finally {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
});

test("records one anonymous Studio page entry before login", () => {
  const { events, runtime } = harness();
  runtime.trackStudioEntryViewed({ authState: "anonymous" });
  runtime.trackStudioEntryViewed({ authState: "anonymous" });

  assert.equal(events.length, 1);
  assert.equal(events[0].name, "studio_entry_viewed");
  assert.equal(events[0].payload.auth_state, "anonymous");
  assert.equal(events[0].payload.cloud_provider, "volcengine");
  assert.equal(events[0].payload.account_id, "2100123456");
  assert.equal(events[0].payload.page_instance_id, "id-1");
  assert.equal("user_role" in events[0].payload, false);
  assert.equal("user_source" in events[0].payload, false);
  assert.equal("agents_source" in events[0].payload, false);
});

test("records one authenticated page-ready Studio visit, not an Agent chat session", () => {
  const { events, identities, runtime } = harness();
  runtime.trackStudioSessionStarted({ agentsSource: "cloud" });
  runtime.trackStudioSessionStarted({ agentsSource: "local" });

  assert.deepEqual(identities, ["user-1"]);
  assert.equal(events.length, 1);
  assert.equal(events[0].name, "studio_session_started");
  assert.equal(events[0].payload.agents_source, "cloud");
  assert.equal("user_unique_id" in events[0].payload, false);
  assert.equal("auth_session_id" in events[0].payload, false);
  assert.equal(events[0].payload.cloud_provider, "volcengine");
  assert.equal(events[0].payload.account_id, "2100123456");
  assert.equal(events[0].payload.page_instance_id, "id-1");
  assert.equal("session_id" in events[0].payload, false);
});

test("links started and terminal events while making the terminal idempotent", () => {
  const { events, runtime, setNow } = harness();
  const operation = runtime.beginAgentDeploy({
    agentId: "agent-1",
    deployAction: "create",
    deploySource: "scratch",
    createMode: "custom",
    aiAssisted: 0,
    deployRegion: "cn-beijing",
    runtimeNetworkType: "public",
    feishuEnabled: 1,
  });
  setNow(175);
  operation.succeed({ runtimeId: "runtime-1" });
  operation.fail({ failedPhase: "deploy", errorKind: "server" });

  assert.equal(events.length, 2);
  assert.deepEqual(events.map(({ payload }) => payload.status), [
    "started",
    "succeeded",
  ]);
  assert.equal(events[0].payload.operation_id, operation.operationId);
  assert.equal(events[1].payload.operation_id, operation.operationId);
  assert.notEqual(events[0].payload.event_id, events[1].payload.event_id);
  assert.equal(events[1].payload.duration_ms, 75);
  assert.equal(events[1].payload.runtime_id, "runtime-1");
});

test("provides all six typed operation event families", () => {
  const { events, runtime } = harness();
  runtime.beginSandboxCreate({
    sandboxKind: "codex",
    sandboxSource: "new_chat",
  }).succeed({ sandboxId: "sandbox-1" });
  runtime.beginAgentDebug({
    agentId: "agent-1",
    variantType: "baseline",
  }).fail({ failedPhase: "create_test_run", errorKind: "server" });
  runtime.beginAgentConnect({
    targetId: "runtime-1",
    agentKind: "runtime",
    connectSource: "my_agents",
  }).succeed({ runtimeRegion: "cn-beijing", runtimeIsMine: 1 });
  runtime.beginAgentMessage({
    agentId: "agent-1",
    agentKind: "runtime",
    messageSource: "composer",
    sessionState: "new",
  }).succeed({ sessionId: "agent-chat-session-1" });
  runtime.beginAgentSourceDownload({
    agentId: "agent-1",
    deployAction: "create",
    deploySource: "scratch",
    createMode: "custom",
    aiAssisted: 0,
  }).succeed({ fileCount: 3, zipSizeBytes: 1024 });

  assert.deepEqual(new Set(events.map(({ name }) => name)), new Set([
    "studio_sandbox_create",
    "studio_agent_debug",
    "studio_agent_connect",
    "studio_agent_message",
    "studio_agent_source_download",
  ]));
  const messageTerminal = events.find(
    ({ name, payload }) =>
      name === "studio_agent_message" && payload.status === "succeeded",
  );
  assert.equal(messageTerminal.payload.session_id, "agent-chat-session-1");
});

test("starts each Studio operation at its business boundary", () => {
  assert.match(appSource, /trackStudioSessionStarted\(\{ agentsSource \}\)/);
  assert.match(appSource, /const operation = beginSandboxCreate\(/);
  assert.match(appSource, /const operation = beginAgentConnect\(/);
  assert.match(appSource, /const messageOperation = currentRuntime[\s\S]*beginAgentMessage\(/);
  assert.match(agentSelectorSource, /const operation = beginAgentConnect\(/);
  assert.match(projectPreviewSource, /const operation = beginAgentDeploy\(/);
  assert.match(projectPreviewSource, /const operation = beginAgentSourceDownload\(/);
  assert.match(customCreateSource, /const operation = beginAgentDebug\(/);
  assert.match(feishuIntegrationSource, /const operation = beginAgentDeploy\(/);

  for (const source of [
    appSource,
    agentSelectorSource,
    projectPreviewSource,
    customCreateSource,
    feishuIntegrationSource,
  ]) {
    assert.doesNotMatch(source, /adk\/telemetry(?:Events|Classifiers)?/);
    assert.doesNotMatch(source, /error_summary/);
  }
});

test("drops unknown, nested, non-finite, and sensitive content fields", () => {
  const { events, runtime } = harness();
  const props = {
    agentId: "agent-1",
    agentKind: "runtime",
    messageSource: "composer",
    sessionState: "existing",
    sessionId: "chat-1",
    prompt: "secret prompt",
    message: "secret message",
    response: "secret response",
    error_summary: "token=secret",
    nested: { unsafe: true },
    invalid_number: Number.NaN,
  };
  runtime.beginAgentMessage(props).fail({
    sessionId: "chat-1",
    failedPhase: "run_sse",
    errorKind: "server",
    error_summary: "password=secret",
  });

  for (const { payload } of events) {
    assert.equal("prompt" in payload, false);
    assert.equal("message" in payload, false);
    assert.equal("response" in payload, false);
    assert.equal("error_summary" in payload, false);
    assert.equal("nested" in payload, false);
    assert.equal("invalid_number" in payload, false);
    assert.ok(Object.values(payload).every(
      (value) => typeof value === "string" || typeof value === "number",
    ));
  }
});

test("classifies only approved stable error categories without error text", () => {
  assert.deepEqual(
    classifyTelemetryError(new Error("secret"), { phase: "build" }),
    { errorKind: "build_failed" },
  );
  assert.deepEqual(
    classifyTelemetryError({ name: "AbortError" }, { phase: "build" }),
    { errorKind: "abort" },
  );
  assert.deepEqual(
    classifyTelemetryError({ name: "RuntimeAccessDeniedError" }),
    { errorKind: "auth" },
  );
  assert.deepEqual(classifyTelemetryError({
    name: "RuntimeProbeError",
    message: "sensitive runtime URL",
  }), { errorKind: "runtime_probe_error" });
  assert.deepEqual(classifyTelemetryError({ status: 403, message: "secret" }), {
    errorKind: "auth",
    errorCode: "403",
  });
  assert.deepEqual(classifyTelemetryError({
    name: "ArbitraryInternalName",
    message: "token=secret",
  }), { errorKind: "unknown" });
});

test("does not record a Studio page visit before identity is confirmed", () => {
  const events = [];
  const runtime = new TelemetryRuntime({
    sink: { emit: (name, payload) => events.push({ name, payload }) },
    createId: () => "id",
    now: () => 0,
  });
  runtime.setContext({
    userPoolId: "pool",
    studioDeployId: "deploy",
    applicationId: "app",
    functionId: "function",
    studioRegion: "cn-beijing",
    studioProject: "studio",
    studioVersion: "1",
    environment: "prod",
    cloudProvider: "byteplus",
  });
  runtime.trackStudioSessionStarted({ agentsSource: "cloud" });
  assert.deepEqual(events, []);
});

test("does not emit an orphan operation terminal if begin happened before identity", () => {
  const events = [];
  const runtime = new TelemetryRuntime({
    sink: { emit: (name, payload) => events.push({ name, payload }) },
    createId: () => "id",
    now: () => 0,
  });
  const operation = runtime.beginSandboxCreate({
    sandboxKind: "codex",
    sandboxSource: "new_chat",
  });
  runtime.identify({
    userUniqueId: "user",
    userRole: "member",
    userSource: "sso",
  });
  operation.succeed({ sandboxId: "sandbox" });
  assert.deepEqual(events, []);
});

test("starts a new Studio visit when the authenticated user changes", () => {
  const { events, runtime } = harness();
  runtime.trackStudioSessionStarted({ agentsSource: "cloud" });
  runtime.identify({
    userUniqueId: "user-2",
    userRole: "member",
    userSource: "sso",
  });
  runtime.trackStudioSessionStarted({ agentsSource: "cloud" });

  assert.equal(events.length, 2);
  assert.notEqual(
    events[0].payload.page_instance_id,
    events[1].payload.page_instance_id,
  );
});

test("uses one domestic TEA application for all Studio deployments", async () => {
  const schemaSource = await import("node:fs").then(({ readFileSync }) =>
    readFileSync(new URL("../src/telemetry/schema.ts", import.meta.url), "utf8"),
  );
  const clientSource = await import("node:fs").then(({ readFileSync }) =>
    readFileSync(new URL("../src/telemetry/client.ts", import.meta.url), "utf8"),
  );
  assert.match(schemaSource, /TEA_APP_ID = 1050062/);
  assert.match(schemaSource, /TELEMETRY_SCHEMA_VERSION = "1\.0"/);
  assert.match(clientSource, /lf-static\.applogcdn\.com/);
  assert.match(clientSource, /channel: "cn"/);
  assert.match(clientSource, /LogAnalyticsObject = "collectEvent"/);
  assert.match(clientSource, /collector\.q = \[\]/);
  assert.match(clientSource, /collector\.l = Date\.now\(\)/);
  assert.doesNotMatch(clientSource, /lf-global-static|sg_central/);
  assert.doesNotMatch(
    adkClientSource,
    /StudioTelemetryApmplusConfig|provider\?: "apmplus"|apmplus\?:/,
  );
  assert.doesNotMatch(adkClientSource, /apmplus\.(?:aid|token)/);
  assert.match(
    adkClientSource,
    /config\.enabled !== true[\s\S]*!config\.studio[\s\S]*typeof config\.studio !== "object"/,
  );
});
