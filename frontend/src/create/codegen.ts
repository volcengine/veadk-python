// Turns a custom-mode AgentDraft into a runnable VeADK project (AgentProject).
// Grounded in veadkCatalog.ts + examples/dogfooding/VEADK_COMPONENTS.md.
//
// Output files: agent.py, __init__.py, .env.example, requirements.txt, README.md.

import { emptyDraft, type AgentDraft, type CustomTool } from "./types";
import type { AgentProject, ProjectFile } from "./project";
import {
  MODEL_ENV,
  findTool,
  findStm,
  findLtm,
  findKb,
  findExporter,
  type EnvVar,
} from "./veadkCatalog";

/** Sanitize to a snake_case Python identifier. */
function ident(raw: string, fallback: string): string {
  let s = (raw || "").trim().toLowerCase();
  s = s.replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "").replace(/_+/g, "_");
  if (!s || /^[0-9]/.test(s)) s = s ? `a_${s}` : fallback;
  return s;
}

/** Python triple-quoted string literal (safe for multi-line instructions). */
function pyTriple(s: string): string {
  // Escape backslashes and any closing triple-quote.
  const body = (s || "").replace(/\\/g, "\\\\").replace(/"""/g, '\\"\\"\\"');
  return `"""${body}"""`;
}

/** Python single-line string literal with double quotes. */
function pyStr(s: string): string {
  return `"${(s || "").replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n")}"`;
}

interface Acc {
  imports: string[];
  preLines: string[]; // tool stubs + component constructions
  env: EnvVar[];
  extras: Set<string>; // pip extras
  usedNames: Set<string>; // python identifiers already taken (avoid collisions)
}

/** Ensure a unique python identifier within this project. */
function uniqueIdent(acc: Acc, raw: string, fallback: string): string {
  const base = ident(raw, fallback);
  let name = base;
  let n = 2;
  while (acc.usedNames.has(name)) name = `${base}_${n++}`;
  acc.usedNames.add(name);
  return name;
}

function addEnv(acc: Acc, vars: EnvVar[]) {
  for (const v of vars) acc.env.push(v);
}

/** Emit a stub function for a free-text / custom tool; returns its py name. */
function emitToolStub(acc: Acc, name: string, description: string): string {
  const fn = uniqueIdent(acc, name, "custom_tool");
  const doc = description?.trim() || `TODO: 描述 ${name} 的用途与参数。`;
  acc.preLines.push(
    `def ${fn}(query: str) -> dict:\n` +
      `    ${pyTriple(doc)}\n` +
      `    # TODO: 实现「${name}」的逻辑。\n` +
      `    return {"result": f"${fn} 尚未实现: {query}"}`,
  );
  return fn;
}

/** Build the Agent(...) wiring for one draft, returning the var name. Recurses
 *  for sub-agents (one level is what the wizard produces). */
function buildAgent(acc: Acc, draft: AgentDraft, varName: string, isRoot: boolean): string {
  const toolExprs: string[] = [];

  // Built-in tools (custom mode) — root only typically, but allow on any.
  for (const id of draft.builtinTools ?? []) {
    const t = findTool(id);
    if (!t) continue;
    if (!acc.imports.includes(t.importLine)) acc.imports.push(t.importLine);
    toolExprs.push(...t.toolNames);
    addEnv(acc, t.env);
    if (t.pipExtra) acc.extras.add(t.pipExtra);
  }
  // Custom function tools.
  for (const ct of draft.customTools ?? []) {
    if (!ct.name?.trim()) continue;
    toolExprs.push(emitToolStub(acc, ct.name, ct.description));
  }
  // MCP tool servers -> one MCPToolset each.
  for (const m of draft.mcpTools ?? []) {
    if (m.transport === "http" && m.url?.trim()) {
      acc.imports.push("from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset");
      acc.imports.push("from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams");
      const v = uniqueIdent(acc, `${m.name || "mcp"}_mcp`, "mcp_tool");
      const headers = m.authToken?.trim()
        ? `, headers={"Authorization": ${pyStr(`Bearer ${m.authToken.trim()}`)}}`
        : "";
      acc.preLines.push(
        `${v} = MCPToolset(connection_params=StreamableHTTPConnectionParams(url=${pyStr(m.url.trim())}${headers}))`,
      );
      toolExprs.push(v);
    } else if (m.transport === "stdio" && m.command?.trim()) {
      acc.imports.push("from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset");
      acc.imports.push("from google.adk.tools.mcp_tool.mcp_toolset import StdioConnectionParams, StdioServerParameters");
      const v = uniqueIdent(acc, `${m.name || "mcp"}_mcp`, "mcp_tool");
      const argsPy = `[${(m.args ?? []).filter((a) => a?.trim()).map((a) => pyStr(a)).join(", ")}]`;
      acc.preLines.push(
        `${v} = MCPToolset(connection_params=StdioConnectionParams(server_params=StdioServerParameters(command=${pyStr(m.command.trim())}, args=${argsPy}), timeout=30))`,
      );
      toolExprs.push(v);
    }
  }
  // Legacy free-text tools (sub-agents from the wizard use draft.tools) → stubs.
  for (const name of draft.tools ?? []) {
    if (!name?.trim()) continue;
    toolExprs.push(emitToolStub(acc, name, ""));
  }

  // Components (root only — sub-agents stay lean).
  const kwargs: string[] = [
    `name=${pyStr(ident(draft.name, varName))}`,
    `description=${pyStr(draft.description || draft.name || "A VeADK agent.")}`,
    `instruction=INSTRUCTION_${varName.toUpperCase()}`,
  ];
  acc.preLines.push(`INSTRUCTION_${varName.toUpperCase()} = ${pyTriple(draft.instruction || "You are a helpful assistant.")}`);

  if (toolExprs.length) kwargs.push(`tools=[${toolExprs.join(", ")}]`);

  if (isRoot) {
    // Model configuration (optional; empty -> veadk reads from config/env).
    if (draft.modelName?.trim()) kwargs.push(`model_name=${pyStr(draft.modelName.trim())}`);
    if (draft.modelProvider?.trim()) kwargs.push(`model_provider=${pyStr(draft.modelProvider.trim())}`);
    if (draft.modelApiBase?.trim()) kwargs.push(`model_api_base=${pyStr(draft.modelApiBase.trim())}`);

    // Short-term memory
    if (draft.memory?.shortTerm) {
      const b = findStm(draft.shortTermBackend || "local");
      if (b) {
        acc.imports.push("from veadk.memory.short_term_memory import ShortTermMemory");
        const args = [`backend=${pyStr(b.id)}`];
        if (b.extraArgs) args.push(b.extraArgs);
        acc.preLines.push(`short_term_memory = ShortTermMemory(${args.join(", ")})`);
        kwargs.push("short_term_memory=short_term_memory");
        addEnv(acc, b.env);
        if (b.pipExtra) acc.extras.add(b.pipExtra);
      }
    }
    // Long-term memory
    if (draft.memory?.longTerm) {
      const b = findLtm(draft.longTermBackend || "local");
      if (b) {
        acc.imports.push("from veadk.memory.long_term_memory import LongTermMemory");
        const idx = ident(draft.name, "my_agent");
        acc.preLines.push(
          `long_term_memory = LongTermMemory(backend=${pyStr(b.id)}, index=${pyStr(idx)}, app_name=${pyStr(idx)})`,
        );
        kwargs.push("long_term_memory=long_term_memory");
        if (draft.autoSaveSession) kwargs.push("auto_save_session=True");
        addEnv(acc, b.env);
        if (b.pipExtra) acc.extras.add(b.pipExtra);
      }
    }
    // Knowledgebase
    if (draft.knowledgebase) {
      const b = findKb(draft.knowledgebaseBackend || "local");
      if (b) {
        acc.imports.push("from veadk.knowledgebase import KnowledgeBase");
        const idx = ident(draft.name + "_kb", "my_kb");
        acc.preLines.push(`knowledgebase = KnowledgeBase(backend=${pyStr(b.id)}, index=${pyStr(idx)}, app_name=${pyStr(idx)})`);
        kwargs.push("knowledgebase=knowledgebase");
        addEnv(acc, b.env);
        if (b.pipExtra) acc.extras.add(b.pipExtra);
      }
    }
    // Tracing
    if (draft.tracing && (draft.tracingExporters?.length ?? 0) > 0) {
      acc.imports.push("from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer");
      acc.preLines.push("tracer = OpentelemetryTracer()");
      kwargs.push("tracers=[tracer]");
      for (const id of draft.tracingExporters ?? []) {
        const e = findExporter(id);
        if (!e) continue;
        acc.env.push({ key: e.enableFlag, required: true, placeholder: "true", comment: `${e.label} 开关` });
        addEnv(acc, e.env);
      }
    }
    if (draft.enableA2ui) {
      kwargs.push("enable_a2ui=True");
      acc.extras.add("a2ui");
    }

    // Sub-agents
    const subVars: string[] = [];
    (draft.subAgents ?? []).forEach((sa, i) => {
      const v = `sub_agent_${i + 1}`;
      buildAgent(acc, sa, v, false);
      subVars.push(v);
    });
    if (subVars.length) kwargs.push(`sub_agents=[${subVars.join(", ")}]`);
  }

  acc.preLines.push(`${varName} = Agent(\n    ${kwargs.join(",\n    ")},\n)`);
  return varName;
}

/** Dedupe env vars by key (first wins; required upgrades). */
function dedupeEnv(env: EnvVar[]): EnvVar[] {
  const map = new Map<string, EnvVar>();
  for (const v of env) {
    const cur = map.get(v.key);
    if (!cur) map.set(v.key, { ...v });
    else if (v.required && !cur.required) cur.required = true;
  }
  return [...map.values()];
}

function renderEnvExample(env: EnvVar[]): string {
  const lines = [
    "# 复制为 .env 并填入真实值（或改用 config.yaml）。",
    "# 标记 [必填] 的变量缺失时 Agent 无法启动。",
    "",
  ];
  for (const v of env) {
    if (v.comment || v.required) {
      lines.push(`# ${v.required ? "[必填] " : ""}${v.comment ?? ""}`.trimEnd());
    }
    lines.push(`${v.key}=${v.placeholder ?? ""}`);
  }
  return lines.join("\n") + "\n";
}

function renderRequirements(extras: Set<string>): string {
  const list = [...extras].sort();
  const pkg = list.length ? `veadk-python[${list.join(",")}]` : "veadk-python";
  return `${pkg}\n`;
}

function renderReadme(name: string, draft: AgentDraft): string {
  return [
    `# ${name}`,
    "",
    draft.description || "由 VeADK Web UI「自定义模式」生成的 Agent 项目。",
    "",
    "## 运行",
    "",
    "```bash",
    "pip install -r requirements.txt",
    "cp .env.example .env   # 填入你的密钥",
    "# 在本项目的上级目录启动 ADK API 服务：",
    `adk api_server --agents_dir .`,
    "```",
    "",
    "`agent.py` 在模块级别暴露 `root_agent`，可被 ADK / VeADK 直接加载。",
    "",
  ].join("\n");
}

/** Main entry: AgentDraft -> AgentProject. */
export function generateProject(draft: AgentDraft): AgentProject {
  const pkg = ident(draft.name, "my_agent");
  const acc: Acc = { imports: [], preLines: [], env: [...MODEL_ENV], extras: new Set(), usedNames: new Set() };

  buildAgent(acc, draft, "agent", true);

  // Assemble agent.py with FastAPI deployment support
  const importBlock = ["from veadk import Agent", ...dedupeImports(acc.imports)].join("\n");

  // Add deployment-specific imports
  const deploymentImports = [
    "import os",
    "from pathlib import Path",
    "import uvicorn",
    "from fastapi.staticfiles import StaticFiles",
    "from google.adk.cli.fast_api import get_fast_api_app",
  ].join("\n");

  // Build agent definition
  const agentDefinition = acc.preLines.join("\n\n") + "\n\n# ADK 加载器要求：顶层 agent 必须命名为 root_agent\nroot_agent = agent\n";

  const agentPy = importBlock + "\n\n" + agentDefinition;

  // Deployment entry point (app.py at root level)
  const appPy = `${deploymentImports}

# Deployment configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
AGENTS_DIR = str(Path(__file__).resolve().parent / "agents")

def build_app():
    """Build FastAPI app for deployment."""
    import veadk
    WEBUI_DIR = Path(veadk.__file__).resolve().parent / "webui"

    # Create FastAPI app with agents_dir (ADK multi-agent structure)
    app = get_fast_api_app(agents_dir=AGENTS_DIR, web=False)

    # Add health check endpoint
    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    # Mount web UI if available
    if (WEBUI_DIR / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(WEBUI_DIR), html=True), name="webui")

    return app

app = build_app()

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
`;

  const files: ProjectFile[] = [
    { path: "app.py", content: appPy },
    { path: `agents/${pkg}/agent.py`, content: agentPy },
    { path: `agents/${pkg}/__init__.py`, content: `from .agent import root_agent\n\n__all__ = ["root_agent"]\n` },
    { path: ".env.example", content: renderEnvExample(dedupeEnv(acc.env)) },
    { path: "requirements.txt", content: renderRequirements(acc.extras) },
    { path: "README.md", content: renderReadme(pkg, draft) },
  ];

  return { name: pkg, files };
}

function dedupeImports(imports: string[]): string[] {
  return [...new Set(imports)];
}

/* ------------------------------------------------------------------ *
 * Config normalization — turn an arbitrary (possibly partial / model-
 * produced) agent-config object into a complete, valid AgentDraft.
 * Both the custom wizard and the intelligent-mode agent_builder produce
 * objects in this shape, so they share one code path into generateProject.
 * ------------------------------------------------------------------ */
const STM_IDS = new Set(["local", "sqlite", "mysql", "postgresql"]);
const LTM_IDS = new Set(["local", "opensearch", "redis", "viking", "mem0"]);
const KB_IDS = new Set(["local", "opensearch", "viking", "context_search"]);
const EXPORTER_IDS = new Set(["apmplus", "cozeloop", "tls"]);
const TOOL_IDS = new Set(BUILTIN_TOOLS_IDS());

function BUILTIN_TOOLS_IDS(): string[] {
  // Imported lazily to avoid a circular import at module top.
  return [
    "web_search",
    "parallel_web_search",
    "link_reader",
    "web_scraper",
    "image_generate",
    "image_edit",
    "video_generate",
    "text_to_speech",
    "vesearch",
  ];
}

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}
function asBool(v: unknown): boolean {
  return v === true;
}
function asStringArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}
function asCustomTools(v: unknown): CustomTool[] {
  if (!Array.isArray(v)) return [];
  return v
    .map((t) => (t && typeof t === "object" ? { name: asString((t as any).name), description: asString((t as any).description) } : null))
    .filter((t): t is CustomTool => !!t && !!t.name.trim());
}
function pick<T>(v: unknown, allowed: Set<string>, fallback: T): string | T {
  return typeof v === "string" && allowed.has(v) ? v : fallback;
}

/** Coerce an arbitrary config object into a complete AgentDraft. */
export function normalizeDraft(raw: unknown): AgentDraft {
  const o = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const mem = (o.memory && typeof o.memory === "object" ? o.memory : {}) as Record<string, unknown>;
  const subAgents = Array.isArray(o.subAgents)
    ? (o.subAgents as unknown[]).map((s) => {
        // Sub-agents only carry the lean fields the wizard/codegen use.
        const so = (s && typeof s === "object" ? s : {}) as Record<string, unknown>;
        return {
          ...emptyDraft(),
          name: asString(so.name),
          description: asString(so.description),
          instruction: asString(so.instruction),
          builtinTools: asStringArray(so.builtinTools).filter((t) => TOOL_IDS.has(t)),
          customTools: asCustomTools(so.customTools),
        };
      })
    : [];

  const mcpTools = Array.isArray(o.mcpTools)
    ? (o.mcpTools as unknown[])
        .map((m) => {
          const mo = (m && typeof m === "object" ? m : {}) as Record<string, unknown>;
          const transport = mo.transport === "stdio" ? "stdio" : "http";
          return {
            name: asString(mo.name),
            transport: transport as "http" | "stdio",
            url: asString(mo.url),
            authToken: asString(mo.authToken),
            command: asString(mo.command),
            args: asStringArray(mo.args),
          };
        })
        .filter((m) => (m.transport === "http" ? !!m.url : !!m.command))
    : [];

  return {
    ...emptyDraft(),
    name: asString(o.name) || "my_agent",
    description: asString(o.description),
    instruction: asString(o.instruction) || "You are a helpful assistant.",
    modelName: asString(o.modelName),
    modelProvider: asString(o.modelProvider),
    modelApiBase: asString(o.modelApiBase),
    builtinTools: asStringArray(o.builtinTools).filter((t) => TOOL_IDS.has(t)),
    customTools: asCustomTools(o.customTools),
    mcpTools,
    memory: { shortTerm: asBool(mem.shortTerm), longTerm: asBool(mem.longTerm) },
    shortTermBackend: pick(o.shortTermBackend, STM_IDS, "local"),
    longTermBackend: pick(o.longTermBackend, LTM_IDS, "local"),
    autoSaveSession: asBool(o.autoSaveSession),
    knowledgebase: asBool(o.knowledgebase),
    knowledgebaseBackend: pick(o.knowledgebaseBackend, KB_IDS, "local"),
    tracing: asBool(o.tracing),
    tracingExporters: asStringArray(o.tracingExporters).filter((e) => EXPORTER_IDS.has(e)),
    enableA2ui: asBool(o.enableA2ui),
    subAgents,
    selectedSkills: Array.isArray(o.selectedSkills)
      ? (o.selectedSkills as unknown[])
          .map((s) => {
            const so = (s && typeof s === "object" ? s : {}) as Record<string, unknown>;
            return { slug: asString(so.slug), name: asString(so.name) || asString(so.slug), namespace: asString(so.namespace) || "public" };
          })
          .filter((s) => !!s.slug)
      : [],
  };
}
