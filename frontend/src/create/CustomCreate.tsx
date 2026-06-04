import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  ArrowLeft,
  Bot,
  Boxes,
  Check,
  Cpu,
  Database,
  Eye,
  FileDown,
  Info,
  LayoutGrid,
  Layers,
  Loader2,
  Plus,
  Rocket,
  Search,
  Sparkles,
  Trash2,
  Wrench,
  X,
} from "lucide-react";
import {
  type CreateModeProps,
  type AgentDraft,
  type CustomTool,
  type McpTool,
  type SelectedSkill,
  emptyDraft,
} from "./types";
import {
  BUILTIN_TOOLS,
  STM_BACKENDS,
  LTM_BACKENDS,
  KB_BACKENDS,
  TRACING_EXPORTERS,
  type BackendOption,
} from "./veadkCatalog";
import { generateProject } from "./codegen";
import { draftToYaml } from "./configYaml";
import { searchSkills, downloadSkillFiles, type SkillHit } from "./skills";
import type { AgentProject } from "./project";
import { ProjectPreview } from "../ui/ProjectPreview";
import "./CustomCreate.css";

/** Trigger a browser download of a text file. */
function downloadText(filename: string, text: string, mime = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type: `${mime};charset=utf-8` }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/* ---------------------------------------------------------------- *
 * Step metadata. Each step renders its own form panel on the right;
 * the left rail shows progress + per-step completion checkmarks.
 * ---------------------------------------------------------------- */
type StepId =
  | "basic"
  | "model"
  | "tools"
  | "skills"
  | "memory"
  | "knowledge"
  | "tracing"
  | "subagents"
  | "review";

interface StepMeta {
  id: StepId;
  label: string;
  hint: string;
  icon: typeof Bot;
  required?: boolean;
}

const STEPS: StepMeta[] = [
  { id: "basic", label: "基本信息", hint: "名称、描述与系统提示词", icon: Info, required: true },
  { id: "model", label: "模型配置", hint: "模型与服务（可选）", icon: Cpu },
  { id: "tools", label: "工具", hint: "可调用的能力", icon: Wrench },
  { id: "skills", label: "技能", hint: "声明式技能", icon: Sparkles },
  { id: "memory", label: "记忆", hint: "短期 / 长期", icon: Layers },
  { id: "knowledge", label: "知识库", hint: "外部知识检索", icon: Database },
  { id: "tracing", label: "观测", hint: "Tracing 与 A2UI", icon: Eye },
  { id: "subagents", label: "子 Agent", hint: "嵌套协作", icon: Boxes },
  { id: "review", label: "完成", hint: "预览并创建", icon: Rocket },
];

const TOOL_PRESETS = [
  "web_search",
  "image_generate",
  "code_runner",
  "calculator",
  "file_reader",
];

/* ---------------------------------------------------------------- *
 * A small reusable "add many strings" editor (used by skills + the
 * sub-agent tool lists). Free-text input + preset chips + a list of
 * removable pills.
 * ---------------------------------------------------------------- */
