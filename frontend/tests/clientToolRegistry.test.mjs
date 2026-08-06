import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const registrySource = readFileSync(
  new URL("../src/client-tools/registry.ts", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const composerSource = readFileSync(
  new URL("../src/ui/Composer.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

const registryBuild = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/client-tools/registry.ts", import.meta.url)),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const registryModule = await import(
  `data:text/javascript;base64,${Buffer.from(registryBuild.outputFiles[0].contents).toString("base64")}`
);

test("declares Janus as the first generic read-only client tool provider", () => {
  assert.match(registrySource, /id: "janus"/);
  assert.match(registrySource, /name: "read_browser_context"/);
  assert.match(registrySource, /input_schema:/);
  assert.match(registrySource, /enum: \["list_tabs", "read_page", "bookmarks"\]/);
  assert.match(registrySource, /probe: probeJanusBrowserContext/);
  assert.match(registrySource, /execute: executeJanusBrowserTool/);
  assert.match(registrySource, /only when both conditions apply/);
  assert.match(registrySource, /answer may exist in the user's browser data/);
  assert.match(registrySource, /untrusted reference material/);
});

test("declares Studio media fallbacks in the generic client tool catalog", () => {
  assert.match(registrySource, /id: "studio-media"/);
  assert.match(registrySource, /probe: probeStudioClientTools/);
  for (const name of [
    "ppt_generate",
    "image_generate",
    "image_edit",
    "video_generate",
    "video_task_query",
  ]) {
    assert.match(registrySource, new RegExp(`name: "${name}"[\\s\\S]*?nativeToolNames: \\["${name}"\\]`));
  }
});

test("filters a client tool already mounted natively", () => {
  assert.match(registrySource, /nativeToolNames\?: readonly string\[\]/);
  assert.match(registrySource, /nativeToolNames\.has\(nativeName\)/);
  assert.match(appSource, /agentInfo\?\.tools/);
  assert.match(appSource, /sessionCapabilities\?\.tools/);
  assert.match(
    appSource,
    /availableClientTools\(clientToolAvailability, nativeToolNames\)/,
  );
});

test("does not mount the Janus fallback over a native tool", () => {
  assert.deepEqual(
    registryModule.availableClientTools(
      [{ providerId: "janus", available: true }],
      new Set(["read_browser_context"]),
    ),
    [],
  );
  const tools = registryModule.availableClientTools(
    [{ providerId: "janus", available: true }],
    new Set(["image_generate", "video_task_query"]),
  );
  assert.deepEqual(tools.map((tool) => tool.name), ["read_browser_context"]);
});

test("mounts only Studio media tools missing from the Runtime", () => {
  const tools = registryModule.availableClientTools(
    [{ providerId: "studio-media", available: true }],
    new Set(["image_generate", "video_task_query"]),
  );
  assert.deepEqual(tools.map((tool) => tool.name), [
    "ppt_generate",
    "image_edit",
    "video_generate",
  ]);
});

test("serializes available client tools through client_tools v1", () => {
  assert.match(clientSource, /clientTools\?: readonly ClientToolDeclaration\[\]/);
  assert.match(clientSource, /client_tools: clientTools\.length > 0 \? clientTools : undefined/);
  assert.doesNotMatch(clientSource, /browser_context_available|browserContextAvailable/);
});

test("executes only registered active client tool calls and resumes the Runtime", () => {
  assert.match(appSource, /function pendingClientToolCalls/);
  assert.match(appSource, /activeToolNames\.has\(call\.name\)/);
  assert.match(appSource, /isRegisteredClientTool\(call\.name\)/);
  assert.match(appSource, /executeClientTool\(call\.name, call\.args\)/);
  assert.match(appSource, /name: call\.name/);
});

test("shows provider status only after local and Runtime protocol probes pass", () => {
  assert.match(appSource, /probeClientToolProviders\(\)/);
  assert.match(appSource, /probeRuntimeClientToolsSupport/);
  assert.match(appSource, /newChatCapabilities\.clientToolsEnabled === true/);
  assert.match(appSource, /availableClientToolStatuses\(clientToolAvailability\)/);
  assert.match(composerSource, /clientToolStatuses\.map\(\(status\) =>/);
  assert.match(composerSource, /\{status\.label\}/);
  assert.match(
    composerSource,
    /<span>回答仅供参考<\/span>[\s\S]*?className="composer-client-tool-status-group"[\s\S]*?className="composer-meta-separator"[\s\S]*?className="composer-client-tool-status"/,
  );
  assert.match(
    stylesSource,
    /\.composer-meta\s*\{[^}]*gap:\s*8px/,
  );
  assert.match(
    stylesSource,
    /\.composer-client-tool-status-group\s*\{[^}]*gap:\s*8px/,
  );
});
