// Curated catalog of VeADK building blocks used by the custom-mode wizard and
// backend project generator. Everything here is grounded in the real
// veadk API (see examples/dogfooding/VEADK_COMPONENTS.md and veadk source).
//
// Each option carries enough metadata to (a) render a picker and (b) emit
// runnable Python + a complete .env.example.

import type { CloudProvider } from "../adk/cloudProvider";
import { createT } from "./i18n";

export interface EnvVar {
  key: string;
  /** Whether the feature is non-functional without it (still emitted, but flagged). */
  required: boolean;
  placeholder?: string;
  defaultValue?: string;
  comment?: string;
  help?: string;
  link?: { label: string; url: string };
  multiline?: boolean;
  format?: "json";
  secret?: boolean;
  readOnly?: boolean;
  serverManaged?: boolean;
  hidden?: boolean;
}

export interface ToolOption {
  id: string;
  label: string;
  desc: string;
  /** import line(s) to add to agent.py. */
  importLine: string;
  /** names to drop into the Agent's tools=[...] list. */
  toolNames: string[];
  env: EnvVar[];
  /** pip extra, e.g. "extensions" -> veadk-python[extensions]. */
  pipExtra?: string;
}

export interface BackendOption {
  id: string;
  label: string;
  desc: string;
  /** extra keyword args appended to the constructor, e.g. 'local_database_path="./stm.db"'. */
  extraArgs?: string;
  env: EnvVar[];
  pipExtra?: string;
  /** needs MODEL_EMBEDDING_* (embedding model). */
  needsEmbedding?: boolean;
}

export interface ExporterOption {
  id: "apmplus" | "cozeloop" | "tls";
  label: string;
  desc: string;
  /** ENABLE_* flag that turns the exporter on. */
  enableFlag: string;
  env: EnvVar[];
}

function localizedOptions<T extends { id: string }>(
  options: T[],
  resourcePath: string,
): Array<T & { label: string; desc: string }> {
  return options.map((option) => ({
    ...option,
    get label() {
      return createT(`${resourcePath}.${option.id}.label`);
    },
    get desc() {
      return createT(`${resourcePath}.${option.id}.description`);
    },
  }));
}

function localizedEnvVar(
  env: EnvVar,
  copy: Partial<Record<"comment" | "placeholder" | "help", string>>,
): EnvVar {
  const localized = { ...env };
  for (const [property, key] of Object.entries(copy)) {
    Object.defineProperty(localized, property, {
      configurable: true,
      enumerable: true,
      get: () => createT(key),
    });
  }
  return localized;
}

const ARK = "https://ark.cn-beijing.volces.com/api/v3/";

/** Base model env — always needed for the agent to run. */
export const MODEL_ENV: EnvVar[] = [
  localizedEnvVar(
    { key: "MODEL_AGENT_NAME", required: false, placeholder: "doubao-seed-1-6-250615" },
    { comment: "traditional.catalog.env.modelAgentName.comment" },
  ),
  { key: "MODEL_AGENT_PROVIDER", required: false, placeholder: "openai" },
  { key: "MODEL_AGENT_API_BASE", required: false, placeholder: ARK },
];

const EMBEDDING_ENV: EnvVar[] = [
  localizedEnvVar(
    { key: "MODEL_EMBEDDING_NAME", required: false, placeholder: "doubao-embedding-vision-250615" },
    { comment: "traditional.catalog.env.embeddingModelName.comment" },
  ),
  { key: "MODEL_EMBEDDING_DIM", required: false, placeholder: "2048" },
  { key: "MODEL_EMBEDDING_API_BASE", required: false, placeholder: ARK },
];

// Studio owns the Volcengine credential chain and forwards it to debug runs and
// AgentKit runtimes. Components must not ask users to duplicate AK/SK settings.
const VOLC_ENV: EnvVar[] = [];
const OPENVIKING_CONSOLE_LINK = {
  get label() {
    return createT("traditional.catalog.links.console");
  },
  url: "https://console.volcengine.com/vikingdb/openviking",
};
const OPENVIKING_SESSIONS_DOC_LINK = {
  get label() {
    return createT("traditional.catalog.links.documentation");
  },
  url: "https://github.com/volcengine/OpenViking/blob/main/docs/zh/api/05-sessions.md",
};
const OPENVIKING_DEFAULT_URL =
  "https://api.vikingdb.cn-beijing.volces.com/openviking";
