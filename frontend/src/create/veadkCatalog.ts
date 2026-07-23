// Curated catalog of VeADK building blocks used by the custom-mode wizard and
// backend project generator. Everything here is grounded in the real
// veadk API (see examples/dogfooding/VEADK_COMPONENTS.md and veadk source).
//
// Each option carries enough metadata to (a) render a picker and (b) emit
// runnable Python + a complete .env.example.

export interface EnvVar {
  key: string;
  /** Whether the feature is non-functional without it (still emitted, but flagged). */
  required: boolean;
  placeholder?: string;
  comment?: string;
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

const ARK = "https://ark.cn-beijing.volces.com/api/v3/";

/** Base model env — always needed for the agent to run. */
export const MODEL_ENV: EnvVar[] = [
  { key: "MODEL_AGENT_NAME", required: false, placeholder: "doubao-seed-1-6-250615", comment: "模型名称" },
  { key: "MODEL_AGENT_PROVIDER", required: false, placeholder: "openai" },
  { key: "MODEL_AGENT_API_BASE", required: false, placeholder: ARK },
];

const EMBEDDING_ENV: EnvVar[] = [
  { key: "MODEL_EMBEDDING_NAME", required: false, placeholder: "doubao-embedding-vision-250615", comment: "向量化模型（记忆/知识库需要）" },
  { key: "MODEL_EMBEDDING_DIM", required: false, placeholder: "2048" },
  { key: "MODEL_EMBEDDING_API_BASE", required: false, placeholder: ARK },
];

// Studio owns the Volcengine credential chain and forwards it to debug runs and
// AgentKit runtimes. Components must not ask users to duplicate AK/SK settings.
const VOLC_ENV: EnvVar[] = [];

/** Feishu Channel runtime credentials. */
export const FEISHU_ENV: EnvVar[] = [
  {
    key: "FEISHU_APP_ID",
    required: true,
    placeholder: "cli_xxx",
    comment: "飞书应用 App ID",
  },
  {
    key: "FEISHU_APP_SECRET",
    required: true,
    placeholder: "输入 App Secret",
    comment: "飞书应用 App Secret",
  },
];

export const A2A_REGISTRY_DEFAULTS = {
  topK: "3",
  region: "cn-beijing",
  endpoint: "https://open.volcengineapi.com/",
} as const;

/** AgentKit A2A registry center runtime configuration. */
export const A2A_REGISTRY_ENV: EnvVar[] = [
  {
    key: "REGISTRY_SPACE_ID",
    required: true,
    placeholder: "请输入智能体中心 ID，如 as-yer579143kbrkemozdn6",
    comment: "AgentKit 智能体中心 ID",
  },
  {
    key: "REGISTRY_TOP_K",
    required: false,
    placeholder: A2A_REGISTRY_DEFAULTS.topK,
    comment: "召回 Agent 数量",
  },
  {
    key: "REGISTRY_REGION",
    required: false,
    placeholder: A2A_REGISTRY_DEFAULTS.region,
    comment: "AgentKit 智能体中心地域",
  },
  {
    key: "REGISTRY_ENDPOINT",
    required: false,
    placeholder: A2A_REGISTRY_DEFAULTS.endpoint,
    comment: "AgentKit 智能体中心 OpenAPI 地址",
  },
];

/* ------------------------------------------------------------------ *
 * Built-in tools (curated to ones that load without npx/uvx/AgentKit).
 * ------------------------------------------------------------------ */
export const BUILTIN_TOOLS: ToolOption[] = [
  {
    id: "web_search",
    label: "联网搜索",
    desc: "火山引擎 Web Search，获取实时信息。",
    importLine: "from veadk.tools.builtin_tools.web_search import web_search",
    toolNames: ["web_search"],
    env: VOLC_ENV,
  },
  {
    id: "parallel_web_search",
    label: "并行联网搜索",
    desc: "并行发起多条搜索查询，更快汇总。",
    importLine: "from veadk.tools.builtin_tools.parallel_web_search import parallel_web_search",
    toolNames: ["parallel_web_search"],
    env: VOLC_ENV,
  },
  {
    id: "link_reader",
    label: "网页读取",
    desc: "抓取并阅读给定链接的正文内容。",
    importLine: "from veadk.tools.builtin_tools.link_reader import link_reader",
    toolNames: ["link_reader"],
    env: [],
  },
  {
    id: "web_scraper",
    label: "网页爬取",
    desc: "结构化爬取网页（需要 Scraper 服务）。",
    importLine: "from veadk.tools.builtin_tools.web_scraper import web_scraper",
    toolNames: ["web_scraper"],
    env: [
      { key: "TOOL_WEB_SCRAPER_ENDPOINT", required: true },
      { key: "TOOL_WEB_SCRAPER_API_KEY", required: true },
    ],
  },
  {
    id: "image_generate",
    label: "图像生成",
    desc: "文生图（Doubao Seedream）。",
    importLine: "from veadk.tools.builtin_tools.image_generate import image_generate",
    toolNames: ["image_generate"],
    env: [{ key: "MODEL_IMAGE_NAME", required: false, placeholder: "doubao-seedream-5-0-260128" }],
  },
  {
    id: "image_edit",
    label: "图像编辑",
    desc: "图生图 / 编辑（Doubao SeedEdit）。",
    importLine: "from veadk.tools.builtin_tools.image_edit import image_edit",
    toolNames: ["image_edit"],
    env: [{ key: "MODEL_EDIT_NAME", required: false, placeholder: "doubao-seededit-3-0-i2i-250628" }],
  },
  {
    id: "video_generate",
    label: "视频生成",
    desc: "文/图生视频（Doubao Seedance），含任务查询。",
    importLine: "from veadk.tools.builtin_tools.video_generate import video_generate, video_task_query",
    toolNames: ["video_generate", "video_task_query"],
    env: [{ key: "MODEL_VIDEO_NAME", required: false, placeholder: "doubao-seedance-2-0-260128" }],
  },
  {
    id: "text_to_speech",
    label: "语音合成 (TTS)",
    desc: "把文本转成语音（火山语音）。",
    importLine: "from veadk.tools.builtin_tools.tts import text_to_speech",
    toolNames: ["text_to_speech"],
    env: [
      { key: "TOOL_VESPEECH_APP_ID", required: true },
      { key: "TOOL_VESPEECH_SPEAKER", required: false, placeholder: "zh_female_vv_uranus_bigtts" },
    ],
  },
  {
    id: "vesearch",
    label: "VeSearch 智能搜索",
    desc: "火山 VeSearch（需要 bot 端点）。",
    importLine: "from veadk.tools.builtin_tools.vesearch import vesearch",
    toolNames: ["vesearch"],
    env: [{ key: "TOOL_VESEARCH_ENDPOINT", required: true, comment: "VeSearch bot_id" }],
  },
];

/* ------------------------------------------------------------------ *
 * Short-term memory backends.
 * ------------------------------------------------------------------ */
export const STM_BACKENDS: BackendOption[] = [
  { id: "local", label: "本地内存", desc: "进程内，不持久化。适合开发调试。", env: [] },
  {
    id: "sqlite",
    label: "SQLite 文件",
    desc: "持久化到本地 .db 文件。",
    extraArgs: 'local_database_path="./short_term_memory.db"',
    env: [],
  },
  {
    id: "mysql",
    label: "MySQL",
    desc: "持久化到 MySQL。",
    env: [
      { key: "DATABASE_MYSQL_HOST", required: true },
      { key: "DATABASE_MYSQL_USER", required: true },
      { key: "DATABASE_MYSQL_PASSWORD", required: true },
      { key: "DATABASE_MYSQL_DATABASE", required: true },
    ],
  },
  {
    id: "postgresql",
    label: "PostgreSQL",
    desc: "持久化到 PostgreSQL。",
    env: [
      { key: "DATABASE_POSTGRESQL_HOST", required: true },
      { key: "DATABASE_POSTGRESQL_PORT", required: false, placeholder: "5432" },
      { key: "DATABASE_POSTGRESQL_USER", required: true },
      { key: "DATABASE_POSTGRESQL_PASSWORD", required: true },
      { key: "DATABASE_POSTGRESQL_DATABASE", required: true },
    ],
  },
];

/* ------------------------------------------------------------------ *
 * Long-term memory backends.
 * ------------------------------------------------------------------ */
export const LTM_BACKENDS: BackendOption[] = [
  { id: "local", label: "本地向量库", desc: "进程内 llama-index 向量库。", env: EMBEDDING_ENV, pipExtra: "extensions", needsEmbedding: true },
  {
    id: "opensearch",
    label: "OpenSearch",
    desc: "OpenSearch 向量检索。",
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
    label: "Redis",
    desc: "Redis 向量检索。",
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
    label: "VikingDB Memory",
    desc: "火山 VikingDB 记忆库（支持用户画像）。",
    env: VOLC_ENV,
  },
  {
    id: "mem0",
    label: "Mem0",
    desc: "Mem0 托管记忆服务。",
    env: [
      { key: "DATABASE_MEM0_API_KEY", required: true },
      { key: "DATABASE_MEM0_BASE_URL", required: false },
    ],
  },
];

/* ------------------------------------------------------------------ *
 * Knowledgebase backends.
 * ------------------------------------------------------------------ */
export const KB_BACKENDS: BackendOption[] = [
  { id: "local", label: "本地向量库", desc: "进程内 llama-index 向量库。", env: EMBEDDING_ENV, pipExtra: "extensions", needsEmbedding: true },
  {
    id: "opensearch",
    label: "OpenSearch",
    desc: "OpenSearch 向量检索。",
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
    id: "viking",
    label: "VikingDB Knowledge",
    desc: "火山 VikingDB 知识库。",
    env: VOLC_ENV,
  },
  {
    id: "context_search",
    label: "Context Search",
    desc: "火山 Context Search 引擎（无需向量化）。",
    env: [
      ...VOLC_ENV,
      { key: "DATABASE_CONTEXT_SEARCH_ENGINE_ID", required: true },
      { key: "DATABASE_CONTEXT_SEARCH_ENGINE_ENDPOINT", required: true },
      { key: "DATABASE_CONTEXT_SEARCH_ENGINE_APIKEY", required: true },
    ],
  },
];

/* ------------------------------------------------------------------ *
 * Tracing exporters (enabled via ENABLE_* env flags).
 * ------------------------------------------------------------------ */
export const TRACING_EXPORTERS: ExporterOption[] = [
  {
    id: "apmplus",
    label: "APMPlus",
    desc: "火山 APMPlus 应用性能监控。",
    enableFlag: "ENABLE_APMPLUS",
    env: [{ key: "OBSERVABILITY_OPENTELEMETRY_APMPLUS_SERVICE_NAME", required: false }],
  },
  {
    id: "cozeloop",
    label: "CozeLoop",
    desc: "扣子 CozeLoop 链路观测。",
    enableFlag: "ENABLE_COZELOOP",
    env: [
      { key: "OBSERVABILITY_OPENTELEMETRY_COZELOOP_API_KEY", required: true },
      { key: "OBSERVABILITY_OPENTELEMETRY_COZELOOP_SERVICE_NAME", required: false, comment: "CozeLoop space_id" },
    ],
  },
  {
    id: "tls",
    label: "TLS (日志服务)",
    desc: "火山 TLS 日志服务导出。",
    enableFlag: "ENABLE_TLS",
    env: [
      ...VOLC_ENV,
      { key: "OBSERVABILITY_OPENTELEMETRY_TLS_SERVICE_NAME", required: false, comment: "TLS topic_id，留空自动创建" },
    ],
  },
];

export const findTool = (id: string) => BUILTIN_TOOLS.find((t) => t.id === id);
export const findStm = (id: string) => STM_BACKENDS.find((b) => b.id === id);
export const findLtm = (id: string) => LTM_BACKENDS.find((b) => b.id === id);
export const findKb = (id: string) => KB_BACKENDS.find((b) => b.id === id);
export const findExporter = (id: string) => TRACING_EXPORTERS.find((e) => e.id === id);
