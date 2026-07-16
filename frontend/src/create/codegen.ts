// Turns a custom-mode AgentDraft into a runnable VeADK project (AgentProject).
// Grounded in veadkCatalog.ts + examples/dogfooding/VEADK_COMPONENTS.md.
//
// Output files: agent.py, __init__.py, .env.example, requirements.txt, README.md.

import { emptyDraft, type AgentDraft, type CustomTool, type SelectedSkill } from "./types";
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

/** Build an orchestrator (SequentialAgent / ParallelAgent / LoopAgent) for one
 *  draft, returning the var name. Orchestrators own no model/instruction/tools;
 *  they only schedule their sub_agents. Children are emitted first (recursively)
 *  so they are defined above the parent. */
function buildOrchestrator(acc: Acc, draft: AgentDraft, varName: string): string {
  const type = draft.agentType as "sequential" | "parallel" | "loop";
  const cls =
    type === "parallel" ? "ParallelAgent" : type === "loop" ? "LoopAgent" : "SequentialAgent";
  acc.imports.push(`from google.adk.agents import ${cls}`);

  // Children (recursive — a child may itself be an orchestrator or an LLM agent).
  const subVars: string[] = [];
  (draft.subAgents ?? []).forEach((sa, i) => {
    const v = `${varName}_sub_${i + 1}`;
    buildAgent(acc, sa, v);
    subVars.push(v);
  });

  const kwargs: string[] = [
    `name=${pyStr(ident(draft.name, varName))}`,
    `description=${pyStr(draft.description || draft.name || "A VeADK orchestrator agent.")}`,
  ];
  if (type === "loop") {
    const iters = Number.isFinite(draft.maxIterations) ? Number(draft.maxIterations) : 3;
    kwargs.push(`max_iterations=${iters > 0 ? iters : 3}`);
  }
  kwargs.push(`sub_agents=[${subVars.join(", ")}]`);

  acc.preLines.push(`${varName} = ${cls}(\n    ${kwargs.join(",\n    ")},\n)`);
  return varName;
}

/** Build a leaf RemoteVeAgent (A2A remote agent referenced by URL). Owns no
 *  model/instruction/tools/sub_agents. RemoteVeAgent takes only name + url (+
 *  optional auth) — its description/skills come from the fetched agent card, so
 *  we deliberately do NOT pass `description` (the constructor rejects it). */
function buildA2a(acc: Acc, draft: AgentDraft, varName: string): string {
  acc.imports.push("from veadk.a2a.remote_ve_agent import RemoteVeAgent");
  const kwargs: string[] = [
    `name=${pyStr(ident(draft.name, varName))}`,
    `url=${pyStr((draft.a2aUrl ?? "").trim())}`,
  ];
  acc.preLines.push(`${varName} = RemoteVeAgent(\n    ${kwargs.join(",\n    ")},\n)`);
  return varName;
}

/** Build the Agent(...) wiring for one draft, returning the var name. Recurses
 *  for sub-agents at any depth. Orchestrator drafts (sequential / parallel /
 *  loop) are delegated to buildOrchestrator; "a2a" to buildA2a. */