const OPENVIKING_MEMORY_POLICY_PLACEHOLDER =
  '{\n  "self": {"enabled": true},\n  "peer": {"enabled": true},\n  "working_memory": {"enabled": true},\n  "memory_types": null\n}';

const VIKING_KB_ENV: EnvVar[] = [
  { key: "DATABASE_VIKING_PROJECT", required: false, placeholder: "default" },
  { key: "DATABASE_VIKING_REGION", required: false },
  { key: "DATABASE_VIKING_COLLECTION_KIND", required: false },
  { key: "DATABASE_VIKING_RESOURCE_ID", required: false },
];

const VIKING_MEMORY_ENV: EnvVar[] = [
  localizedEnvVar(
    {
      key: "DATABASE_VIKINGMEM_PROJECT",
      required: false,
      placeholder: "default",
      hidden: true,
    },
    { comment: "traditional.catalog.env.vikingMemoryProject.comment" },
  ),
  localizedEnvVar(
    { key: "DATABASE_VIKING_REGION", required: false, hidden: true },
    { comment: "traditional.catalog.env.vikingMemoryRegion.comment" },
  ),
  localizedEnvVar(
    {
      key: "DATABASE_VIKINGMEM_MEMORY_TYPE",
      required: false,
      placeholder: "sys_event_v1,sys_profile_v1",
      hidden: true,
    },
    { comment: "traditional.catalog.env.vikingMemoryType.comment" },
  ),
];

/** Feishu Channel runtime credentials. */
export const FEISHU_ENV: EnvVar[] = [
  localizedEnvVar(
    { key: "FEISHU_APP_ID", required: true, placeholder: "cli_xxx" },
    { comment: "traditional.catalog.env.feishuAppId.comment" },
  ),
  localizedEnvVar(
    { key: "FEISHU_APP_SECRET", required: true, secret: true },
    {
      placeholder: "traditional.catalog.env.feishuAppSecret.placeholder",
      comment: "traditional.catalog.env.feishuAppSecret.comment",
    },
  ),
];

export const A2A_REGISTRY_DEFAULTS = {
  topK: "3",
  region: "cn-beijing",
  endpoint: "https://open.volcengineapi.com/",
} as const;

export function a2aRegistryDefaults(cloudProvider: CloudProvider) {
  if (cloudProvider === "byteplus") {
    const region = "ap-southeast-1";
    return {
      topK: A2A_REGISTRY_DEFAULTS.topK,
      region,
      endpoint: `https://agentkit.${region}.byteplusapi.com/`,
    };
  }
  return A2A_REGISTRY_DEFAULTS;
}

/** AgentKit A2A registry center runtime configuration. */
export const A2A_REGISTRY_ENV: EnvVar[] = [
  localizedEnvVar(
    { key: "REGISTRY_SPACE_ID", required: true },
    {
      placeholder: "traditional.catalog.env.registrySpaceId.placeholder",
      comment: "traditional.catalog.env.registrySpaceId.comment",
    },
  ),
  localizedEnvVar(
    { key: "REGISTRY_TOP_K", required: false, placeholder: A2A_REGISTRY_DEFAULTS.topK },
    { comment: "traditional.catalog.env.registryTopK.comment" },
  ),
  localizedEnvVar(
    { key: "REGISTRY_REGION", required: false, placeholder: A2A_REGISTRY_DEFAULTS.region },
    { comment: "traditional.catalog.env.registryRegion.comment" },
  ),
  localizedEnvVar(
    { key: "REGISTRY_ENDPOINT", required: false, placeholder: A2A_REGISTRY_DEFAULTS.endpoint },
    { comment: "traditional.catalog.env.registryEndpoint.comment" },
  ),
];

/* ------------------------------------------------------------------ *
 * Built-in tools (curated to ones that load without npx/uvx/AgentKit).
 * ------------------------------------------------------------------ */
export const BUILTIN_TOOLS: ToolOption[] = localizedOptions<
  Omit<ToolOption, "label" | "desc">
