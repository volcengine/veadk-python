import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

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

test("the automatic message stream accepts only a typed delivery event", async (t) => {
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

test("delivery reference and CTA stay browser-safe and open the shared deploy UI", () => {
  const releaseInterface = blocksSource.match(
    /export interface IntelligentDevelopmentReleaseRef \{([\s\S]*?)\n\}/,
  )?.[1] ?? "";
  assert.doesNotMatch(releaseInterface, /path|url|localStorage/i);
  assert.match(blocksUiSource, /onClick=\{\(\) => onDeploy\?\.\(value\)\}/);
  assert.match(blocksUiSource, /手动部署到 Runtime/);
  assert.match(appSource, /onDeployDelivery=\{setIntelligentDeployment\}/);
  assert.match(appSource, /<IntelligentDeployment[\s\S]*?delivery=\{intelligentDeployment\}/);
  assert.match(deploymentSource, /<ProjectPreview/);
  assert.doesNotMatch(deploymentSource, /localStorage|releasePath|validationReportPath/);
});

test("trusted deployment sends no browser files and generates its Runtime name once", () => {
  assert.match(
    deploymentSource,
    /const \[project, setProject\] = useState<AgentProject>\(\(\) => \(\{[\s\S]*?name: generateRuntimeName\(delivery\.agentName\),[\s\S]*?files: EMPTY_FILES/,
  );
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
});

// Keep the construction under test explicit: intelligent mode is configured once,
// while the normal client remains the unchanged default.
test("client exports remain separately configured", () => {
  assert.match(sandboxSource, /export const sandboxClient = createSandboxClient\(SANDBOX_API\)/);
  assert.match(
    sandboxSource,
    /export const intelligentDevelopmentClient = createSandboxClient\(\s*"\/web\/intelligent-development\/sessions",\s*\{ textOnly: true, messageTimeoutMs: 3_600_000 \}/,
  );
  assert.doesNotMatch(sandboxSource, /verifyDelivery\(/);
  assert.doesNotMatch(appSource, /验证并生成交付物|verifyIntelligentDevelopment/);
  assert.match(
    appSource,
    /!sandboxSession\?\.intelligentDevelopment\s*&&\s*await sandboxCommands\.executeSlash\(value\)/,
  );
});
