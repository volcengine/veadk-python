import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const registrySource = readFileSync(
  new URL("../src/automations/registry.ts", import.meta.url),
  "utf8",
);
const typesSource = readFileSync(
  new URL("../src/automations/types.ts", import.meta.url),
  "utf8",
);
const applicationsSource = readFileSync(
  new URL("../src/ui/Applications.tsx", import.meta.url),
  "utf8",
);
const applicationsStyles = readFileSync(
  new URL("../src/ui/Applications.css", import.meta.url),
  "utf8",
);
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const definitionSource = readFileSync(
  new URL("../src/automations/codingAgents.ts", import.meta.url),
  "utf8",
);
const integrationSource = readFileSync(
  new URL("../src/automations/coding-agents/CodingAgentsIntegration.tsx", import.meta.url),
  "utf8",
);
const integrationStyles = readFileSync(
  new URL("../src/automations/coding-agents/CodingAgentsIntegration.css", import.meta.url),
  "utf8",
);

async function loadTypeScriptModule(relativePath) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(relativePath, import.meta.url))],
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node20",
    write: false,
  });
  const source = Buffer.from(result.outputFiles[0].contents).toString("base64");
  return import(`data:text/javascript;base64,${source}`);
}

test("registers Coding Agents as a local configuration automation", () => {
  assert.match(typesSource, /\| "coding-agents"/);
  assert.match(typesSource, /kind: "coding-agent"/);
  assert.match(typesSource, /badgeTone\?: "default" \| "success"/);
  assert.match(registrySource, /codingAgentsAutomation/);
  assert.match(definitionSource, /name: "配置 Coding Agents"/);
  assert.match(definitionSource, /badgeTone: "success"/);
  assert.match(applicationsSource, /application\.badgeTone/);
  assert.match(applicationsStyles, /application-card-badge\.is-success/);
  assert.match(appSource, /applicationsView === "coding-agents"/);
  assert.match(appSource, /<CodingAgentsIntegration/);
});

test("only enables Coding Agents configuration on 127.0.0.1", async () => {
  const { isCodingAgentsAutomationAvailable } = await loadTypeScriptModule(
    "../src/automations/codingAgents.ts",
  );

  assert.equal(isCodingAgentsAutomationAvailable("127.0.0.1"), true);
  assert.equal(isCodingAgentsAutomationAvailable("localhost"), false);
  assert.equal(isCodingAgentsAutomationAvailable("studio.example.com"), false);
  assert.match(applicationsSource, /disabled=\{disabled\}/);
  assert.match(applicationsSource, /aria-describedby=\{tooltipId\}/);
  assert.match(applicationsSource, /role="tooltip"/);
  assert.match(applicationsSource, /仅本地部署可用/);
  assert.match(applicationsStyles, /\.application-card-wrap\.is-disabled:hover \.application-card-tooltip/);
  assert.match(applicationsStyles, /\.application-card-wrap\.is-disabled:focus-visible \.application-card-tooltip/);
});

test("renders client and bundled skill selection with one global configure action", () => {
  assert.match(integrationSource, /getCodingAgentCapabilities/);
  assert.match(integrationSource, /trae-logo\.svg/);
  assert.match(integrationSource, /function ClaudeLogo/);
  assert.match(integrationSource, /function CodexLogo/);
  assert.match(integrationSource, /aria-label="选择 Coding Agent"/);
  assert.match(integrationSource, /aria-label="选择内置 Skill"/);
  assert.match(integrationSource, /aria-pressed=\{selectedAgentIds\.has\(agent\.id\)\}/);
  assert.match(integrationSource, /type="checkbox"/);
  assert.match(integrationSource, /查看文件/);
  assert.match(integrationSource, /SkillPreviewDialog/);
  assert.match(integrationSource, /全局安装/);
  assert.match(integrationSource, /globalSkillsPath/);
  assert.match(integrationSource, /正在配置…/);
  assert.match(integrationSource, /actionBusy \? "正在配置…" : "配置"/);
  assert.match(integrationSource, /role="alert"/);
  assert.match(integrationSource, /AbortController/);
  assert.doesNotMatch(integrationSource, /Skill Space|listSkillSpaces|getSkillDetail/);
  assert.doesNotMatch(integrationSource, /任务说明|安装并连接|launchCodingAgent/);
  assert.doesNotMatch(integrationSource, /localStorage|sessionStorage/);
  assert.doesNotMatch(integrationSource, /lucide-react/);
  assert.match(integrationStyles, /\.coding-agents-content \{ width: 100%/);
  assert.match(integrationStyles, /\.coding-agents-skill-list \{ display: flex; flex-direction: column/);
  assert.match(integrationStyles, /\.coding-agents-preview-dialog \{[^}]*margin: auto/is);
  assert.match(integrationStyles, /\.coding-agents-preview-file pre[^}]*font-family:[^}]*monospace/is);
  assert.match(integrationStyles, /@media \(max-width: 760px\)/);
  assert.match(integrationStyles, /@media \(prefers-reduced-motion: reduce\)/);
});

test("uses a fixed same-origin API with only agent and bundled skill ids", async () => {
  const originalWindow = globalThis.window;
  const originalLocalStorage = globalThis.localStorage;
  const originalSessionStorage = globalThis.sessionStorage;
  const storage = {
    getItem() { return null; },
    setItem() {},
  };
  globalThis.window = {
    location: { search: "", origin: "http://localhost", pathname: "/", hash: "" },
  };
  globalThis.localStorage = storage;
  globalThis.sessionStorage = storage;
  const {
    getCodingAgentCapabilities,
    getCodingAgentSkillPreview,
    installCodingAgentSkills,
  } = await loadTypeScriptModule("../src/adk/codingAgents.ts");
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    return new Response(JSON.stringify({ platform: "macos", agents: [], skills: [], installations: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    const signal = new AbortController().signal;
    await getCodingAgentCapabilities(signal);
    await getCodingAgentSkillPreview("agentkit-cli", signal);
    await installCodingAgentSkills({
      agents: ["trae"],
      skills: ["agentkit-cli"],
    }, signal);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.window = originalWindow;
    globalThis.localStorage = originalLocalStorage;
    globalThis.sessionStorage = originalSessionStorage;
  }

  assert.deepEqual(calls.map(({ url }) => url), [
    "/web/coding-agents/capabilities",
    "/web/coding-agents/skills/agentkit-cli/preview",
    "/web/coding-agents/install",
  ]);
  assert.equal(calls[1].init.method, "GET");
  assert.equal(calls[2].init.method, "POST");
  assert.equal(new Headers(calls[2].init.headers).get("Content-Type"), "application/json");
  assert.deepEqual(JSON.parse(calls[2].init.body), {
    agents: ["trae"],
    skills: ["agentkit-cli"],
  });
});