>([
  {
    id: "web_search",
    importLine: "from veadk.tools.builtin_tools.web_search import web_search",
    toolNames: ["web_search"],
    env: VOLC_ENV,
  },
  {
    id: "parallel_web_search",
    importLine: "from veadk.tools.builtin_tools.parallel_web_search import parallel_web_search",
    toolNames: ["parallel_web_search"],
    env: VOLC_ENV,
  },
  {
    id: "link_reader",
    importLine: "from veadk.tools.builtin_tools.link_reader import link_reader",
    toolNames: ["link_reader"],
    env: [],
  },
  {
    id: "web_scraper",
    importLine: "from veadk.tools.builtin_tools.web_scraper import web_scraper",
    toolNames: ["web_scraper"],
    env: [
      { key: "TOOL_WEB_SCRAPER_ENDPOINT", required: true },
      { key: "TOOL_WEB_SCRAPER_API_KEY", required: true },
    ],
  },
  {
    id: "image_generate",
    importLine: "from veadk.tools.builtin_tools.image_generate import image_generate",
    toolNames: ["image_generate"],
    env: [{ key: "MODEL_IMAGE_NAME", required: false, placeholder: "doubao-seedream-5-0-260128" }],
  },
  {
    id: "image_edit",
    importLine: "from veadk.tools.builtin_tools.image_edit import image_edit",
    toolNames: ["image_edit"],
    env: [{ key: "MODEL_EDIT_NAME", required: false, placeholder: "doubao-seededit-3-0-i2i-250628" }],
  },
  {
    id: "video_generate",
    importLine: "from veadk.tools.builtin_tools.video_generate import video_generate, video_task_query",
    toolNames: ["video_generate", "video_task_query"],
    env: [{ key: "MODEL_VIDEO_NAME", required: false, placeholder: "doubao-seedance-2-0-260128" }],
  },
  {
    id: "text_to_speech",
    importLine: "from veadk.tools.builtin_tools.tts import text_to_speech",
    toolNames: ["text_to_speech"],
    env: [
      { key: "TOOL_VESPEECH_APP_ID", required: true },
      { key: "TOOL_VESPEECH_SPEAKER", required: false, placeholder: "zh_female_vv_uranus_bigtts" },
    ],
  },
  {
    id: "run_code",
    importLine: "from veadk.tools.builtin_tools.run_code import run_code",
    toolNames: ["run_code"],
    env: [
      {
        key: "AGENTKIT_TOOL_ID",
        required: true,
        placeholder: "t-xxxx",
        get comment() {
          return createT("traditional.catalog.env.agentKitToolId.comment");
        },
      },
      {
        key: "AGENTKIT_TOOL_REGION",
        required: false,
        placeholder: "cn-beijing",
        get comment() {
          return createT("traditional.catalog.env.agentKitToolRegion.comment");
        },
      },
    ],
  },
  {
    id: "vesearch",
    importLine: "from veadk.tools.builtin_tools.vesearch import vesearch",
    toolNames: ["vesearch"],
    env: [{ key: "TOOL_VESEARCH_ENDPOINT", required: true, comment: "VeSearch bot_id" }],
  },
], "traditional.catalog");

const HIDDEN_CREATE_TOOL_IDS = new Set([
  "web_scraper",
  "text_to_speech",
  "vesearch",
]);

const BYTEPLUS_HIDDEN_CREATE_TOOL_IDS = new Set([
  "web_search",
  "parallel_web_search",
]);

export const CREATE_BUILTIN_TOOLS = BUILTIN_TOOLS.filter(
  (tool) => !HIDDEN_CREATE_TOOL_IDS.has(tool.id),
);

export function createBuiltinToolsForProvider(
  cloudProvider: CloudProvider = "volcengine",
): ToolOption[] {
  const hidden =
    cloudProvider === "byteplus"
      ? BYTEPLUS_HIDDEN_CREATE_TOOL_IDS
      : new Set<string>();
  return CREATE_BUILTIN_TOOLS.filter((tool) => !hidden.has(tool.id));
}

/* ------------------------------------------------------------------ *
 * Short-term memory backends.
 * ------------------------------------------------------------------ */