function buildAgent(acc: Acc, draft: AgentDraft, varName: string): string {
  const agentType = draft.agentType ?? "llm";
  if (agentType === "a2a") {
    return buildA2a(acc, draft, varName);
  }
  if (agentType !== "llm") {
    return buildOrchestrator(acc, draft, varName);
  }

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

  // Skills (from Skill Hub / local upload / AgentKit SkillSpace). Each
  // selected skill is materialized to skills/<folder>/SKILL.md (+ optional
  // scripts/references) by the browser at finish() time. At runtime we load
  // every skill directory via ADK's load_skill_from_dir and wrap them in a
  // SkillToolset so the model can invoke them. This is added to tools=[...]
  // on the Agent, same as a built-in tool.
  const skillFolders = (draft.selectedSkills ?? [])
    .map((s) => s.folder)
    .filter((f): f is string => !!f && f.trim().length > 0);
  if (skillFolders.length > 0) {
    acc.imports.push("from pathlib import Path as _Path");
    acc.imports.push("from google.adk.skills import load_skill_from_dir");
    acc.imports.push("from google.adk.tools.skill_toolset import SkillToolset");
    const v = uniqueIdent(acc, `skills_${varName}`, "skill_toolset");
    // One skill per line for readability (especially with many skills).
    const loaders = skillFolders.map(
      (f) =>
        `        load_skill_from_dir(_Path(__file__).parent.parent.parent / "skills" / ${pyStr(f)})`,
    );
    acc.preLines.push(
      `${v} = SkillToolset(skills=[\n${loaders.join(",\n")},\n    ])`,
    );
    toolExprs.push(v);
  }

  // Every LLM agent (root or sub) gets the full component config. Preline
  // variable names are suffixed with `varName` so nested agents don't collide.
  const kwargs: string[] = [
    `name=${pyStr(ident(draft.name, varName))}`,
    `description=${pyStr(draft.description || draft.name || "A VeADK agent.")}`,
    `instruction=INSTRUCTION_${varName.toUpperCase()}`,
  ];
  acc.preLines.push(`INSTRUCTION_${varName.toUpperCase()} = ${pyTriple(draft.instruction || "You are a helpful assistant.")}`);

  if (toolExprs.length) kwargs.push(`tools=[${toolExprs.join(", ")}]`);

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
      const v = `stm_${varName}`;
      acc.preLines.push(`${v} = ShortTermMemory(${args.join(", ")})`);
      kwargs.push(`short_term_memory=${v}`);
      addEnv(acc, b.env);
      if (b.pipExtra) acc.extras.add(b.pipExtra);
    }
  }
  // Long-term memory
  if (draft.memory?.longTerm) {
    const b = findLtm(draft.longTermBackend || "local");
    if (b) {
      acc.imports.push("from veadk.memory.long_term_memory import LongTermMemory");
      const idx = ident(draft.name, varName);
      const v = `ltm_${varName}`;
      acc.preLines.push(
        `${v} = LongTermMemory(backend=${pyStr(b.id)}, index=${pyStr(idx)}, app_name=${pyStr(idx)})`,
      );
      kwargs.push(`long_term_memory=${v}`);
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
      const idx = ident(draft.name + "_kb", varName + "_kb");
      const v = `kb_${varName}`;
      acc.preLines.push(`${v} = KnowledgeBase(backend=${pyStr(b.id)}, index=${pyStr(idx)}, app_name=${pyStr(idx)})`);
      kwargs.push(`knowledgebase=${v}`);
      addEnv(acc, b.env);
      if (b.pipExtra) acc.extras.add(b.pipExtra);
    }
  }
  // Tracing
  if (draft.tracing && (draft.tracingExporters?.length ?? 0) > 0) {
    acc.imports.push("from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer");
    const v = `tracer_${varName}`;
    acc.preLines.push(`${v} = OpentelemetryTracer()`);
    kwargs.push(`tracers=[${v}]`);
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

  // Sub-agents (recurse — a child may itself be an LLM / orchestrator / a2a).
  const subVars: string[] = [];
  (draft.subAgents ?? []).forEach((sa, i) => {
    const v = `${varName}_sub_${i + 1}`;
    buildAgent(acc, sa, v);
    subVars.push(v);
  });
  if (subVars.length) kwargs.push(`sub_agents=[${subVars.join(", ")}]`);

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
  return `${pkg}\nagentkit-sdk-python\ngoogle-adk\n`;
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
    "python app.py",
    "```",
    "",
    "`app.py` 使用 AgentKit AgentServerApp 包裹 `root_agent`，监听 `0.0.0.0:8000`。",
    "",
  ].join("\n");
}

