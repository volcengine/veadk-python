import { stringify } from "yaml";
import type { ProjectFile } from "../project";
import { DSH_PACKAGE_VERSION, nativeContainerFiles } from "./containerFiles";
import type { CloudProvider } from "../../adk/cloudProvider";

// Native web-profile settings, verified against this upstream revision
export const DSH_CONFIG_REVISION = "aa8262ec091698bae9a6b04773a6b5b06ad4aef2";
export const DSH_CONFIG_SOURCE = `https://github.com/deepseek-ai/deepseek-harness/blob/${DSH_CONFIG_REVISION}`;
export const DSH_PROTOCOLS = ["openai-completions", "openai-responses", "anthropic-messages"] as const;
// Bundled catalogs at DSH_CONFIG_REVISION; a deployment can extend these
export const DSH_MODELS = ["deepseek-flash", "deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-vision-exp"] as const;
export const DSH_PRESETS = ["standard", "minimal", "ptc", "cordis"] as const;
export const DSH_REASONING_EFFORTS = ["off", "low", "high", "max"] as const;

export interface NativeField {
  path: string;
  kind: "text" | "number" | "select";
  options?: readonly string[];
  allowCustom?: boolean;
  check?: "env" | "url" | "positive" | "integer" | "timer";
  defaultValue?: string;
}

export interface NativeSection {
  id: string;
  source: string;
  fields: NativeField[];
}

// Known defaults are prefilled and exported; fields without a fixed default stay optional
export const NATIVE_SECTIONS: NativeSection[] = [
  {
    id: "defaults", source: "packages/core/agent-default-model/src/index.ts",
    fields: [
      { path: "agent-default-model.provider", kind: "select", defaultValue: "deepseek-official" },
      { path: "agent-default-model.model", kind: "select", defaultValue: "deepseek-flash" },
      { path: "agent-default-model.reasoningEffort", kind: "select" },
      { path: "agent-presets.default", kind: "select", options: DSH_PRESETS, allowCustom: true, defaultValue: "standard" },
      { path: "permission.defaultPreset", kind: "select", options: ["read-only", "workspace-write", "danger-full-access"], defaultValue: "workspace-write" },
    ],
  },
  {
    id: "deepseek", source: "packages/llm/llm-deepseek/src/index.ts",
    fields: [
      { path: "llm-deepseek.apiKeyEnv", kind: "text", check: "env", defaultValue: "DEEPSEEK_API_KEY" },
      { path: "llm-deepseek.baseURL", kind: "text", check: "url" },
      { path: "llm-deepseek.thinking", kind: "select", options: ["enabled", "disabled"] },
      { path: "llm-deepseek.reasoningEffort", kind: "select", options: DSH_REASONING_EFFORTS, defaultValue: "high" },
      { path: "llm-deepseek.maxTokens", kind: "number", check: "integer", defaultValue: "256000" },
      { path: "llm-deepseek.defaultContextWindow", kind: "number", check: "integer", defaultValue: "1000000" },
      { path: "llm-deepseek.streamIdleTimeoutMs", kind: "number", check: "timer", defaultValue: "300000" },
    ],
  },
  {
    id: "shell", source: "packages/shell/bash-local/src/index.ts",
    fields: [
      { path: "bash.timeoutMs", kind: "number", check: "positive", defaultValue: "60000" },
      { path: "bash.maxTimeoutMs", kind: "number", check: "positive", defaultValue: "600000" },
      { path: "bash.maxOutputBytes", kind: "number", check: "positive", defaultValue: "64000" },
    ],
  },
  {
    id: "loop", source: "packages/core/agent-loop/src/index.ts",
    fields: [{ path: "agent-loop.maxParallelToolCalls", kind: "number", check: "integer" }],
  },
  {
    id: "subagents", source: "packages/subagent/tool-subagent/src/model-selection-settings.ts",
    fields: [{ path: "subagent-model-selection.enabled", kind: "select", options: ["true", "false"], defaultValue: "false" }],
  },
  {
    id: "search", source: "packages/web/web-search-deepseek/src/index.ts",
    fields: [
      { path: "web-search-deepseek.apiKeyEnv", kind: "text", check: "env", defaultValue: "DEEPSEEK_API_KEY" },
      { path: "web-search-deepseek.baseURL", kind: "text", check: "url" },
      { path: "web-search-deepseek.model", kind: "select", options: ["deepseek-v4-flash"], allowCustom: true, defaultValue: "deepseek-v4-flash" },
      { path: "web-search-deepseek.apiVersion", kind: "select", options: ["2023-06-01"], allowCustom: true, defaultValue: "2023-06-01" },
      { path: "web-search-deepseek.maxTokens", kind: "number", check: "integer", defaultValue: "4096" },
      { path: "web-search-deepseek.maxUses", kind: "number", check: "integer", defaultValue: "5" },
    ],
  },
];

