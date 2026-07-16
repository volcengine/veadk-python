import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  ArrowLeft,
  Bot,
  Boxes,
  Check,
  Cloud,
  Cpu,
  Database,
  Eye,
  FileDown,
  FileUp,
  FolderUp,
  GitBranch,
  Globe,
  Info,
  LayoutGrid,
  Layers,
  Loader2,
  Plus,
  Repeat,
  Rocket,
  Shapes,
  Sparkles,
  Split,
  Trash2,
  Wrench,
  X,
} from "lucide-react";
import {
  type CreateModeProps,
  type AgentDraft,
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
import { draftToYaml, yamlToDraft } from "./configYaml";
import type { AgentProject } from "./project";
import type { SkillSource } from "./skills/types";
import { downloadSkillHubSkill } from "./skills/skillhub";
import { downloadSkillSpaceSkill } from "./skills/skillspace";
import { SkillHubPicker } from "./SkillHubPicker";
import { LocalPicker } from "./LocalPicker";
import { SkillSpacePicker } from "./SkillSpacePicker";
import { ProjectPreview } from "../ui/ProjectPreview";
import { deployAgentkitProject } from "../adk/client";
import type { DeployStage } from "../adk/client";
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
  | "type"
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
  { id: "type", label: "类型", hint: "选择 Agent 类型", icon: Shapes, required: true },
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

type AgentTypeId = NonNullable<AgentDraft["agentType"]>;

interface AgentTypeMeta {
  id: AgentTypeId;
  label: string;
  desc: string;
  icon: typeof Bot;
}

/** Custom mark for the LLM agent type: a chat bubble with a generative
 *  "spark", drawn in the lucide stroke style so it sits with the other icons. */
function LlmIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      <path d="M12 6.5c.4 2.4 1 3 3.4 3.4-2.4.4-3 1-3.4 3.4-.4-2.4-1-3-3.4-3.4 2.4-.4 3-1 3.4-3.4Z" />
    </svg>
  );
}

/** The selectable Agent kinds shown on the "type" step. */
const AGENT_TYPES: AgentTypeMeta[] = [
  {
    id: "llm",
    label: "LLM 智能体",
    desc: "大模型驱动，自主完成任务",
    icon: LlmIcon as unknown as typeof Bot,
  },
  {
    id: "sequential",
    label: "顺序编排",
    desc: "子 Agent 按顺序依次执行",
    icon: GitBranch,
  },
  {
    id: "parallel",
    label: "并行编排",
    desc: "子 Agent 并行执行后汇总",
    icon: Split,
  },
  {
    id: "loop",
    label: "循环编排",
    desc: "子 Agent 循环执行到满足条件",
    icon: Repeat,
  },
  {
    id: "a2a",
    label: "A2A 远程 Agent",
    desc: "挂载 URL 指向的远程 Agent",
    icon: Globe,
  },
];

/** Orchestrators (sequential/parallel/loop) own sub-agents but no model.
 *  A2A is a leaf, not an orchestrator — see {@link isA2aType}. */
const isOrchestratorType = (t: AgentDraft["agentType"]): boolean =>
  t === "sequential" || t === "parallel" || t === "loop";

const isA2aType = (t: AgentDraft["agentType"]): boolean => t === "a2a";


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
 * Multi-source skill picker: tab bar switching between Skill Hub
 * (public marketplace), local folder/.zip upload, and account-scoped
 * AgentKit SkillSpaces. Selected skills from all sources share one
 * pill list rendered above the tabs.
 * ---------------------------------------------------------------- */
function SkillPill({
  s,
  onRemove,
}: {
  s: SelectedSkill;
  onRemove: () => void;
}) {
  let Icon = Sparkles;
  let label = "Skill Hub";
  if (s.source === "local") {
    Icon = FolderUp;
    label = "本地";
  } else if (s.source === "skillspace") {
    Icon = Cloud;
    label = "SkillSpace";
  }
  return (
    <motion.span
      key={`${s.source}:${s.folder}:${s.skillId || s.slug || ""}:${s.version || ""}`}
      className="cw-pill"
      layout
      initial={{ opacity: 0, scale: 0.85 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.85 }}
      transition={{ duration: 0.16 }}
    >
      <Icon className="cw-i cw-i-sm" />
      {s.name}
      <span className="cw-pill-source">{label}</span>
      <button
        type="button"
        className="cw-pill-x"
        onClick={onRemove}
        aria-label={`移除 ${s.name}`}
      >
        <X className="cw-i cw-i-sm" />
      </button>
    </motion.span>
  );
}