/** Main entry: AgentDraft -> AgentProject. */
export function generateProject(draft: AgentDraft): AgentProject {
  const pkg = ident(draft.name, "my_agent");
  const acc: Acc = { imports: [], preLines: [], env: [...MODEL_ENV], extras: new Set(), usedNames: new Set() };

  buildAgent(acc, draft, "agent");

  // Assemble agent.py with AgentKit deployment support
  const importBlock = ["from veadk import Agent", ...dedupeImports(acc.imports)].join("\n");

  // Add deployment-specific imports
  const deploymentImports = [
    "import os",
    "from pathlib import Path",
    "from agentkit.apps import AgentkitAgentServerApp",
    "from fastapi.staticfiles import StaticFiles",
    "from veadk.memory.short_term_memory import ShortTermMemory",
    `from agents.${pkg}.agent import root_agent`,
  ].join("\n");

  // Build agent definition
  const agentDefinition = acc.preLines.join("\n\n") + "\n\n# ADK 加载器要求：顶层 agent 必须命名为 root_agent\nroot_agent = agent\n";

  const agentPy = importBlock + "\n\n" + agentDefinition;

  // Deployment entry point (app.py at root level)
  const appPy = `${deploymentImports}

# Deployment configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

def build_app():
    """Build AgentKit AgentServerApp for deployment."""
    import veadk
    WEBUI_DIR = Path(veadk.__file__).resolve().parent / "webui"

    # AgentKit's AgentServerApp exposes the ADK-compatible API surface
    # (/list-apps, /run, /run_sse, sessions) expected by AgentKit runtime tests.
    short_term_memory = getattr(root_agent, "short_term_memory", None) or ShortTermMemory(
        backend="local"
    )
    agent_server_app = AgentkitAgentServerApp(
        agent=root_agent,
        short_term_memory=short_term_memory,
    )
    app = agent_server_app.app

    # Add health check endpoint
    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    # Agent-structure introspection (data plane), consumed by the VeADK web
    # UI's "管理 Agent" view to show this runtime's agent name + sub-agent tree.
    from fastapi import HTTPException as _HTTPException

    def _agent_type(a: object) -> str:
        try:
            from google.adk.agents import LoopAgent, ParallelAgent, SequentialAgent

            if isinstance(a, LoopAgent):
                return "loop"
            if isinstance(a, SequentialAgent):
                return "sequential"
            if isinstance(a, ParallelAgent):
                return "parallel"
        except Exception:
            pass
        try:
            from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

            if isinstance(a, RemoteA2aAgent):
                return "a2a"
        except Exception:
            pass
        return "llm"

    def _model_name(m: object) -> str:
        if isinstance(m, str):
            return m
        return str(getattr(m, "model", None) or type(m).__name__)

    def _tool_label(t: object) -> str:
        name = getattr(t, "name", None) or getattr(t, "__name__", None)
        return str(name or type(t).__name__)

    def _agent_node(a: object, depth: int = 0) -> dict:
        children = []
        if depth < 8:
            children = [_agent_node(s, depth + 1) for s in getattr(a, "sub_agents", []) or []]
        return {
            "name": getattr(a, "name", "") or "",
            "description": getattr(a, "description", "") or "",
            "type": _agent_type(a),
            "model": _model_name(getattr(a, "model", "")),
            "tools": [_tool_label(t) for t in getattr(a, "tools", []) or []],
            "children": children,
        }

    @app.get("/web/agent-info/{app_name}")
    def agent_info(app_name: str) -> dict:
        expected_name = getattr(root_agent, "name", "") or ""
        if app_name != expected_name:
            raise _HTTPException(status_code=404, detail="unknown agent: " + app_name)
        return {
            "name": expected_name or app_name,
            "description": getattr(root_agent, "description", "") or "",
            "type": _agent_type(root_agent),
            "model": _model_name(getattr(root_agent, "model", "")),
            "tools": [_tool_label(t) for t in getattr(root_agent, "tools", []) or []],
            "subAgents": [getattr(s, "name", "") for s in getattr(root_agent, "sub_agents", []) or []],
            "graph": _agent_node(root_agent),
        }

    @app.get("/web/agent-graph")
    def agent_graph() -> dict:
        # Single introspection endpoint on the main agent: returns this runtime's
        # root agent + recursive sub-agent tree, with no /list-apps discovery
        # needed. Used by the VeADK "管理 Agent" view.
        return {
            "name": getattr(root_agent, "name", "") or "",
            "description": getattr(root_agent, "description", "") or "",
            "type": _agent_type(root_agent),
            "model": _model_name(getattr(root_agent, "model", "")),
            "tools": [_tool_label(t) for t in getattr(root_agent, "tools", []) or []],
            "graph": _agent_node(root_agent),
        }

    # Serve the bundled VeADK web UI without taking over "/", which is reserved
    # by AgentServerApp for the A2A protocol surface.
    if (WEBUI_DIR / "index.html").is_file():
        if (WEBUI_DIR / "assets").is_dir():
            app.mount(
                "/assets",
                StaticFiles(directory=str(WEBUI_DIR / "assets")),
                name="webui-assets",
            )

        from fastapi.responses import FileResponse as _FileResponse

        @app.get("/")
        @app.get("/webui")
        @app.get("/webui/{path:path}")
        def webui(path: str = ""):
            return _FileResponse(WEBUI_DIR / "index.html")

    # AgentServerApp mounts A2A at "/", so routes added after construction must
    # be moved before that root mount or they will be shadowed.
    _priority_paths = {
        "/",
        "/ping",
        "/web/agent-info/{app_name}",
        "/web/agent-graph",
        "/assets",
        "/webui",
        "/webui/{path:path}",
    }
    _priority_routes = [
        r for r in app.router.routes if getattr(r, "path", None) in _priority_paths
    ]
    if _priority_routes:
        app.router.routes[:] = _priority_routes + [
            r for r in app.router.routes if r not in _priority_routes
        ]

    return agent_server_app, app

agent_server_app, app = build_app()

if __name__ == "__main__":
    agent_server_app.run(host=HOST, port=PORT)
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
const AGENT_TYPES = new Set(["llm", "sequential", "parallel", "loop", "a2a"]);
function asAgentType(v: unknown): NonNullable<AgentDraft["agentType"]> {
  return typeof v === "string" && AGENT_TYPES.has(v)
    ? (v as NonNullable<AgentDraft["agentType"]>)
    : "llm";
}
function asMaxIterations(v: unknown): number {
  return typeof v === "number" && Number.isFinite(v) && v > 0 ? Math.floor(v) : 3;
}

/** Recursively coerce a subAgents array. Children carry the lean fields the
 *  wizard/codegen use plus their own type + nested children. */
function parseSubAgents(v: unknown): AgentDraft[] {
  if (!Array.isArray(v)) return [];
  return v.map((s) => {
    const so = (s && typeof s === "object" ? s : {}) as Record<string, unknown>;
    return {
      ...emptyDraft(),
      name: asString(so.name),
      description: asString(so.description),
      instruction: asString(so.instruction),
      agentType: asAgentType(so.agentType),
      maxIterations: asMaxIterations(so.maxIterations),
      a2aUrl: asString(so.a2aUrl),
      builtinTools: asStringArray(so.builtinTools).filter((t) => TOOL_IDS.has(t)),
      customTools: asCustomTools(so.customTools),
      subAgents: parseSubAgents(so.subAgents),
    };
  });
}

/** Coerce an arbitrary config object into a complete AgentDraft. */
export function normalizeDraft(raw: unknown): AgentDraft {
  const o = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const mem = (o.memory && typeof o.memory === "object" ? o.memory : {}) as Record<string, unknown>;
  const subAgents = parseSubAgents(o.subAgents);

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
    agentType: asAgentType(o.agentType),
    maxIterations: asMaxIterations(o.maxIterations),
    a2aUrl: asString(o.a2aUrl),
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
    selectedSkills: ((): SelectedSkill[] => {
        if (!Array.isArray(o.selectedSkills)) return [];
        const out: SelectedSkill[] = [];
        for (const raw of o.selectedSkills as unknown[]) {
          const so = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
          const src = asString(so.source);
          const source: SelectedSkill["source"] =
            src === "local" || src === "skillspace" || src === "skillhub"
              ? src
              : "skillhub"; // backward compat: pre-multi-source YAMLs default to hub
          const name =
            asString(so.name) ||
            asString(so.slug) ||
            asString(so.skillName) ||
            asString(so.skillId) ||
            "skill";
          const folder = asString(so.folder) || name;
          const description = asString(so.description);
          if (source === "skillhub") {
            const slug = asString(so.slug);
            if (!slug) continue;
            out.push({
              source,
              folder,
              name,
              description,
              slug,
              namespace: asString(so.namespace) || "public",
            });
            continue;
          }
          if (source === "local") {
            const files = Array.isArray(so.localFiles) ? so.localFiles : [];
            const localFiles = files
              .map((f) => {
                const fo = (f && typeof f === "object" ? f : {}) as Record<string, unknown>;
                const path = asString(fo.path);
                const content = asString(fo.content);
                if (!path) return null;
                return { path, content };
              })
              .filter((x): x is { path: string; content: string } => x !== null);
            if (localFiles.length === 0) continue;
            out.push({ source, folder, name, description, localFiles });
            continue;
          }
          // skillspace
          const skillSpaceId = asString(so.skillSpaceId);
          const skillId = asString(so.skillId);
          if (!skillSpaceId || !skillId) continue;
          out.push({
            source,
            folder,
            name,
            description,
            skillSpaceId,
            skillSpaceName: asString(so.skillSpaceName),
            skillId,
            version: asString(so.version),
          });
        }
        return out;
      })(),
  };
}