export const STM_BACKENDS: BackendOption[] = localizedOptions<
  Omit<BackendOption, "label" | "desc">
>([
  { id: "local", env: [] },
  {
    id: "sqlite",
    extraArgs: 'local_database_path="./short_term_memory.db"',
    env: [],
  },
  {
    id: "mysql",
    env: [
      { key: "DATABASE_MYSQL_HOST", required: true },
      { key: "DATABASE_MYSQL_USER", required: true },
      { key: "DATABASE_MYSQL_PASSWORD", required: true },
      { key: "DATABASE_MYSQL_DATABASE", required: true },
    ],
  },
  {
    id: "postgresql",
    env: [
      { key: "DATABASE_POSTGRESQL_HOST", required: true },
      { key: "DATABASE_POSTGRESQL_PORT", required: false, placeholder: "5432" },
      { key: "DATABASE_POSTGRESQL_USER", required: true },
      { key: "DATABASE_POSTGRESQL_PASSWORD", required: true },
      { key: "DATABASE_POSTGRESQL_DATABASE", required: true },
    ],
  },
], "traditional.backends.shortTerm");

/* ------------------------------------------------------------------ *
 * Long-term memory backends.
 * ------------------------------------------------------------------ */
export const LTM_BACKENDS: BackendOption[] = localizedOptions<
  Omit<BackendOption, "label" | "desc">
>([
  { id: "local", env: EMBEDDING_ENV, pipExtra: "extensions", needsEmbedding: true },
  {
    id: "opensearch",
    env: [
      { key: "DATABASE_OPENSEARCH_HOST", required: true },
      { key: "DATABASE_OPENSEARCH_PORT", required: false, placeholder: "9200" },
      { key: "DATABASE_OPENSEARCH_USERNAME", required: true },
      { key: "DATABASE_OPENSEARCH_PASSWORD", required: true },
      ...EMBEDDING_ENV,
    ],
    pipExtra: "extensions",
    needsEmbedding: true,
  },
  {
    id: "redis",
    env: [
      { key: "DATABASE_REDIS_HOST", required: true },
      { key: "DATABASE_REDIS_PORT", required: false, placeholder: "6379" },
      { key: "DATABASE_REDIS_PASSWORD", required: false },
      ...EMBEDDING_ENV,
    ],
    pipExtra: "extensions",
    needsEmbedding: true,
  },
  {
    id: "viking",
    env: VIKING_MEMORY_ENV,
  },
  {
    id: "openviking",
    env: [
      {
        key: "DATABASE_OPENVIKING_URL",
        required: true,
        placeholder: OPENVIKING_DEFAULT_URL,
        get comment() {
          return createT("traditional.catalog.env.openVikingUrl.comment");
        },
        link: OPENVIKING_CONSOLE_LINK,
      },
      {
        key: "DATABASE_OPENVIKING_API_KEY",
        required: true,
        comment: "OpenViking API Key",
        link: OPENVIKING_CONSOLE_LINK,
      },
      {
        key: "DATABASE_OPENVIKING_USER_ID",
        required: false,
        placeholder: "default",
        get comment() {
          return createT("traditional.catalog.env.openVikingMemoryUserId.comment");
        },
        get help() {
          return createT("traditional.catalog.env.openVikingMemoryUserId.help");
        },
      },
      {
        key: "DATABASE_OPENVIKING_MEMORY_POLICY",
        required: false,
        placeholder: OPENVIKING_MEMORY_POLICY_PLACEHOLDER,
        get comment() {
          return createT("traditional.catalog.env.openVikingMemoryPolicy.comment");
        },
        multiline: true,
        format: "json",
        get help() {
          return createT("traditional.catalog.env.openVikingMemoryPolicy.help");
        },
        link: OPENVIKING_SESSIONS_DOC_LINK,
      },
    ],
  },
  {
    id: "mem0",
    env: [
      { key: "DATABASE_MEM0_API_KEY", required: true },
      { key: "DATABASE_MEM0_BASE_URL", required: false },
    ],
    pipExtra: "database",
  },
], "traditional.backends.longTerm");

/* ------------------------------------------------------------------ *
 * Knowledgebase backends.
 * ------------------------------------------------------------------ */