export interface NativeModelDraft {
  key: string;
  id: string;
  name: string;
  contextWindow: string;
  maxTokens: string;
}

export interface NativeProviderDraft {
  key: string;
  id: string;
  displayName: string;
  baseURL: string;
  api: string;
  apiKeyEnv: string;
  models: NativeModelDraft[];
}

export interface NativeRouteDraft { key: string; provider: string; model: string }
export interface NativeConfigDraft {
  fields: Record<string, string>;
  providers: NativeProviderDraft[];
  allowedModels: NativeRouteDraft[];
}

export function nativeProviderOptions(draft: NativeConfigDraft): string[] {
  return [...new Set(["deepseek-official", ...draft.providers.map((provider) => provider.id.trim()).filter(Boolean)])];
}

export function nativeModelOptions(draft: NativeConfigDraft, provider: string): readonly string[] {
  if (provider === "deepseek-official") return DSH_MODELS;
  const models = draft.providers.find((item) => item.id.trim() === provider)?.models ?? [];
  return [...new Set(models.map((model) => model.id.trim()).filter(Boolean))];
}

export function resolveNativeField(draft: NativeConfigDraft, field: NativeField): NativeField {
  const provider = (draft.fields["agent-default-model.provider"] ?? "").trim() || "deepseek-official";
  switch (field.path) {
    case "agent-default-model.provider": return { ...field, options: nativeProviderOptions(draft) };
    case "agent-default-model.model": return { ...field, options: nativeModelOptions(draft, provider), allowCustom: provider === "deepseek-official" };
    // Models entered through this editor do not declare reasoning levels
    case "agent-default-model.reasoningEffort": return { ...field, options: provider === "deepseek-official" ? DSH_REASONING_EFFORTS : [] };
    default: return field;
  }
}

export function updateNativeField(draft: NativeConfigDraft, path: string, value: string): NativeConfigDraft {
  const fields = { ...draft.fields, [path]: value };
  if (path === "agent-default-model.provider" && value !== draft.fields[path]) {
    fields["agent-default-model.model"] = nativeModelOptions(draft, value)[0] ?? "";
    fields["agent-default-model.reasoningEffort"] = "";
  }
  return { ...draft, fields };
}

export function createNativeDraft(): NativeConfigDraft {
  const fields: Record<string, string> = {};
  for (const section of NATIVE_SECTIONS) {
    for (const field of section.fields) {
      if (field.defaultValue !== undefined) fields[field.path] = field.defaultValue;
    }
  }
  return { fields, providers: [], allowedModels: [] };
}

export type NativeConfigIssue = "positive" | "integer" | "timer" | "env" | "url" | "option" | "required" | "duplicate" | "providerId" | "routes" | "modelPair" | "unknownProvider" | "unknownModel";
export type NativeConfigErrors = Record<string, NativeConfigIssue>;

function validUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password &&
      ![...url.searchParams.keys()].some((key) => /token|key|secret|password/i.test(key));
  } catch { return false; }
}

function fieldIssue(field: NativeField, value: string): NativeConfigIssue | null {
  if (!value) return null;
  if (field.options && !field.allowCustom && !field.options.includes(value)) return "option";
  if (field.check === "env" && !/^[A-Za-z_][A-Za-z0-9_]*$/.test(value)) return "env";
  if (field.check === "url" && !validUrl(value)) return "url";
  if (field.check === "integer" && (!Number.isSafeInteger(Number(value)) || Number(value) <= 0)) return "integer";
  if (field.check === "positive" && (!Number.isFinite(Number(value)) || Number(value) <= 0)) return "positive";
  if (field.check === "timer" && (!Number.isFinite(Number(value)) || Number(value) <= 0 || Number(value) > 2147483647)) return "timer";
  return null;
}