const SKILL_SOURCES: {
  id: SkillSource;
  label: string;
  icon: typeof Globe;
}[] = [
  { id: "skillhub", label: "Skill Hub", icon: Globe },
  { id: "local", label: "本地文件", icon: FolderUp },
  { id: "skillspace", label: "SkillSpace", icon: Cloud },
];

function SkillsSourceTabs({
  selected,
  onChange,
}: {
  selected: SelectedSkill[];
  onChange: (next: SelectedSkill[]) => void;
}) {
  const [active, setActive] = useState<SkillSource>("skillhub");
  const remove = (key: string) =>
    onChange(selected.filter((s) => skillKey(s) !== key));

  return (
    <div className="cw-skillspane">
      {selected.length > 0 && (
        <div className="cw-skill-selected">
          <span className="cw-skill-selected-label">已选技能</span>
          <div className="cw-pills">
            <AnimatePresence initial={false}>
              {selected.map((s) => (
                <SkillPill key={skillKey(s)} s={s} onRemove={() => remove(skillKey(s))} />
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      <div className="cw-skill-sourcetabs" role="tablist">
        {SKILL_SOURCES.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={active === id}
            className={`cw-skill-pickertab ${active === id ? "is-on" : ""}`}
            onClick={() => setActive(id)}
          >
            <Icon className="cw-i cw-i-sm" />
            {label}
          </button>
        ))}
      </div>

      <div className="cw-skill-tabbody">
        {active === "skillhub" && (
          <SkillHubPicker selected={selected} onChange={onChange} />
        )}
        {active === "local" && (
          <LocalPicker selected={selected} onChange={onChange} />
        )}
        {active === "skillspace" && (
          <SkillSpacePicker selected={selected} onChange={onChange} />
        )}
      </div>
    </div>
  );
}

function skillKey(s: SelectedSkill): string {
  if (s.source === "skillhub") return `hub:${s.namespace}/${s.slug}`;
  if (s.source === "local") return `local:${s.folder}`;
  return `ss:${s.skillSpaceId}/${s.skillId}/${s.version || ""}`;
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


/* ================================================================ *
 * Tree addressing — the draft is a recursive AgentDraft. A node is
 * addressed by an array of child indices; [] is the root.
 * ================================================================ */
type NodePath = number[];

const samePath = (a: NodePath, b: NodePath) =>
  a.length === b.length && a.every((v, i) => v === b[i]);

function pathExists(root: AgentDraft, path: NodePath): boolean {
  let node: AgentDraft | undefined = root;
  for (const i of path) {
    node = node.subAgents?.[i];
    if (!node) return false;
  }
  return true;
}

function getNode(root: AgentDraft, path: NodePath): AgentDraft {
  let node = root;
  for (const i of path) node = node.subAgents[i];
  return node;
}

/** Immutably replace the node at `path` by applying `fn` (copies each level). */
function updateNode(
  root: AgentDraft,
  path: NodePath,
  fn: (n: AgentDraft) => AgentDraft,
): AgentDraft {
  if (path.length === 0) return fn(root);
  const [i, ...rest] = path;
  const subAgents = root.subAgents.slice();
  subAgents[i] = updateNode(subAgents[i], rest, fn);
  return { ...root, subAgents };
}

function addChild(root: AgentDraft, path: NodePath): AgentDraft {
  return updateNode(root, path, (n) => ({
    ...n,
    subAgents: [...n.subAgents, emptyDraft()],
  }));
}

function removeNode(root: AgentDraft, path: NodePath): AgentDraft {
  if (path.length === 0) return root; // the root is never removable
  const parentPath = path.slice(0, -1);
  const idx = path[path.length - 1];
  return updateNode(root, parentPath, (n) => ({
    ...n,
    subAgents: n.subAgents.filter((_, i) => i !== idx),
  }));
}

/** Move a child within its parent's list from index `from` to `to`. The moved
 *  node carries its whole subtree with it. */
function reorderSiblings(
  root: AgentDraft,
  parentPath: NodePath,
  from: number,
  to: number,
): AgentDraft {
  return updateNode(root, parentPath, (n) => {
    const subAgents = n.subAgents.slice();
    const [moved] = subAgents.splice(from, 1);
    subAgents.splice(to, 0, moved);
    return { ...n, subAgents };
  });
}

/** Reordering only matters where child order drives execution: Sequential and
 *  Loop orchestrators. Parallel / LLM sub-agents are order-independent. */
const orderedChildrenType = (t: AgentDraft["agentType"]) =>
  t === "sequential" || t === "loop";

/** A node holds children only when it's an LLM or an orchestrator (not A2A). */
const nodeAcceptsChildren = (n: AgentDraft) => !isA2aType(n.agentType);

/** Max nesting depth below the root (root = depth 0). Keeps the tree readable
 *  within the fixed-width panel instead of needing horizontal scroll. */
const MAX_TREE_DEPTH = 3;

const typeMeta = (type: AgentDraft["agentType"]) =>
  AGENT_TYPES.find((t) => t.id === (type ?? "llm")) ?? AGENT_TYPES[0];

/** Per-node required-field problem, or null when the node is valid. */
function nodeProblem(n: AgentDraft): string | null {
  if (n.name.trim().length === 0) return "缺少名称";
  if (isA2aType(n.agentType))
    return (n.a2aUrl ?? "").trim().length === 0 ? "缺少 Agent URL" : null;
  if (isOrchestratorType(n.agentType))
    return n.subAgents.length === 0 ? "缺少子 Agent" : null;
  return n.instruction.trim().length === 0 ? "缺少系统提示词" : null;
}

interface TreeProblem {
  path: NodePath;
  name: string;
  problem: string;
}

/** Collect required-field problems across the whole tree, in render order. */
function treeProblems(root: AgentDraft, path: NodePath = []): TreeProblem[] {
  const out: TreeProblem[] = [];
  const p = nodeProblem(root);
  if (p) out.push({ path, name: root.name.trim() || "未命名", problem: p });
  if (nodeAcceptsChildren(root)) {
    root.subAgents.forEach((c, i) => out.push(...treeProblems(c, [...path, i])));
  }
  return out;
}

/* ---------------------------------------------------------------- *
 * Left structure tree: one selectable, editable node (recursive).
 * ---------------------------------------------------------------- */
function TreeNode({
  root,
  path,
  selectedPath,
  onSelect,
  onChange,
}: {
  root: AgentDraft;
  path: NodePath;
  selectedPath: NodePath;
  onSelect: (p: NodePath) => void;
  /** Replace the whole tree; optionally move the selection. */
  onChange: (nextRoot: AgentDraft, select?: NodePath) => void;
}) {
  const node = getNode(root, path);
  const meta = typeMeta(node.agentType);
  const Icon = meta.icon;
  const isRoot = path.length === 0;
  const selected = samePath(path, selectedPath);
  const acceptsChildren = nodeAcceptsChildren(node);
  const canAddChild = acceptsChildren && path.length < MAX_TREE_DEPTH;

  const add = () => {
    const next = addChild(root, path);
    const childIndex = getNode(next, path).subAgents.length - 1;
    onChange(next, [...path, childIndex]);
  };
  const del = () => onChange(removeNode(root, path), path.slice(0, -1));

  // Drag-to-reorder is enabled only when this node's PARENT is a Sequential or
  // Loop orchestrator (order = execution order). Dragging carries the subtree.
  const parentPath = path.slice(0, -1);
  const draggable =
    !isRoot && orderedChildrenType(getNode(root, parentPath).agentType);
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    const raw = e.dataTransfer.getData("application/x-agent-path");
    if (!raw) return;
    let src: NodePath;
    try {
      src = JSON.parse(raw) as NodePath;
    } catch {
      return;
    }
    // Reorder among siblings only (same parent).
    if (!samePath(src.slice(0, -1), parentPath)) return;
    const from = src[src.length - 1];
    const to = path[path.length - 1];
    if (from === to) return;
    onChange(reorderSiblings(root, parentPath, from, to), [...parentPath, to]);
  };

  return (
    <div className="cw-tree-branch">
      <div
        className={`cw-tree-node cw-tree-type-${node.agentType ?? "llm"} ${
          selected ? "is-selected" : ""
        } ${draggable ? "is-draggable" : ""} ${dragOver ? "is-dragover" : ""} ${
          nodeProblem(node) ? "is-invalid" : ""
        }`}
        role="button"
        tabIndex={0}
        draggable={draggable}
        onDragStart={
          draggable
            ? (e) => {
                e.dataTransfer.setData(
                  "application/x-agent-path",
                  JSON.stringify(path),
                );
                e.dataTransfer.effectAllowed = "move";
                e.stopPropagation();
              }
            : undefined
        }
        onDragOver={
          draggable
            ? (e) => {
                e.preventDefault();
                setDragOver(true);
              }
            : undefined
        }
        onDragLeave={draggable ? () => setDragOver(false) : undefined}
        onDrop={draggable ? handleDrop : undefined}
        onClick={() => onSelect(path)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect(path);
          }
        }}
      >
        <Icon className="cw-tree-icon" />
        <span className="cw-tree-main">
          <span className="cw-tree-name">{node.name.trim() || "未命名"}</span>
          <span className="cw-tree-type">{meta.label}</span>
        </span>
        <span className="cw-tree-actions">
          {canAddChild && (
            <button
              type="button"
              className="cw-icon-btn"
              title="添加子 Agent"
              onClick={(e) => {
                e.stopPropagation();
                add();
              }}
            >
              <Plus className="cw-i cw-i-sm" />
            </button>
          )}
          {!isRoot && (
            <button
              type="button"
              className="cw-icon-btn cw-icon-danger"
              title="删除"
              onClick={(e) => {
                e.stopPropagation();
                del();
              }}
            >
              <Trash2 className="cw-i cw-i-sm" />
            </button>
          )}
        </span>
      </div>
      {acceptsChildren && node.subAgents.length > 0 && (
        <div className="cw-tree-children">
          {node.subAgents.map((_, i) => (
            <TreeNode
              key={i}
              root={root}
              path={[...path, i]}
              selectedPath={selectedPath}
              onSelect={onSelect}
              onChange={onChange}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ================================================================ *
 * Main component
 * ================================================================ */
interface CustomCreateProps extends CreateModeProps {
  /** Pre-fill the wizard (used when importing an agent-structure YAML). */
  initialDraft?: AgentDraft;
  /** Current user identity, tagged onto deployed runtimes for the 管理 Agent view. */
  author?: string;
}

export function CustomCreate({ onBack, onCreate, onAgentAdded, initialDraft, author = "" }: CustomCreateProps) {
  void onCreate; // outcome is the in-pane project preview, not a navigation
  void onBack; // no footer nav in the single-scroll layout; back lives in app chrome
  const [draft, setDraft] = useState<AgentDraft>(() => initialDraft ?? emptyDraft());
  const [showErrors, setShowErrors] = useState(false);
  const [project, setProject] = useState<AgentProject | null>(null);
  const [building, setBuilding] = useState(false);
  // The section nearest the top of the scroll container (scroll-spy) — drives
  // the right-hand step nav highlight.
  const [activeId, setActiveId] = useState<StepId>("type");
  // YAML import: file input + last error message.
  const yamlInputRef = useRef<HTMLInputElement>(null);
  const [importErr, setImportErr] = useState("");
  const onImportYaml = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-importing the same file
    if (!file) return;
    setImportErr("");
    try {
      const text = await file.text();
      setDraft(yamlToDraft(text));
      setSelectedPath([]);
      setShowErrors(false);
    } catch (ex) {
      setImportErr(`导入失败：${ex instanceof Error ? ex.message : String(ex)}`);
    }
  };

  // Which tree node is being edited ([] = root). The detail pane and per-node
  // inline errors are driven by this selection.
  const [selectedPath, setSelectedPath] = useState<NodePath>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const sectionRefs = useRef<Partial<Record<StepId, HTMLElement | null>>>({});

  // Section wrapper: registers a ref for scroll-spy + renders the heading.
  // IMPORTANT: keep a STABLE identity (stored in a ref). If this were declared
  // as a fresh function each render, React would remount every section on every
  // keystroke — detaching the nodes the IntersectionObserver watches (breaking
  // the scroll-spy) and dropping input focus.
  // NOTE: Must be declared before any conditional returns to satisfy React hooks rules.
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
        </header>
        {children}
      </section>
    );
  }

  // The selection is clamped to a path that still exists (a deletion may have
  // removed the previously-selected node). `patch` always edits this node.
  const safePath = pathExists(draft, selectedPath) ? selectedPath : [];
  const node = getNode(draft, safePath);

  const patch = (p: Partial<AgentDraft>) =>
    setDraft((d) => updateNode(d, safePath, (n) => ({ ...n, ...p })));

  // Replace the whole tree (structural edits from the left tree), optionally
  // moving the selection to a new node.
  const applyTree = (nextRoot: AgentDraft, select?: NodePath) => {
    setDraft(nextRoot);
    if (select) setSelectedPath(select);
  };

  // Root-only rich sections read these off the root draft directly.
  const builtinTools = node.builtinTools ?? [];
  const mcpTools = node.mcpTools ?? [];
  const tracingExporters = node.tracingExporters ?? [];
  const selectedSkills = node.selectedSkills ?? [];

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
    patch({ tracingExporters: next, tracing: next.length > 0 ? true : node.tracing });
  };

  // Detail-pane branching is driven by the SELECTED node's type.
  const orchestrator = isOrchestratorType(node.agentType);
  const a2a = isA2aType(node.agentType);

  // Inline error flags for the selected node.
  const nameMissing = node.name.trim().length === 0;
  const instructionMissing = node.instruction.trim().length === 0;
  const urlMissing = (node.a2aUrl ?? "").trim().length === 0;

  // Whole-tree validation: every node must satisfy its type's requirements.
  const problems = useMemo(() => treeProblems(draft), [draft]);
  const canFinish = problems.length === 0;

  // Per-step completion, for the nav's done-checkmarks + progress fill.
  const completion = useMemo<Record<StepId, boolean>>(
    () => ({
      type: true,
      basic: !nameMissing && (orchestrator || a2a || !instructionMissing),
      model: Boolean(
        node.modelName?.trim() ||
          node.modelProvider?.trim() ||
          node.modelApiBase?.trim(),
      ),
      tools: builtinTools.length > 0 || mcpTools.length > 0,
      skills: selectedSkills.length > 0,
      memory: node.memory.shortTerm || node.memory.longTerm,
      knowledge: node.knowledgebase,
      tracing: node.tracing || node.enableA2ui,
      subagents: (node.subAgents?.length ?? 0) > 0,
      review: canFinish,
    }),
    [node, nameMissing, instructionMissing, orchestrator, a2a, canFinish, builtinTools, mcpTools, selectedSkills],
  );

  // The nav only lists the sections actually rendered for THIS node's type —
  // orchestrators / A2A leaves have far fewer than an LLM (type lives in the
  // top bar; sub-agents live in the left tree; both are excluded here).
  const navStepIds: StepId[] =
    orchestrator || a2a
      ? ["basic"]
      : ["basic", "model", "tools", "skills", "memory", "knowledge", "tracing"];
  const navSteps = STEPS.filter((s) => navStepIds.includes(s.id));
  const activeIndex = navSteps.findIndex((s) => s.id === activeId);

  // Smooth-scroll a section into view (nav click is a convenience).
  const scrollToSection = (id: StepId) => {
    sectionRefs.current[id]?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // Scroll-spy: mark the section nearest the top of the scroll container active.
  useEffect(() => {
    if (project) return; // observer targets only exist in the form view
    const root = scrollRef.current;
    if (!root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        const id = (visible[0]?.target as HTMLElement | undefined)?.dataset
          .stepId as StepId | undefined;
        if (id) setActiveId(id);
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
      // Select the first node that still has a missing required field.
      if (problems[0]) setSelectedPath(problems[0].path);
      return;
    }
    // NOTE: do NOT call onCreate() here — it navigates away from the create
    // view. The generated project preview below IS the outcome of this step.

    const proj = generateProject(draft);

    // Collect skill selections across EVERY agent in the tree (dedup by a
    // source-aware key) — skills can be chosen on any LLM node, not just root.
    const allSkills: SelectedSkill[] = [];
    const seenSkill = new Set<string>();
    const collectSkills = (n: AgentDraft) => {
      for (const s of n.selectedSkills ?? []) {
        const key =
          s.source === "skillhub"
            ? `hub:${s.namespace}/${s.slug}`
            : s.source === "local"
              ? `local:${s.folder}`
              : `ss:${s.skillSpaceId}/${s.skillId}/${s.version || ""}`;
        if (!seenSkill.has(key)) {
          seenSkill.add(key);
          allSkills.push(s);
        }
      }
      (n.subAgents ?? []).forEach(collectSkills);
    };
    collectSkills(draft);

    // Materialize files per source in parallel. Per-skill failures are skipped
    // (logged) so one bad skill can't abort the build. Local skills already
    // carry their files; hub + skillspace skills are fetched here.
    if (allSkills.length > 0) {
      setBuilding(true);
      try {
        const results = await Promise.all(
          allSkills.map((s) => {
            const p =
              s.source === "local"
                ? Promise.resolve(s.localFiles ?? [])
                : s.source === "skillspace"
                  ? downloadSkillSpaceSkill(
                      s.skillSpaceId!,
                      s.skillId!,
                      s.version,
                      s.folder,
                    )
                  : downloadSkillHubSkill(s);
            return p.catch((err: unknown) => {
              console.warn(`下载技能失败：${s.name}`, err);
              return [];
            });
          }),
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

  // ----------------------------------------------------------------
  // Preview mode: takes over the whole pane, hiding the wizard chrome.
  // ----------------------------------------------------------------
  if (project) {
    const handleDeploy = async (
      proj: AgentProject,
      onStage?: (s: DeployStage) => void,
    ) => {
      return deployAgentkitProject(
        proj.name,
        proj.files,
        { region: "cn-beijing", projectName: "default" },
        { author, onStage },
      );
    };

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
          <ProjectPreview project={project} onChange={setProject} onDeploy={handleDeploy} onAgentAdded={onAgentAdded} />
        </div>
      </div>
    );
  }

  const Section = sectionImpl.current;

  const metaOf = (id: StepId) => STEPS.find((s) => s.id === id)!;

  return (
    <div className="cw-root">
      <div className="cw-editor">
        {/* Left: the Agent structure tree (select / add / remove / reorder). */}
        <aside className="cw-tree" aria-label="Agent 结构">
          <div className="cw-tree-head">Agent 结构</div>
          <TreeNode
            root={draft}
            path={[]}
            selectedPath={safePath}
            onSelect={setSelectedPath}
            onChange={applyTree}
          />
        </aside>
        {/* Right: the form for the currently-selected node. The agent-type bar
            is fixed on top (outside the scroll area); the form (left) + step
            nav (right) scroll below it. */}
        <div className="cw-detail">
          {/* Fixed top bar: pick the agent type; missing-info shows here too. */}
          <div className="cw-typebar">
            <div className="cw-typebar-inner">
              <header className="cw-sec-head">
                <h2 className="cw-sec-title">
                  类型<span className="cw-sec-required">必填</span>
                </h2>
              </header>
              <div className="cw-typeradio cw-typeradio--row">
                {AGENT_TYPES.map((t) => {
                  const on = (node.agentType ?? "llm") === t.id;
                  const Icon = t.icon;
                  return (
                    <label
                      key={t.id}
                      className={`cw-typeradio-item ${on ? "is-on" : ""}`}
                    >
                      <input
                        type="radio"
                        name="agentType"
                        className="cw-typeradio-input"
                        checked={on}
                        onChange={() => patch({ agentType: t.id })}
                      />
                      <span className="cw-typeradio-dot" aria-hidden />
                      <span className="cw-typeradio-main">
                        <span className="cw-typeradio-head">
                          <Icon className="cw-typeradio-icon" />
                          <span className="cw-typeradio-title">{t.label}</span>
                        </span>
                      </span>
                    </label>
                  );
                })}
              </div>
              {problems.length > 0 && (
                <div className="cw-missing" role="alert">
                  <span className="cw-missing-lead">待补全（{problems.length}）</span>
                  <div className="cw-missing-list">
                    {problems.map((p) => (
                      <button
                        key={p.path.join(".") + p.problem}
                        type="button"
                        className="cw-missing-item"
                        onClick={() => {
                          setShowErrors(true);
                          setSelectedPath(p.path);
                        }}
                      >
                        {p.name} · {p.problem}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Scroll area: form on the left, step nav on the right. */}
          <div className="cw-detail-scroll" ref={scrollRef}>
          <div className="cw-detail-inner">
            <div className="cw-lower">
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
                        value={node.name}
                        placeholder="例如：客服智能体"
                        onChange={(e) => patch({ name: e.target.value })}
                      />
                      {showErrors && nameMissing && (
                        <span className="cw-error-text">名称为必填项</span>
                      )}
                    </div>
                    <div className="cw-field">
                      <label className="cw-label">描述</label>
                      <textarea
                        className="cw-textarea cw-textarea-sm"
                        value={node.description}
                        placeholder="简要描述这个 Agent 的用途，便于团队识别…"
                        onChange={(e) =>
                          patch({ description: e.target.value })
                        }
                      />
                      <span className="cw-help">
                        描述会显示在 Agent 列表与选择器中。
                      </span>
                    </div>
                    {orchestrator ? (
                      <>
                        <p className="cw-section-desc">
                          编排型 Agent 只负责调度子 Agent，不需要模型或系统提示词。请在左侧
                          「Agent 结构」中为它添加、排序子 Agent。
                        </p>
                        {node.agentType === "loop" && (
                          <div className="cw-field">
                            <label className="cw-label">最大轮次</label>
                            <input
                              className="cw-input"
                              type="number"
                              min={1}
                              value={node.maxIterations ?? 3}
                              onChange={(e) =>
                                patch({
                                  maxIterations: Math.max(
                                    1,
                                    Number(e.target.value) || 1,
                                  ),
                                })
                              }
                            />
                            <span className="cw-help">
                              循环编排反复执行子 Agent，直到满足条件或达到该轮次上限。
                            </span>
                          </div>
                        )}
                      </>
                    ) : a2a ? (
                      <div className="cw-field">
                        <label className="cw-label">
                          Agent URL<span className="cw-req">*</span>
                        </label>
                        <input
                          className={`cw-input ${
                            showErrors && urlMissing ? "is-error" : ""
                          }`}
                          value={node.a2aUrl ?? ""}
                          placeholder="https://example.com/my-agent"
                          onChange={(e) => patch({ a2aUrl: e.target.value })}
                        />
                        {showErrors && urlMissing ? (
                          <span className="cw-error-text">Agent URL 为必填项</span>
                        ) : (
                          <span className="cw-help">
                            远程 Agent 的访问地址（A2A 协议）；VeADK 会拉取其 Agent Card
                            并按需处理鉴权。
                          </span>
                        )}
                      </div>
                    ) : (
                      <div className="cw-field">
                        <label className="cw-label">
                          系统提示词<span className="cw-req">*</span>
                        </label>
                        <textarea
                          className={`cw-textarea cw-textarea-lg ${
                            showErrors && instructionMissing ? "is-error" : ""
                          }`}
                          value={node.instruction}
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
                    )}
                  </div>
            </Section>

            {/* Every LLM agent (root or sub) gets the full config —
                model/tools/skills/memory/knowledge/tracing. Orchestrators and
                A2A leaves own none of these. */}
            {!orchestrator && !a2a && (
              <>
            <Section meta={metaOf("model")}>
                  <div className="cw-form">
                    <div className="cw-field">
                      <label className="cw-label">模型名称</label>
                      <input
                        className="cw-input"
                        value={node.modelName ?? ""}
                        placeholder="doubao-seed-1-6-250615"
                        onChange={(e) => patch({ modelName: e.target.value })}
                      />
                    </div>
                    <div className="cw-field">
                      <label className="cw-label">服务商 Provider</label>
                      <input
                        className="cw-input"
                        value={node.modelProvider ?? ""}
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
                        value={node.modelApiBase ?? ""}
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
                      从 Skill Hub、本地文件或 AgentKit SkillSpace 添加技能，生成项目时会写入 skills/ 目录。
                    </p>
                    <SkillsSourceTabs
                      selected={selectedSkills}
                      onChange={(next) => patch({ selectedSkills: next })}
                    />
                  </div>
            </Section>

            <Section meta={metaOf("memory")}>
                  <div className="cw-form cw-toggle-stack">
                    <Toggle
                      checked={node.memory.shortTerm}
                      onChange={(v) =>
                        patch({
                          memory: { ...node.memory, shortTerm: v },
                        })
                      }
                      title="短期记忆"
                      desc="在单次会话内保留上下文，跨轮次记住对话内容。"
                      icon={Layers}
                    />
                    {node.memory.shortTerm && (
                      <div className="cw-field cw-subfield">
                        <label className="cw-label">短期记忆后端</label>
                        <BackendSelect
                          options={STM_BACKENDS}
                          value={node.shortTermBackend}
                          onChange={(id) => patch({ shortTermBackend: id })}
                        />
                      </div>
                    )}
                    <Toggle
                      checked={node.memory.longTerm}
                      onChange={(v) =>
                        patch({
                          memory: { ...node.memory, longTerm: v },
                        })
                      }
                      title="长期记忆"
                      desc="跨会话持久化关键信息，让 Agent 记住历史偏好。"
                      icon={Database}
                    />
                    {node.memory.longTerm && (
                      <div className="cw-field cw-subfield">
                        <label className="cw-label">长期记忆后端</label>
                        <BackendSelect
                          options={LTM_BACKENDS}
                          value={node.longTermBackend}
                          onChange={(id) => patch({ longTermBackend: id })}
                        />
                        <Toggle
                          checked={!!node.autoSaveSession}
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
                      checked={node.knowledgebase}
                      onChange={(v) => patch({ knowledgebase: v })}
                      title="知识库"
                      desc="启用外部知识检索（RAG），让 Agent 基于你的资料作答。"
                      icon={Database}
                    />
                    {node.knowledgebase && (
                      <div className="cw-field cw-subfield">
                        <label className="cw-label">知识库后端</label>
                        <BackendSelect
                          options={KB_BACKENDS}
                          value={node.knowledgebaseBackend}
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
                      checked={node.tracing}
                      onChange={(v) => patch({ tracing: v })}
                      title="观测 / Tracing"
                      desc="记录每一步的调用链路与耗时，便于调试与性能分析。"
                      icon={Eye}
                    />
                    {node.tracing && (
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
                      checked={node.enableA2ui}
                      onChange={(v) => patch({ enableA2ui: v })}
                      title="A2UI"
                      desc="允许 Agent 渲染交互式 UI 卡片，而不仅仅是纯文本。"
                      icon={LayoutGrid}
                    />
                  </div>
            </Section>
              </>
            )}
          </div>

            {/* Right rail: scroll-spy step nav (click to jump to a section).
                Only the sections rendered for this node's type are listed. */}
            <nav className="cw-rail" aria-label="步骤导航">
              <ol className="cw-steps">
                <div className="cw-rail-track" aria-hidden>
                  <motion.div
                    className="cw-rail-fill"
                    animate={{
                      height: `${(Math.max(activeIndex, 0) / Math.max(navSteps.length - 1, 1)) * 100}%`,
                    }}
                    transition={{ type: "spring", stiffness: 260, damping: 32 }}
                  />
                </div>
                {navSteps.map((s) => {
                  const active = s.id === activeId;
                  const done = completion[s.id];
                  return (
                    <li key={s.id}>
                      <button
                        type="button"
                        className={`cw-step ${active ? "is-active" : ""} ${done ? "is-done" : ""}`}
                        onClick={() => scrollToSection(s.id)}
                        aria-current={active ? "step" : undefined}
                      >
                        <span className="cw-step-marker" aria-hidden>
                          <span className="cw-dot" />
                        </span>
                        <span className="cw-step-text">
                          <span className="cw-step-labelrow">
                            <span className="cw-step-label">{s.label}</span>
                            {s.required && <span className="cw-step-required">必填</span>}
                          </span>
                          <span className="cw-step-hint">{s.hint}</span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </nav>
          </div>{/* cw-lower */}
          </div>{/* cw-detail-inner */}
          </div>{/* cw-detail-scroll */}
        </div>{/* cw-detail */}
      </div>{/* cw-editor */}
      <footer className="cw-footer-bar">
        <div className="cw-footer-status">
          {canFinish ? (
            <span className="cw-footer-ok">✓ 配置完整，可生成项目</span>
          ) : (
            <button
              type="button"
              className="cw-footer-problem"
              onClick={() => {
                setShowErrors(true);
                if (problems[0]) setSelectedPath(problems[0].path);
              }}
            >
              待补全（{problems.length}）：{problems[0].name} · {problems[0].problem}
            </button>
          )}
        </div>
        <div className="cw-footer-actions">
          {importErr && <span className="cw-footer-importerr">{importErr}</span>}
          <input
            ref={yamlInputRef}
            type="file"
            accept=".yaml,.yml,text/yaml"
            style={{ display: "none" }}
            onChange={onImportYaml}
          />
          <button
            type="button"
            className="cw-btn cw-btn-soft"
            onClick={() => yamlInputRef.current?.click()}
            title="从 YAML 加载 Agent 结构（覆盖当前表单）"
          >
            <FileUp className="cw-i" />
            导入 YAML
          </button>
          <button
            type="button"
            className="cw-btn cw-btn-soft"
            onClick={() =>
              downloadText(
                `${draft.name || "agent"}.yaml`,
                draftToYaml(draft),
                "text/yaml",
              )
            }
            title="导出表示 Agent 结构的 YAML"
          >
            <FileDown className="cw-i" />
            导出 YAML
          </button>
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
      </footer>
    </div>
  );
}