export const DEFAULT_KB_BACKEND = "viking";

export const KB_BACKENDS: BackendOption[] = localizedOptions<
  Omit<BackendOption, "label" | "desc">
>([
  {
    id: "viking",
    env: VIKING_KB_ENV,
  },
  {
    id: "opensearch",
    env: [
      { key: "DATABASE_OPENSEARCH_HOST", required: true },
      { key: "DATABASE_OPENSEARCH_PORT", required: false, placeholder: "9200" },
      { key: "DATABASE_OPENSEARCH_USERNAME", required: true },
      { key: "DATABASE_OPENSEARCH_PASSWORD", required: true },
      ...EMBEDDING_ENV,
    ],
    pipExtra: "extensions",
    needsEmbedding: true,
  },
  {
    id: "context_search",
    env: [
      ...VOLC_ENV,
      { key: "DATABASE_CONTEXT_SEARCH_ENGINE_ID", required: true },
      { key: "DATABASE_CONTEXT_SEARCH_ENGINE_ENDPOINT", required: true },
      { key: "DATABASE_CONTEXT_SEARCH_ENGINE_APIKEY", required: true },
    ],
  },
  {
    id: "openviking",
    env: [
      {
        key: "DATABASE_OPENVIKING_URL",
        required: true,
        placeholder: OPENVIKING_DEFAULT_URL,
        get comment() {
          return createT("traditional.catalog.env.openVikingUrl.comment");
        },
        link: OPENVIKING_CONSOLE_LINK,
      },
      {
        key: "DATABASE_OPENVIKING_API_KEY",
        required: true,
        comment: "OpenViking API Key",
        link: OPENVIKING_CONSOLE_LINK,
      },
      {
        key: "DATABASE_OPENVIKING_USER_ID",
        required: false,
        placeholder: "default",
        get comment() {
          return createT("traditional.catalog.env.openVikingKnowledgeUserId.comment");
        },
        get help() {
          return createT("traditional.catalog.env.openVikingKnowledgeUserId.help");
        },
      },
      {
        key: "DATABASE_OPENVIKING_TARGET_URI",
        required: false,
        placeholder: "viking://user/default/resources/<index>/",
        get comment() {
          return createT("traditional.catalog.env.openVikingTargetUri.comment");
        },
        get help() {
          return createT("traditional.catalog.env.openVikingTargetUri.help");
        },
      },
    ],
  },
], "traditional.backends.knowledge");

/* ------------------------------------------------------------------ *
 * Tracing exporters (enabled via ENABLE_* env flags).
 * ------------------------------------------------------------------ */
export const TRACING_EXPORTERS: ExporterOption[] = localizedOptions<
  Omit<ExporterOption, "label" | "desc">
>([
  {
    id: "apmplus",
    enableFlag: "ENABLE_APMPLUS",
    env: [{ key: "OBSERVABILITY_OPENTELEMETRY_APMPLUS_SERVICE_NAME", required: false }],
  },
  {
    id: "cozeloop",
    enableFlag: "ENABLE_COZELOOP",
    env: [
      { key: "OBSERVABILITY_OPENTELEMETRY_COZELOOP_API_KEY", required: true },
      { key: "OBSERVABILITY_OPENTELEMETRY_COZELOOP_SERVICE_NAME", required: false, comment: "CozeLoop space_id" },
    ],
  },
  {
    id: "tls",
    enableFlag: "ENABLE_TLS",
    env: [
      ...VOLC_ENV,
      localizedEnvVar(
        { key: "OBSERVABILITY_OPENTELEMETRY_TLS_SERVICE_NAME", required: false },
        { comment: "traditional.catalog.env.tlsServiceName.comment" },
      ),
    ],
  },
], "traditional.exporters");

export const findTool = (id: string) => BUILTIN_TOOLS.find((t) => t.id === id);
export const findStm = (id: string) => STM_BACKENDS.find((b) => b.id === id);
export const findLtm = (id: string) => LTM_BACKENDS.find((b) => b.id === id);
export const findKb = (id: string) => KB_BACKENDS.find((b) => b.id === id);
export const findExporter = (id: string) => TRACING_EXPORTERS.find((e) => e.id === id);