function TagEditor({
  values,
  onChange,
  placeholder,
  presets,
}: {
  values: string[];
  onChange: (next: string[]) => void;
  placeholder: string;
  presets?: string[];
}) {
  const [text, setText] = useState("");

  const add = (raw: string) => {
    const v = raw.trim();
    if (!v || values.includes(v)) {
      setText("");
      return;
    }
    onChange([...values, v]);
    setText("");
  };

  const remove = (v: string) => onChange(values.filter((x) => x !== v));

  return (
    <div className="cw-tag-editor">
      <div className="cw-tag-inputrow">
        <input
          className="cw-input"
          value={text}
          placeholder={placeholder}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add(text);
            }
          }}
        />
        <button
          type="button"
          className="cw-btn cw-btn-soft"
          onClick={() => add(text)}
          disabled={!text.trim()}
        >
          <Plus className="cw-i" />
          添加
        </button>
      </div>

      {presets && presets.length > 0 && (
        <div className="cw-presets">
          <span className="cw-presets-label">推荐</span>
          {presets
            .filter((p) => !values.includes(p))
            .map((p) => (
              <button
                key={p}
                type="button"
                className="cw-chip cw-chip-ghost"
                onClick={() => add(p)}
              >
                <Plus className="cw-i cw-i-sm" />
                {p}
              </button>
            ))}
        </div>
      )}

      {values.length > 0 ? (
        <div className="cw-pills">
          <AnimatePresence initial={false}>
            {values.map((v) => (
              <motion.span
                key={v}
                className="cw-pill"
                layout
                initial={{ opacity: 0, scale: 0.85 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.85 }}
                transition={{ duration: 0.16 }}
              >
                {v}
                <button
                  type="button"
                  className="cw-pill-x"
                  onClick={() => remove(v)}
                  aria-label={`移除 ${v}`}
                >
                  <X className="cw-i cw-i-sm" />
                </button>
              </motion.span>
            ))}
          </AnimatePresence>
        </div>
      ) : (
        <p className="cw-empty-line">暂未添加，回车或点击「添加」即可加入。</p>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- *
 * Multi-select checklist. Each row = label + desc, toggling the id in
 * `selected`. Used for built-in tools and tracing exporters.
 * ---------------------------------------------------------------- */
interface ChecklistItem {
  id: string;
  label: string;
  desc: string;
}

function Checklist({
  items,
  selected,
  onToggle,
}: {
  items: ChecklistItem[];
  selected: string[];
  onToggle: (id: string) => void;
}) {
  return (
    <div className="cw-checklist">
      {items.map((it) => {
        const on = selected.includes(it.id);
        return (
          <button
            key={it.id}
            type="button"
            className={`cw-check ${on ? "is-on" : ""}`}
            onClick={() => onToggle(it.id)}
            aria-pressed={on}
          >
            <span className="cw-check-box" aria-hidden>
              {on && <Check className="cw-i cw-i-sm" />}
            </span>
            <span className="cw-check-text">
              <span className="cw-check-title">{it.label}</span>
              <span className="cw-check-desc">{it.desc}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

/* ---------------------------------------------------------------- *
 * Segmented backend picker. Renders BackendOption[] as a wrapping row
 * of selectable cards; one active at a time.
 * ---------------------------------------------------------------- */
function BackendSelect({
  options,
  value,
  onChange,
}: {
  options: BackendOption[];
  value: string | undefined;
  onChange: (id: string) => void;
}) {
  return (
    <div className="cw-segmented">
      {options.map((o) => {
        const on = (value ?? options[0]?.id) === o.id;
        return (
          <button
            key={o.id}
            type="button"
            className={`cw-seg ${on ? "is-on" : ""}`}
            onClick={() => onChange(o.id)}
            aria-pressed={on}
            title={o.desc}
          >
            <span className="cw-seg-title">{o.label}</span>
            <span className="cw-seg-desc">{o.desc}</span>
          </button>
        );
      })}
    </div>
  );
}

/* ---------------------------------------------------------------- *
 * Custom function-tool editor: add {name, description} rows. Name is
 * required; description optional. Rows are removable.
 * ---------------------------------------------------------------- */
function CustomToolEditor({
  tools,
  onChange,
}: {
  tools: CustomTool[];
  onChange: (next: CustomTool[]) => void;
}) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");

  const add = () => {
    const n = name.trim();
    if (!n) return;
    onChange([...tools, { name: n, description: desc.trim() }]);
    setName("");
    setDesc("");
  };

  const remove = (i: number) => onChange(tools.filter((_, idx) => idx !== i));

  return (
    <div className="cw-ctool">
      <div className="cw-ctool-inputs">
        <input
          className="cw-input"
          value={name}
          placeholder="函数名，例如 lookup_order"
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <input
          className="cw-input"
          value={desc}
          placeholder="描述（可选）：这个工具做什么"
          onChange={(e) => setDesc(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <button
          type="button"
          className="cw-btn cw-btn-soft"
          onClick={add}
          disabled={!name.trim()}
        >
          <Plus className="cw-i" />
          添加
        </button>
      </div>

      {tools.length > 0 ? (
        <div className="cw-ctool-list">
          <AnimatePresence initial={false}>
            {tools.map((t, i) => (
              <motion.div
                key={`${t.name}-${i}`}
                className="cw-ctool-row"
                layout
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.16 }}
              >
                <span className="cw-ctool-icon" aria-hidden>
                  <Wrench className="cw-i cw-i-sm" />
                </span>
                <span className="cw-ctool-meta">
                  <span className="cw-ctool-name">{t.name}</span>
                  {t.description && (
                    <span className="cw-ctool-desc">{t.description}</span>
                  )}
                </span>
                <button
                  type="button"
                  className="cw-icon-btn cw-icon-danger"
                  onClick={() => remove(i)}
                  aria-label={`移除 ${t.name}`}
                >
                  <Trash2 className="cw-i cw-i-sm" />
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      ) : (
        <p className="cw-empty-line">暂无自定义函数工具，生成时会为每个工具创建可运行的桩函数。</p>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- *
 * MCP tool editor: edits draft.mcpTools. Each row picks a transport
 * (http / stdio) and shows the matching fields. http -> url + optional
 * bearer token; stdio -> command + space-separated args. Optional name.
 * ---------------------------------------------------------------- */
function McpToolEditor({
  tools,
  onChange,
}: {
  tools: McpTool[];
  onChange: (next: McpTool[]) => void;
}) {
  const update = (i: number, p: Partial<McpTool>) =>
    onChange(tools.map((t, idx) => (idx === i ? { ...t, ...p } : t)));

  const remove = (i: number) => onChange(tools.filter((_, idx) => idx !== i));

  const add = () =>
    onChange([...tools, { name: "", transport: "http", url: "" }]);

  return (
    <div className="cw-mcp">
      {tools.length > 0 && (
        <div className="cw-mcp-list">
          <AnimatePresence initial={false}>
            {tools.map((t, i) => (
              <motion.div
                key={i}
                className="cw-mcp-row"
                layout
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.16 }}
              >
                <div className="cw-mcp-rowhead">
                  <div className="cw-mcp-transport">
                    <button
                      type="button"
                      className={`cw-seg cw-seg-sm ${
                        t.transport === "http" ? "is-on" : ""
                      }`}
                      onClick={() => update(i, { transport: "http" })}
                      aria-pressed={t.transport === "http"}
                    >
                      <span className="cw-seg-title">HTTP</span>
                    </button>
                    <button
                      type="button"
                      className={`cw-seg cw-seg-sm ${
                        t.transport === "stdio" ? "is-on" : ""
                      }`}
                      onClick={() => update(i, { transport: "stdio" })}
                      aria-pressed={t.transport === "stdio"}
                    >
                      <span className="cw-seg-title">stdio</span>
                    </button>
                  </div>
                  <button
                    type="button"
                    className="cw-icon-btn cw-icon-danger"
                    onClick={() => remove(i)}
                    aria-label="移除 MCP 工具"
                  >
                    <Trash2 className="cw-i cw-i-sm" />
                  </button>
                </div>

                <input
                  className="cw-input"
                  value={t.name}
                  placeholder="名称（用于命名，可留空）"
                  onChange={(e) => update(i, { name: e.target.value })}
                />

                {t.transport === "http" ? (
                  <>
                    <input
                      className="cw-input"
                      value={t.url ?? ""}
                      placeholder="MCP 服务地址（StreamableHTTP）"
                      onChange={(e) => update(i, { url: e.target.value })}
                    />
                    <input
                      className="cw-input"
                      value={t.authToken ?? ""}
                      placeholder="Bearer Token（可选）"
                      onChange={(e) => update(i, { authToken: e.target.value })}
                    />
                  </>
                ) : (
                  <>
                    <input
                      className="cw-input"
                      value={t.command ?? ""}
                      placeholder="启动命令，例如 npx"
                      onChange={(e) => update(i, { command: e.target.value })}
                    />
                    <input
                      className="cw-input"
                      value={(t.args ?? []).join(" ")}
                      placeholder="参数（用空格分隔），例如 -y @playwright/mcp@latest"
                      onChange={(e) =>
                        update(i, {
                          args: e.target.value.split(/\s+/).filter(Boolean),
                        })
                      }
                    />
                  </>
                )}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      <button type="button" className="cw-add-sub" onClick={add}>
        <Plus className="cw-i" />
        添加 MCP 工具
      </button>

      {tools.length === 0 && (
        <p className="cw-empty-line">
          暂无 MCP 工具，点击「添加 MCP 工具」连接外部 MCP 服务。
        </p>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- *
 * Skill Hub search + select. Searches the skill hub (skills.ts) and
 * lets the user toggle results into draft.selectedSkills (de-duped by
 * slug). Selected skills show as removable rows above the results.
 * ---------------------------------------------------------------- */
function SkillHubPicker({
  selected,
  onChange,
}: {
  selected: SelectedSkill[];
  onChange: (next: SelectedSkill[]) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SkillHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const isSelected = (slug: string) => selected.some((s) => s.slug === slug);

  const toggle = (hit: SkillHit) => {
    if (isSelected(hit.slug)) {
      onChange(selected.filter((s) => s.slug !== hit.slug));
    } else {
      onChange([
        ...selected,
        { slug: hit.slug, name: hit.name, namespace: hit.namespace },
      ]);
    }
  };

  const removeSelected = (slug: string) =>
    onChange(selected.filter((s) => s.slug !== slug));

  const runSearch = async (q: string) => {
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const hits = await searchSkills(q);
      setResults(hits);
    } catch (e) {
      setError(e instanceof Error ? e.message : "搜索失败，请稍后重试。");
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  // Debounce typing ~300ms; also searches on Enter / button via runSearch.
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      setSearched(false);
      setError(null);
      return;
    }
    const t = setTimeout(() => runSearch(q), 300);
    return () => clearTimeout(t);
  }, [query]);

  return (
    <div className="cw-skillhub">
      <div className="cw-skill-searchrow">
        <div className="cw-skill-searchbox">
          <Search className="cw-i cw-skill-searchicon" aria-hidden />
          <input
            className="cw-input cw-skill-input"
            value={query}
            placeholder="搜索 Skill Hub，例如 数据分析、PDF…"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                if (query.trim()) runSearch(query);
              }
            }}
          />
        </div>
        <button
          type="button"
          className="cw-btn cw-btn-soft"
          onClick={() => query.trim() && runSearch(query)}
          disabled={!query.trim() || loading}
        >
          {loading ? (
            <Loader2 className="cw-i cw-spin" />
          ) : (
            <Search className="cw-i" />
          )}
          搜索
        </button>
      </div>

      {selected.length > 0 && (
        <div className="cw-skill-selected">
          <span className="cw-skill-selected-label">已选技能</span>
          <div className="cw-pills">
            <AnimatePresence initial={false}>
              {selected.map((s) => (
                <motion.span
                  key={s.slug}
                  className="cw-pill"
                  layout
                  initial={{ opacity: 0, scale: 0.85 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.85 }}
                  transition={{ duration: 0.16 }}
                >
                  <Sparkles className="cw-i cw-i-sm" />
                  {s.name}
                  <button
                    type="button"
                    className="cw-pill-x"
                    onClick={() => removeSelected(s.slug)}
                    aria-label={`移除 ${s.name}`}
                  >
                    <X className="cw-i cw-i-sm" />
                  </button>
                </motion.span>
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      {error && (
        <div className="cw-banner">
          <Info className="cw-i" />
          <span>{error}</span>
        </div>
      )}

      {loading && results.length === 0 ? (
        <p className="cw-empty-line">正在搜索…</p>
      ) : results.length > 0 ? (
        <div className="cw-skill-results">
          {results.map((hit) => {
            const on = isSelected(hit.slug);
            return (
              <button
                key={hit.id || hit.slug}
                type="button"
                className={`cw-skill-result ${on ? "is-on" : ""}`}
                onClick={() => toggle(hit)}
                aria-pressed={on}
              >
                <span className="cw-skill-result-icon" aria-hidden>
                  {on ? (
                    <Check className="cw-i cw-i-sm" />
                  ) : (
                    <Plus className="cw-i cw-i-sm" />
                  )}
                </span>
                <span className="cw-skill-result-meta">
                  <span className="cw-skill-result-name">{hit.name}</span>
                  {hit.description && (
                    <span className="cw-skill-result-desc">
                      {hit.description}
                    </span>
                  )}
                  {hit.sourceRepo && (
                    <span className="cw-skill-result-repo">
                      {hit.sourceRepo}
                    </span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      ) : searched && !error ? (
        <p className="cw-empty-line">没有找到匹配的技能，换个关键词试试。</p>
      ) : (
        !searched && (
          <p className="cw-empty-line">
            输入关键词以搜索 Skill Hub，所选技能会在生成项目时下载到 skills/ 目录。
          </p>
        )
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- *
 * Toggle switch row.
 * ---------------------------------------------------------------- */
function Toggle({
  checked,
  onChange,
  title,
  desc,
  icon: Icon,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  title: string;
  desc: string;
  icon: typeof Bot;
}) {
  return (
    <button
      type="button"
      className={`cw-toggle ${checked ? "is-on" : ""}`}
      onClick={() => onChange(!checked)}
      aria-pressed={checked}
    >
      <span className="cw-toggle-icon">
        <Icon className="cw-i" />
      </span>
      <span className="cw-toggle-text">
        <span className="cw-toggle-title">{title}</span>
        <span className="cw-toggle-desc">{desc}</span>
      </span>
      <span className="cw-switch" aria-hidden>
        <motion.span
          className="cw-switch-knob"
          layout
          transition={{ type: "spring", stiffness: 520, damping: 34 }}
        />
      </span>
    </button>
  );
}

/* ---------------------------------------------------------------- *
 * A compact inline editor for one sub-agent. Recursive-friendly: it
 * edits the same core AgentDraft fields, so it could nest deeper.
 * ---------------------------------------------------------------- */
function SubAgentEditor({
  draft,
  index,
  onChange,
  onRemove,
}: {
  draft: AgentDraft;
  index: number;
  onChange: (next: AgentDraft) => void;
  onRemove: () => void;
}) {
  const patch = (p: Partial<AgentDraft>) => onChange({ ...draft, ...p });

  return (
    <motion.div
      className="cw-sub"
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.18 }}
    >
      <div className="cw-sub-head">
        <span className="cw-sub-badge">
          <Bot className="cw-i cw-i-sm" />
          子 Agent {index + 1}
        </span>
        <button
          type="button"
          className="cw-icon-btn cw-icon-danger"
          onClick={onRemove}
          aria-label="删除子 Agent"
        >
          <Trash2 className="cw-i cw-i-sm" />
        </button>
      </div>

      <div className="cw-field">
        <label className="cw-label">
          名称<span className="cw-req">*</span>
        </label>
        <input
          className="cw-input"
          value={draft.name}
          placeholder="例如：检索助手"
          onChange={(e) => patch({ name: e.target.value })}
        />
      </div>

      <div className="cw-field">
        <label className="cw-label">描述</label>
        <input
          className="cw-input"
          value={draft.description}
          placeholder="一句话说明它负责什么"
          onChange={(e) => patch({ description: e.target.value })}
        />
      </div>

      <div className="cw-field">
        <label className="cw-label">
          系统提示词<span className="cw-req">*</span>
        </label>
        <textarea
          className="cw-textarea cw-textarea-sm"
          value={draft.instruction}
          placeholder="定义这个子 Agent 的角色与行为…"
          onChange={(e) => patch({ instruction: e.target.value })}
        />
      </div>

      <div className="cw-field">
        <label className="cw-label">工具</label>
        <TagEditor
          values={draft.tools}
          onChange={(tools) => patch({ tools })}
          placeholder="为子 Agent 添加工具…"
          presets={TOOL_PRESETS}
        />
      </div>
    </motion.div>
  );
}

/* ---------------------------------------------------------------- *
 * Review row helpers.
 * ---------------------------------------------------------------- */
function ReviewRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="cw-review-row">
      <span className="cw-review-key">{label}</span>
      <div className="cw-review-val">{children}</div>
    </div>
  );
}

function boolTag(on: boolean) {
  return (
    <span className={`cw-tag ${on ? "cw-tag-on" : "cw-tag-off"}`}>
      {on ? "已开启" : "未开启"}
    </span>
  );
}

const labelOf = (
  options: { id: string; label: string }[],
  id: string | undefined,
) => options.find((o) => o.id === id)?.label ?? id ?? "—";

/* ================================================================ *
 * Main component
 * ================================================================ */
interface CustomCreateProps extends CreateModeProps {
  /** Pre-fill the wizard (used when importing an agent-structure YAML). */
  initialDraft?: AgentDraft;
}

export function CustomCreate({ onBack, onCreate, initialDraft }: CustomCreateProps) {
  void onCreate; // outcome is the in-pane project preview, not a navigation
  void onBack; // no footer nav in the single-scroll layout; back lives in app chrome
  const [draft, setDraft] = useState<AgentDraft>(() => initialDraft ?? emptyDraft());
  const [showErrors, setShowErrors] = useState(false);
  const [project, setProject] = useState<AgentProject | null>(null);
  const [building, setBuilding] = useState(false);

  // Scroll-spy: which section is currently in view.
  const [activeId, setActiveId] = useState<StepId>(STEPS[0].id);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const sectionRefs = useRef<Partial<Record<StepId, HTMLElement | null>>>({});

  const patch = (p: Partial<AgentDraft>) => setDraft((d) => ({ ...d, ...p }));

  const builtinTools = draft.builtinTools ?? [];
  const customTools = draft.customTools ?? [];
  const mcpTools = draft.mcpTools ?? [];
  const tracingExporters = draft.tracingExporters ?? [];

  const toggleBuiltin = (id: string) =>
    patch({
      builtinTools: builtinTools.includes(id)
        ? builtinTools.filter((x) => x !== id)
        : [...builtinTools, id],
    });

  const toggleExporter = (id: string) => {
    const next = tracingExporters.includes(id)
      ? tracingExporters.filter((x) => x !== id)
      : [...tracingExporters, id];
    // Auto-enable tracing when at least one exporter is chosen.
    patch({ tracingExporters: next, tracing: next.length > 0 ? true : draft.tracing });
  };

  // Required-field validation: name + instruction.
  const nameMissing = draft.name.trim().length === 0;
  const instructionMissing = draft.instruction.trim().length === 0;
  const canFinish = !nameMissing && !instructionMissing;

  // Per-step completion for the left-rail checkmarks.
  const selectedSkills = draft.selectedSkills ?? [];

  const completion: Record<StepId, boolean> = useMemo(
    () => ({
      basic: !nameMissing && !instructionMissing,
      model: Boolean(
        draft.modelName?.trim() ||
          draft.modelProvider?.trim() ||
          draft.modelApiBase?.trim(),
      ),
      tools: builtinTools.length > 0 || customTools.length > 0 || mcpTools.length > 0,
      skills: selectedSkills.length > 0,
      memory: draft.memory.shortTerm || draft.memory.longTerm,
      knowledge: draft.knowledgebase,
      tracing: draft.tracing || draft.enableA2ui,
      subagents: draft.subAgents.length > 0,
      review: canFinish,
    }),
    [draft, nameMissing, instructionMissing, canFinish, builtinTools, customTools, mcpTools, selectedSkills],
  );

  const activeIndex = STEPS.findIndex((s) => s.id === activeId);

  // Smooth-scroll a section into view (rail click is a convenience).
  const scrollToSection = (id: StepId) => {
    sectionRefs.current[id]?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  // Scroll-spy: mark the section nearest the top of the scroll container as
  // active. rootMargin pushes the activation line into the upper area so a
  // section becomes active once it reaches the top ~35% of the viewport.
  useEffect(() => {
    if (project) return; // observer targets only exist in the form view
    const root = scrollRef.current;
    if (!root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length > 0) {
          const id = (visible[0].target as HTMLElement).dataset.stepId as
            | StepId
            | undefined;
          if (id) setActiveId(id);
        }
      },
      { root, rootMargin: "0px 0px -65% 0px", threshold: 0 },
    );
    for (const el of Object.values(sectionRefs.current)) {
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [project]);

  const finish = async () => {
    if (!canFinish) {
      setShowErrors(true);
      // Required name + instruction both live in the basic section.
      scrollToSection("basic");
      return;
    }
    // NOTE: do NOT call onCreate() here — it navigates away from the create
    // view. The generated project preview below IS the outcome of this step.

    const proj = generateProject(draft);

    // Pull in any Skill Hub selections, downloading their files in parallel.
    // Per-skill failures are skipped so one bad skill can't abort the build.
    if (selectedSkills.length > 0) {
      setBuilding(true);
      try {
        const results = await Promise.all(
          selectedSkills.map((s) =>
            downloadSkillFiles(s.slug, s.namespace).catch((err) => {
              console.warn(`下载技能失败：${s.name}`, err);
              return [];
            }),
          ),
        );
        const existing = new Set(proj.files.map((f) => f.path));
        for (const files of results) {
          for (const f of files) {
            // Generated files win on collision (unlikely — skills live under skills/).
            if (!existing.has(f.path)) {
              proj.files.push(f);
              existing.add(f.path);
            }
          }
        }
      } finally {
        setBuilding(false);
      }
    }

    setProject(proj);
  };

  // Sub-agent mutators.
  const addSubAgent = () =>
    patch({ subAgents: [...draft.subAgents, emptyDraft()] });
  const updateSubAgent = (i: number, next: AgentDraft) =>
    patch({
      subAgents: draft.subAgents.map((s, idx) => (idx === i ? next : s)),
    });
  const removeSubAgent = (i: number) =>
    patch({ subAgents: draft.subAgents.filter((_, idx) => idx !== i) });

  // ----------------------------------------------------------------
  // Preview mode: takes over the whole pane, hiding the wizard chrome.
  // ----------------------------------------------------------------
  if (project) {
    return (
      <div className="cw-root cw-root-preview">
        <div className="cw-preview-bar">
          <button
            type="button"
            className="cw-btn cw-btn-ghost"
            onClick={() => setProject(null)}
          >
            <ArrowLeft className="cw-i" />
            返回配置
          </button>
          <span className="cw-preview-title">
            <Rocket className="cw-i" />
            项目预览 · {project.name}
          </span>
          <button
            type="button"
            className="cw-btn cw-btn-soft cw-preview-yaml"
            onClick={() =>
              downloadText(`${draft.name || "agent"}.yaml`, draftToYaml(draft), "text/yaml")
            }
            title="导出表示 Agent 结构的 YAML"
          >
            <FileDown className="cw-i" />
            导出 YAML
          </button>
        </div>
        <div className="cw-preview-body">
          <ProjectPreview project={project} onChange={setProject} />
        </div>
      </div>
    );
  }

  // Section wrapper: registers a ref for scroll-spy + renders the heading.
  // IMPORTANT: keep a STABLE identity (stored in a ref). If this were declared
  // as a fresh function each render, React would remount every section on every
  // keystroke — detaching the nodes the IntersectionObserver watches (breaking
  // the scroll-spy) and dropping input focus.
  const sectionImpl = useRef<
    ((p: { meta: StepMeta; children: React.ReactNode }) => React.ReactElement) | null
  >(null);
  if (!sectionImpl.current) {
    sectionImpl.current = ({ meta, children }) => (
      <section
        ref={(el) => {
          sectionRefs.current[meta.id] = el;
        }}
        id={`cw-sec-${meta.id}`}
        data-step-id={meta.id}
        className="cw-section"
      >
        <header className="cw-sec-head">
          <h2 className="cw-sec-title">
            {meta.label}
            {meta.required && <span className="cw-sec-required">必填</span>}
          </h2>
          <p className="cw-sec-hint">{meta.hint}</p>
        </header>
        {children}
      </section>
    );
  }
  const Section = sectionImpl.current;

  const metaOf = (id: StepId) => STEPS.find((s) => s.id === id)!;

  return (
    <div className="cw-root">
      {/* Scroll container (IntersectionObserver root). Centers the
          [form column + rail] group as one unit. */}
      <div className="cw-body" ref={scrollRef}>
        <div className="cw-center">
          {/* Form column: all sections stacked */}
          <div className="cw-form-col">
            <Section meta={metaOf("basic")}>
                <div className="cw-form">
                    <div className="cw-field">
                      <label className="cw-label">
                        Agent 名称<span className="cw-req">*</span>
                      </label>
                      <input
                        className={`cw-input ${
                          showErrors && nameMissing ? "is-error" : ""
                        }`}
                        value={draft.name}
                        placeholder="例如：客服智能体"
                        onChange={(e) => patch({ name: e.target.value })}
                        autoFocus
                      />
                      {showErrors && nameMissing && (
                        <span className="cw-error-text">名称为必填项</span>
                      )}
                    </div>
                    <div className="cw-field">
                      <label className="cw-label">描述</label>
                      <textarea
                        className="cw-textarea cw-textarea-sm"
                        value={draft.description}
                        placeholder="简要描述这个 Agent 的用途，便于团队识别…"
                        onChange={(e) =>
                          patch({ description: e.target.value })
                        }
                      />
                      <span className="cw-help">
                        描述会显示在 Agent 列表与选择器中。
                      </span>
                    </div>
                    <div className="cw-field">
                      <label className="cw-label">
                        系统提示词<span className="cw-req">*</span>
                      </label>
                      <textarea
                        className={`cw-textarea cw-textarea-lg ${
                          showErrors && instructionMissing ? "is-error" : ""
                        }`}
                        value={draft.instruction}
                        placeholder={
                          "你是一个……\n\n你的目标是……\n\n约束：\n- ……"
                        }
                        onChange={(e) =>
                          patch({ instruction: e.target.value })
                        }
                      />
                      {showErrors && instructionMissing ? (
                        <span className="cw-error-text">
                          系统提示词为必填项
                        </span>
                      ) : (
                        <span className="cw-help">
                          定义 Agent 的角色、目标与行为边界，这是最关键的一步。
                        </span>
                      )}
                    </div>
                  </div>
            </Section>

            <Section meta={metaOf("model")}>
                  <div className="cw-form">
                    <div className="cw-field">
                      <label className="cw-label">模型名称</label>
                      <input
                        className="cw-input"
                        value={draft.modelName ?? ""}
                        placeholder="doubao-seed-1-6-250615"
                        onChange={(e) => patch({ modelName: e.target.value })}
                      />
                    </div>
                    <div className="cw-field">
                      <label className="cw-label">服务商 Provider</label>
                      <input
                        className="cw-input"
                        value={draft.modelProvider ?? ""}
                        placeholder="openai"
                        onChange={(e) =>
                          patch({ modelProvider: e.target.value })
                        }
                      />
                    </div>
                    <div className="cw-field">
                      <label className="cw-label">API Base</label>
                      <input
                        className="cw-input"
                        value={draft.modelApiBase ?? ""}
                        placeholder="https://ark.cn-beijing.volces.com/api/v3/"
                        onChange={(e) =>
                          patch({ modelApiBase: e.target.value })
                        }
                      />
                      <span className="cw-help">
                        留空则使用 VeADK 默认模型配置；API Key 请在生成项目的
                        .env.example 中填写（不会写入代码）。
                      </span>
                    </div>
                  </div>
            </Section>

            <Section meta={metaOf("tools")}>
                  <div className="cw-form">
                    <div className="cw-field">
                      <label className="cw-label">内置工具</label>
                      <span className="cw-help">
                        勾选 VeADK 提供的内置能力，生成时会自动补全 import 与所需环境变量。
                      </span>
                      <Checklist
                        items={BUILTIN_TOOLS}
                        selected={builtinTools}
                        onToggle={toggleBuiltin}
                      />
                    </div>
                    <div className="cw-field">
                      <label className="cw-label">自定义函数工具</label>
                      <span className="cw-help">
                        添加你自己的函数工具，生成的 agent.py 会为每个工具创建可运行的桩函数。
                      </span>
                      <CustomToolEditor
                        tools={customTools}
                        onChange={(next) => patch({ customTools: next })}
                      />
                    </div>
                    <div className="cw-field">
                      <label className="cw-label">MCP 工具</label>
                      <span className="cw-help">
                        连接外部 MCP 服务，生成时会为每个条目创建对应的 MCPToolset。
                      </span>
                      <McpToolEditor
                        tools={mcpTools}
                        onChange={(next) => patch({ mcpTools: next })}
                      />
                    </div>
                  </div>
            </Section>

            <Section meta={metaOf("skills")}>
                  <div className="cw-form">
                    <p className="cw-section-desc">
                      从 Skill Hub 搜索并选择技能，生成项目时会自动下载到
                      skills/ 目录。
                    </p>
                    <SkillHubPicker
                      selected={selectedSkills}
                      onChange={(next) => patch({ selectedSkills: next })}
                    />
                  </div>
            </Section>

            <Section meta={metaOf("memory")}>
                  <div className="cw-form cw-toggle-stack">
                    <Toggle
                      checked={draft.memory.shortTerm}
                      onChange={(v) =>
                        patch({
                          memory: { ...draft.memory, shortTerm: v },
                        })
                      }
                      title="短期记忆"
                      desc="在单次会话内保留上下文，跨轮次记住对话内容。"
                      icon={Layers}
                    />
                    {draft.memory.shortTerm && (
                      <div className="cw-field cw-subfield">
                        <label className="cw-label">短期记忆后端</label>
                        <BackendSelect
                          options={STM_BACKENDS}
                          value={draft.shortTermBackend}
                          onChange={(id) => patch({ shortTermBackend: id })}
                        />
                      </div>
                    )}
                    <Toggle
                      checked={draft.memory.longTerm}
                      onChange={(v) =>
                        patch({
                          memory: { ...draft.memory, longTerm: v },
                        })
                      }
                      title="长期记忆"
                      desc="跨会话持久化关键信息，让 Agent 记住历史偏好。"
                      icon={Database}
                    />
                    {draft.memory.longTerm && (
                      <div className="cw-field cw-subfield">
                        <label className="cw-label">长期记忆后端</label>
                        <BackendSelect
                          options={LTM_BACKENDS}
                          value={draft.longTermBackend}
                          onChange={(id) => patch({ longTermBackend: id })}
                        />
                        <Toggle
                          checked={!!draft.autoSaveSession}
                          onChange={(v) => patch({ autoSaveSession: v })}
                          title="自动保存会话到长期记忆"
                          desc="会话结束时自动把内容写入长期记忆，无需手动调用。"
                          icon={Database}
                        />
                      </div>
                    )}
                  </div>
            </Section>

            <Section meta={metaOf("knowledge")}>
                  <div className="cw-form cw-toggle-stack">
                    <Toggle
                      checked={draft.knowledgebase}
                      onChange={(v) => patch({ knowledgebase: v })}
                      title="知识库"
                      desc="启用外部知识检索（RAG），让 Agent 基于你的资料作答。"
                      icon={Database}
                    />
                    {draft.knowledgebase && (
                      <div className="cw-field cw-subfield">
                        <label className="cw-label">知识库后端</label>
                        <BackendSelect
                          options={KB_BACKENDS}
                          value={draft.knowledgebaseBackend}
                          onChange={(id) =>
                            patch({ knowledgebaseBackend: id })
                          }
                        />
                      </div>
                    )}
                  </div>
            </Section>

            <Section meta={metaOf("tracing")}>
                  <div className="cw-form cw-toggle-stack">
                    <Toggle
                      checked={draft.tracing}
                      onChange={(v) => patch({ tracing: v })}
                      title="观测 / Tracing"
                      desc="记录每一步的调用链路与耗时，便于调试与性能分析。"
                      icon={Eye}
                    />
                    {draft.tracing && (
                      <div className="cw-field cw-subfield">
                        <label className="cw-label">Tracing 导出器</label>
                        <span className="cw-help">
                          选择一个或多个观测平台，生成时会写入对应的 ENABLE_* 开关与环境变量。
                        </span>
                        <Checklist
                          items={TRACING_EXPORTERS}
                          selected={tracingExporters}
                          onToggle={toggleExporter}
                        />
                      </div>
                    )}
                    <Toggle
                      checked={draft.enableA2ui}
                      onChange={(v) => patch({ enableA2ui: v })}
                      title="A2UI"
                      desc="允许 Agent 渲染交互式 UI 卡片，而不仅仅是纯文本。"
                      icon={LayoutGrid}
                    />
                  </div>
            </Section>

            <Section meta={metaOf("subagents")}>
                  <div className="cw-form">
                    <p className="cw-section-desc">
                      添加协作的子 Agent，每个子 Agent 拥有独立的提示词与工具，可被主 Agent 调度。
                    </p>
                    <div className="cw-sub-list">
                      <AnimatePresence initial={false}>
                        {draft.subAgents.map((sa, i) => (
                          <SubAgentEditor
                            key={i}
                            draft={sa}
                            index={i}
                            onChange={(next) => updateSubAgent(i, next)}
                            onRemove={() => removeSubAgent(i)}
                          />
                        ))}
                      </AnimatePresence>
                    </div>
                    <button
                      type="button"
                      className="cw-add-sub"
                      onClick={addSubAgent}
                    >
                      <Plus className="cw-i" />
                      添加子 Agent
                    </button>
                    {draft.subAgents.length === 0 && (
                      <p className="cw-empty-line">
                        子 Agent 是可选的，留空即可创建一个独立 Agent。
                      </p>
                    )}
                  </div>
            </Section>

            <Section meta={metaOf("review")}>
                  <div className="cw-form">
                    {!canFinish && (
                      <div className="cw-banner">
                        <Info className="cw-i" />
                        <span>
                          请先补全必填项：
                          {nameMissing && "「名称」"}
                          {nameMissing && instructionMissing && "、"}
                          {instructionMissing && "「系统提示词」"}。
                        </span>
                      </div>
                    )}
                    <div className="cw-review">
                      <ReviewRow label="名称">
                        {draft.name.trim() ? (
                          <span className="cw-review-strong">
                            {draft.name}
                          </span>
                        ) : (
                          <span className="cw-review-muted">未填写</span>
                        )}
                      </ReviewRow>
                      <ReviewRow label="描述">
                        {draft.description.trim() || (
                          <span className="cw-review-muted">无</span>
                        )}
                      </ReviewRow>
                      <ReviewRow label="系统提示词">
                        {draft.instruction.trim() ? (
                          <pre className="cw-review-pre">
                            {draft.instruction}
                          </pre>
                        ) : (
                          <span className="cw-review-muted">未填写</span>
                        )}
                      </ReviewRow>
                      <ReviewRow label="内置工具">
                        {builtinTools.length ? (
                          <div className="cw-review-chips">
                            {builtinTools.map((id) => (
                              <span key={id} className="cw-chip">
                                {labelOf(BUILTIN_TOOLS, id)}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="cw-review-muted">无</span>
                        )}
                      </ReviewRow>
                      <ReviewRow label="自定义工具">
                        {customTools.length ? (
                          <div className="cw-review-chips">
                            {customTools.map((t, i) => (
                              <span key={`${t.name}-${i}`} className="cw-chip">
                                {t.name}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="cw-review-muted">无</span>
                        )}
                      </ReviewRow>
                      <ReviewRow label="模型">
                        {draft.modelName?.trim() ||
                        draft.modelProvider?.trim() ||
                        draft.modelApiBase?.trim() ? (
                          <span className="cw-review-muted">
                            {[
                              draft.modelName?.trim(),
                              draft.modelProvider?.trim(),
                              draft.modelApiBase?.trim(),
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        ) : (
                          <span className="cw-review-muted">默认配置</span>
                        )}
                      </ReviewRow>
                      <ReviewRow label="MCP 工具">
                        {mcpTools.length ? (
                          <div className="cw-review-chips">
                            {mcpTools.map((t, i) => (
                              <span key={i} className="cw-chip">
                                {t.name.trim() ||
                                  (t.transport === "http"
                                    ? t.url || "http"
                                    : t.command || "stdio")}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="cw-review-muted">无</span>
                        )}
                      </ReviewRow>
                      <ReviewRow label="技能">
                        {selectedSkills.length ? (
                          <div className="cw-review-chips">
                            {selectedSkills.map((s) => (
                              <span key={s.slug} className="cw-chip">
                                {s.name}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="cw-review-muted">无</span>
                        )}
                      </ReviewRow>
                      <ReviewRow label="短期记忆">
                        {draft.memory.shortTerm ? (
                          <span>
                            {boolTag(true)}{" "}
                            <span className="cw-review-muted">
                              · {labelOf(STM_BACKENDS, draft.shortTermBackend)}
                            </span>
                          </span>
                        ) : (
                          boolTag(false)
                        )}
                      </ReviewRow>
                      <ReviewRow label="长期记忆">
                        {draft.memory.longTerm ? (
                          <span>
                            {boolTag(true)}{" "}
                            <span className="cw-review-muted">
                              · {labelOf(LTM_BACKENDS, draft.longTermBackend)}
                              {draft.autoSaveSession ? " · 自动保存会话" : ""}
                            </span>
                          </span>
                        ) : (
                          boolTag(false)
                        )}
                      </ReviewRow>
                      <ReviewRow label="知识库">
                        {draft.knowledgebase ? (
                          <span>
                            {boolTag(true)}{" "}
                            <span className="cw-review-muted">
                              · {labelOf(KB_BACKENDS, draft.knowledgebaseBackend)}
                            </span>
                          </span>
                        ) : (
                          boolTag(false)
                        )}
                      </ReviewRow>
                      <ReviewRow label="观测 / Tracing">
                        {draft.tracing ? (
                          <span>
                            {boolTag(true)}
                            {tracingExporters.length > 0 && (
                              <span className="cw-review-muted">
                                {" "}
                                ·{" "}
                                {tracingExporters
                                  .map((id) => labelOf(TRACING_EXPORTERS, id))
                                  .join("、")}
                              </span>
                            )}
                          </span>
                        ) : (
                          boolTag(false)
                        )}
                      </ReviewRow>
                      <ReviewRow label="A2UI">
                        {boolTag(draft.enableA2ui)}
                      </ReviewRow>
                      <ReviewRow label="子 Agent">
                        {draft.subAgents.length ? (
                          <div className="cw-review-subs">
                            {draft.subAgents.map((sa, i) => (
                              <span key={i} className="cw-chip cw-chip-sub">
                                <Bot className="cw-i cw-i-sm" />
                                {sa.name.trim() || `子 Agent ${i + 1}`}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="cw-review-muted">无</span>
                        )}
                      </ReviewRow>
                    </div>
                    <div className="cw-finish-actions">
                      <button
                        type="button"
                        className="cw-btn cw-btn-primary cw-btn-finish"
                        onClick={finish}
                        disabled={!canFinish || building}
                      >
                        {building ? (
                          <>
                            <Loader2 className="cw-i cw-spin" />
                            正在下载技能…
                          </>
                        ) : (
                          <>
                            <Rocket className="cw-i" />
                            生成项目
                          </>
                        )}
                      </button>
                    </div>
                  </div>
            </Section>
          </div>

          {/* Right rail: scroll-spy step indicator */}
          <nav className="cw-rail" aria-label="步骤导航">
            <ol className="cw-steps">
              {/* Connector line + progress fill, anchored to the steps list so
                  it runs exactly through the dot column from first to last dot.
                  Fill reflects progress to the active (in-view) section. */}
              <div className="cw-rail-track" aria-hidden>
                <motion.div
                  className="cw-rail-fill"
                  animate={{
                    height: `${
                      (Math.max(activeIndex, 0) / (STEPS.length - 1)) * 100
                    }%`,
                  }}
                  transition={{ type: "spring", stiffness: 260, damping: 32 }}
                />
              </div>
              {STEPS.map((s) => {
                const active = s.id === activeId;
                const done = completion[s.id];
                return (
                  <li key={s.id}>
                    <button
                      type="button"
                      className={`cw-step ${active ? "is-active" : ""} ${
                        done ? "is-done" : ""
                      }`}
                      onClick={() => scrollToSection(s.id)}
                      aria-current={active ? "step" : undefined}
                    >
                      <span className="cw-step-marker" aria-hidden>
                        <span className="cw-dot" />
                      </span>
                      <span className="cw-step-text">
                        <span className="cw-step-labelrow">
                          <span className="cw-step-label">{s.label}</span>
                          {s.required && (
                            <span className="cw-step-required">必填</span>
                          )}
                        </span>
                        <span className="cw-step-hint">{s.hint}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>
        </div>
      </div>
    </div>
  );
}