export function validateNativeDraft(draft: NativeConfigDraft): NativeConfigErrors {
  const errors: NativeConfigErrors = {};
  for (const section of NATIVE_SECTIONS) {
    for (const field of section.fields) {
      const issue = fieldIssue(resolveNativeField(draft, field), (draft.fields[field.path] ?? "").trim());
      if (issue) errors[field.path] = issue;
    }
  }
  const providerIds = new Set<string>();
  for (const provider of draft.providers) {
    const path = `providers.${provider.key}`;
    const id = provider.id.trim();
    if (!/^[a-z][a-z0-9._-]*$/.test(id) || ["constructor", "prototype", "deepseek-official"].includes(id)) errors[`${path}.id`] = "providerId";
    else if (providerIds.has(id)) errors[`${path}.id`] = "duplicate";
    providerIds.add(id);
    if (!(DSH_PROTOCOLS as readonly string[]).includes(provider.api)) errors[`${path}.api`] = "option";
    if (!validUrl(provider.baseURL.trim())) errors[`${path}.baseURL`] = "url";
    if (!provider.apiKeyEnv.trim()) errors[`${path}.apiKeyEnv`] = "required";
    else if (fieldIssue({ path: "", kind: "text", check: "env" }, provider.apiKeyEnv.trim())) errors[`${path}.apiKeyEnv`] = "env";
    if (!provider.models.length) errors[`${path}.models`] = "required";
    const modelIds = new Set<string>();
    for (const model of provider.models) {
      const modelPath = `${path}.models.${model.key}`;
      const modelId = model.id.trim();
      if (!modelId) errors[`${modelPath}.id`] = "required";
      else if (modelIds.has(modelId)) errors[`${modelPath}.id`] = "duplicate";
      modelIds.add(modelId);
      for (const name of ["contextWindow", "maxTokens"] as const) {
        if (fieldIssue({ path: "", kind: "number", check: "integer" }, model[name].trim())) errors[`${modelPath}.${name}`] = "integer";
      }
    }
  }
  const provider = (draft.fields["agent-default-model.provider"] ?? "").trim();
  const model = (draft.fields["agent-default-model.model"] ?? "").trim();
  const checkRoute = (providerId: string, modelId: string, path: string) => {
    if (!providerId || !modelId) return;
    if (providerId === "deepseek-official") return;
    const custom = draft.providers.find((item) => item.id.trim() === providerId);
    if (!custom) errors[path] = "unknownProvider";
    else if (!custom.models.some((item) => item.id.trim() === modelId)) errors[path] = "unknownModel";
  };
  if (provider && provider !== "deepseek-official" && !model) errors["agent-default-model.model"] = "modelPair";
  checkRoute(provider || "deepseek-official", model, "agent-default-model.model");
  const routePath = "subagent-model-selection.allowedModels";
  if (draft.fields["subagent-model-selection.enabled"] === "true" && !draft.allowedModels.length) errors[routePath] = "routes";
  const routes = new Set<string>();
  for (const route of draft.allowedModels) {
    const routeProvider = route.provider.trim();
    const routeModel = route.model.trim();
    const key = JSON.stringify([routeProvider, routeModel]);
    if (!routeProvider || !routeModel) errors[routePath] = "routes";
    else if (routes.has(key)) errors[routePath] = "duplicate";
    routes.add(key);
    checkRoute(routeProvider, routeModel, routePath);
  }
  return errors;
}

export function nativeConfigFiles(draft: NativeConfigDraft, cloudProvider: CloudProvider = "volcengine"): ProjectFile[] {
  if (Object.keys(validateNativeDraft(draft)).length) throw new Error("Invalid DeepSeek Harness configuration");
  const settings: Record<string, Record<string, unknown>> = {};
  const credentialRefs = new Set(["DEEPSEEK_API_KEY"]);
  for (const section of NATIVE_SECTIONS) {
    for (const field of section.fields) {
      const value = (draft.fields[field.path] ?? "").trim();
      if (!value) continue;
      const [namespace, name] = field.path.split(".");
      settings[namespace] ??= {};
      settings[namespace][name] = field.kind === "number" ? Number(value)
        : field.path === "subagent-model-selection.enabled" ? value === "true" : value;
      if (field.check === "env") credentialRefs.add(value);
    }
  }
  if (draft.providers.length) {
    settings["llm-pi-ai"] = { providers: Object.fromEntries(draft.providers.map((provider) => {
      credentialRefs.add(provider.apiKeyEnv.trim());
      return [provider.id.trim(), {
        ...(provider.displayName.trim() ? { displayName: provider.displayName.trim() } : {}),
        baseURL: provider.baseURL.trim(), api: provider.api, apiKeyEnv: provider.apiKeyEnv.trim(),
        models: provider.models.map((model) => ({
          id: model.id.trim(),
          ...(model.name.trim() ? { name: model.name.trim() } : {}),
          ...(model.contextWindow.trim() ? { contextWindow: Number(model.contextWindow) } : {}),
          ...(model.maxTokens.trim() ? { maxTokens: Number(model.maxTokens) } : {}),
        })),
      }];
    })) };
  }
  if (draft.allowedModels.length) {
    settings["subagent-model-selection"] ??= {};
    settings["subagent-model-selection"].allowedModels = draft.allowedModels.map(({ provider, model }) => ({ provider: provider.trim(), model: model.trim() }));
  }
  return [
    ...nativeContainerFiles(cloudProvider),
    { path: "settings.yaml", content: `# DeepSeek Harness web profile\n# Configuration reference: ${DSH_CONFIG_REVISION}\n# Omitted fields inherit the deployed profile\n${stringify(settings, { lineWidth: 0 })}` },
    { path: ".env.example", content: `# Supply credentials through the deployment environment\n${[...credentialRefs].sort().map((key) => `${key}=\n`).join("")}` },
    { path: "README.md", content: `# DeepSeek Harness container

DSH package: ${DSH_PACKAGE_VERSION}
Configuration reference revision: ${DSH_CONFIG_REVISION}

## Build and run locally

Build the image from the exported directory:

    docker build -t deepseek-harness-agent .

Supply the credential references listed in .env.example through the process environment.
For the default DeepSeek provider, set DEEPSEEK_API_KEY in your shell and run:

    docker run --rm -p 127.0.0.1:8000:8000 -e DEEPSEEK_API_KEY deepseek-harness-agent

For custom providers, also pass their credential names with -e. Never put secret
values in the Dockerfile, settings.yaml or build arguments. The .env.example file
lists names only and is not loaded automatically. The build context includes only
the Dockerfile, settings.yaml, container.patch.yml, runtime.mjs and start.sh.

The image installs the official DSH npm package as its Harness base layer. It
runs as the node user with /workspace as its working directory. start.sh copies
the exported settings into DSH_HOME on each start, so image configuration replaces
any settings left there by a previous run. Supply persistent storage at
/home/node/.dsh and /workspace if sessions and workspace files must survive container
replacement; writable storage must be accessible to the node user (UID 1000).

The container boots the native DSH web profile privately on 127.0.0.1:3080.
The runtime.mjs plugin exposes GET /ping and POST /invocations on port 8000;
_FAAS_RUNTIME_PORT, then PORT, can override that port. Session creation goes through
DSH's native session controller and retains the selected Agent preset and model.
AgentKit starts /opt/application/run.sh directly; this script supplies the required
environment defaults without depending on Docker ENTRYPOINT or image ENV metadata.
The native browser service keeps its own authentication and is not exposed publicly.

## AgentKit Runtime

Use Studio's Deploy action to select the cloud region, build resources and secrets.
The deployment builds the Dockerfile through CodePipeline, pushes the image to CR,
and creates an AgentKit Runtime. agentkit.yaml also supplies the entry point for
CLI cloud builds. Region and resource selections belong to deployment configuration.
Volcengine and BytePlus use the same container and their own deployment credentials.

Runtime gateway authentication protects the invocation API. When running locally,
bind the container port to loopback as shown above. The adapter itself does not
implement a second authentication layer.

POST /invocations accepts {"prompt":"Hello","session_id":"optional-session-id"}
and returns {"response":"...","session_id":"...","agent_preset":"standard"}.
Requests for an active session return 409; malformed input returns 400. The default
invocation timeout is 300 seconds, configurable with DSH_INVOCATION_TIMEOUT_MS.
Disconnecting or timing out cancels the active turn. Provider errors return a failed
HTTP response instead of an empty successful answer. /ping checks Harness readiness;
a successful model invocation must be verified separately after deployment.

Session and workspace persistence follow the mounted storage. Without persistent
storage, container replacement loses local sessions. Concurrent replicas need
session routing or shared storage. This adapter exposes a JSON invocation API;
Studio's existing ADK chat protocol is not part of this adapter.

## Configuration scope

Preset choices must exist in the image. The bundled presets are included with DSH;
custom presets and extra plugins must be installed explicitly and added to the build
context. New default model, preset and permission selections apply to new sessions.
The editor covers default model/preset/permissions, the direct DeepSeek adapter,
custom providers, shell settings, tool-call parallelism, child model selection and
DeepSeek search. Other native plugin and preset-file settings are outside this editor.

Source: ${DSH_CONFIG_SOURCE}/docs/config-catalog.md
` },
  ];
}
