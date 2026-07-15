import { useMemo, useState } from "react";
import {
  ChevronRight,
  Download,
  File,
  FilePlus,
  Folder,
  Loader2,
  Pencil,
  Rocket,
  Trash2,
} from "lucide-react";
// Use the core build + register only the languages we map, so we don't ship
// all ~190 highlight.js grammars (keeps the bundle small).
import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import typescript from "highlight.js/lib/languages/typescript";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import yaml from "highlight.js/lib/languages/yaml";
import markdown from "highlight.js/lib/languages/markdown";
import bash from "highlight.js/lib/languages/bash";
import ini from "highlight.js/lib/languages/ini";
import dockerfile from "highlight.js/lib/languages/dockerfile";
import makefile from "highlight.js/lib/languages/makefile";
hljs.registerLanguage("python", python);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("json", json);
hljs.registerLanguage("yaml", yaml);
hljs.registerLanguage("markdown", markdown);
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("ini", ini);
hljs.registerLanguage("dockerfile", dockerfile);
hljs.registerLanguage("makefile", makefile);
import type { AgentProject, ProjectFile } from "../create/project";
import type { DeployStage } from "../adk/client";
import { buildZip } from "./zip";
import "./ProjectPreview.css";

// --- syntax highlighting ----------------------------------------------------

/** Map a file extension (without dot, lowercased) to an hljs language id. */
const EXT_LANG: Record<string, string> = {
  py: "python",
  pyi: "python",
  ts: "typescript",
  tsx: "typescript",
  mts: "typescript",
  cts: "typescript",
  js: "javascript",
  jsx: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  json: "json",
  jsonc: "json",
  yaml: "yaml",
  yml: "yaml",
  md: "markdown",
  markdown: "markdown",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  toml: "ini",
  ini: "ini",
  cfg: "ini",
  conf: "ini",
  env: "ini",
  txt: "plaintext",
};

/** Map well-known full filenames to an hljs language id. */
const NAME_LANG: Record<string, string> = {
  dockerfile: "dockerfile",
  "requirements.txt": "plaintext",
  "requirements-dev.txt": "plaintext",
  ".env": "ini",
  ".gitignore": "plaintext",
  "makefile": "makefile",
};

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** Pick an hljs language id for a given file path. Returns null when unknown. */
function languageFor(path: string): string | null {
  const file = path.split("/").pop() ?? path;
  const lower = file.toLowerCase();
  if (NAME_LANG[lower]) return NAME_LANG[lower];
  // Handle dotfiles / extensionless names like `.env`, `Dockerfile`.
  if (lower.startsWith("dockerfile")) return "dockerfile";
  if (lower.startsWith(".env")) return "ini";
  const dot = lower.lastIndexOf(".");
  if (dot === -1) return null;
  const ext = lower.slice(dot + 1);
  return EXT_LANG[ext] ?? null;
}

/** Produce highlighted HTML for the given file content. */
function highlight(content: string, path: string): string {
  try {
    const lang = languageFor(path);
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(content, { language: lang, ignoreIllegals: true }).value;
    }
    if (lang === null) {
      // Unknown extension: let hljs guess.
      return hljs.highlightAuto(content).value;
    }
    // Known mapping but language not registered: render as plaintext.
    return escapeHtml(content);
  } catch {
    return escapeHtml(content);
  }
}

export interface DeployResult {
  apikey: string;
  url: string;
  agentName: string;
}

/** The ordered deploy phases shown in the stepper (keys match DeployStage.phase). */
const DEPLOY_STEPS: { phase: string; label: string }[] = [
  { phase: "build", label: "构建镜像" },
  { phase: "deploy", label: "部署" },
  { phase: "publish", label: "发布" },
];

export interface ProjectPreviewProps {
  project: AgentProject;
  /** When provided, files are editable and changes call onChange with the new project. Omit for read-only. */
  onChange?: (project: AgentProject) => void;
  /** One-click deploy handler. Should return deploy result (URL + API Key). Omit to hide the deploy button.
   *  `onStage` receives each live build/deploy/publish progress frame. */
  onDeploy?: (
    project: AgentProject,
    onStage?: (s: DeployStage) => void,
  ) => Promise<DeployResult>;
  /** Called after successfully adding the agent to the connection list. */
  onAgentAdded?: (agentId: string, agentName: string) => void;
}

// --- tree model -------------------------------------------------------------

interface TreeNode {
  name: string;
  /** Full path for file nodes; undefined for folder nodes. */
  path?: string;
  children: Map<string, TreeNode>;
}

function buildTree(files: ProjectFile[]): TreeNode {
  const root: TreeNode = { name: "", children: new Map() };
  for (const f of files) {
    const parts = f.path.split("/").filter(Boolean);
    let node = root;
    parts.forEach((part, i) => {
      let child = node.children.get(part);
      if (!child) {
        child = { name: part, children: new Map() };
        node.children.set(part, child);
      }
      if (i === parts.length - 1) child.path = f.path;
      node = child;
    });
  }
  return root;
}

function sortedChildren(node: TreeNode): TreeNode[] {
  return [...node.children.values()].sort((a, b) => {
    const aFolder = a.children.size > 0 && a.path === undefined;
    const bFolder = b.children.size > 0 && b.path === undefined;
    if (aFolder !== bFolder) return aFolder ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

// --- component --------------------------------------------------------------

export function ProjectPreview({ project, onChange, onDeploy, onAgentAdded }: ProjectPreviewProps) {
  const editable = typeof onChange === "function";

  // Initialize all hooks BEFORE any conditional returns (React hooks rule)
  const [selected, setSelected] = useState<string | null>(
    project?.files?.[0]?.path ?? null,
  );
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [newPath, setNewPath] = useState("");
  const [deploying, setDeploying] = useState(false);
  const [deployError, setDeployError] = useState<string | null>(null);
  const [deployResult, setDeployResult] = useState<DeployResult | null>(null);
  // Latest progress frame per deploy phase + the phase currently in flight,
  // driving the build/deploy/publish stepper.
  const [stageMap, setStageMap] = useState<Record<string, DeployStage>>({});
  const [activePhase, setActivePhase] = useState<string | null>(null);
  const [addingAgent, setAddingAgent] = useState(false);

  const tree = useMemo(() => {
    if (!project?.files || !Array.isArray(project.files)) {
      return { name: "", children: new Map() };
    }
    return buildTree(project.files);
  }, [project?.files]);

  // Validate project structure AFTER all hooks
  if (!project || !Array.isArray(project.files)) {
    return <div className="pp-error">项目数据无效</div>;
  }

  const selectedFile =
    project.files.find((f) => f.path === selected) ?? null;

  function toggleFolder(key: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function commitFiles(files: ProjectFile[], nextSelected?: string | null) {
    if (!onChange) return;
    onChange({ ...project, files });
    if (nextSelected !== undefined) setSelected(nextSelected);
  }

  function handleEdit(content: string) {
    if (!selectedFile) return;
    commitFiles(
      project.files.map((f) =>
        f.path === selectedFile.path ? { ...f, content } : f,
      ),
    );
  }

  function handleAddSubmit() {
    const path = newPath.trim();
    setAdding(false);
    setNewPath("");
    if (!path) return;
    if (project.files.some((f) => f.path === path)) {
      setSelected(path);
      return;
    }
    commitFiles([...project.files, { path, content: "" }], path);
  }

  function handleRename() {
    if (!selectedFile) return;
    const next = window.prompt("重命名文件", selectedFile.path);
    const path = next?.trim();
    if (!path || path === selectedFile.path) return;
    if (project.files.some((f) => f.path === path)) return;
    commitFiles(
      project.files.map((f) =>
        f.path === selectedFile.path ? { ...f, path } : f,
      ),
      path,
    );
  }

  function handleDelete() {
    if (!selectedFile) return;
    const remaining = project.files.filter((f) => f.path !== selectedFile.path);
    commitFiles(remaining, remaining[0]?.path ?? null);
  }

  async function handleDeploy() {
    if (!onDeploy || deploying) return;
    setDeployError(null);
    setDeployResult(null);
    setStageMap({});
    setActivePhase(null);
    setDeploying(true);
    try {
      const result = await onDeploy(project, (s) => {
        setStageMap((prev) => ({ ...prev, [s.phase]: s }));
        setActivePhase(s.phase);
      });
      setDeployResult(result);
      setActivePhase(null);
    } catch (err) {
      setDeployError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeploying(false);
    }
  }

  async function handleAddAgent() {
    if (!deployResult || addingAgent) return;
    setAddingAgent(true);
    setDeployError(null);
    try {
      const { addConnection, remoteAppId, loadConnections } = await import("../adk/connections");

      // 先调用 addConnection 获取实际的 apps 列表
      const conn = await addConnection(
        deployResult.agentName,
        deployResult.url,
        deployResult.apikey,
        "" // 先不传 appLabel，等拿到真实的 app 名称后再更新
      );

      if (conn.apps.length === 0) {
        setDeployError("连接成功，但该地址未发现任何 Agent（/list-apps 为空）。");
      } else {
        // 更新 connection，将第一个 app 的 label 设置为部署返回的真实名称
        const updatedConn = {
          ...conn,
          appLabels: { [conn.apps[0]]: deployResult.agentName }
        };

        // 重新保存到 localStorage
        const allConns = loadConnections();
        const updatedList = allConns.map(c => c.id === conn.id ? updatedConn : c);
        localStorage.setItem("veadk_agentkit_connections", JSON.stringify(updatedList));

        // 重新注册连接以更新路由表
        const { registerConnections } = await import("../adk/connections");
        registerConnections(updatedList);

        // 如果提供了 onAgentAdded 回调，调用它进行导航；否则显示 alert
        if (onAgentAdded) {
          const agentId = remoteAppId(conn.id, conn.apps[0]);
          onAgentAdded(agentId, deployResult.agentName);
        } else {
          alert(`🎉 Agent "${deployResult.agentName}" 已添加到左上角下拉列表！`);
        }
      }
    } catch (err) {
      setDeployError(
        `添加 Agent 失败：${err instanceof Error ? err.message : String(err)}`
      );
    } finally {
      setAddingAgent(false);
    }
  }

  function handleDownloadZip() {
    const blob = buildZip(project.files);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${project.name || "project"}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function renderNode(node: TreeNode, depth: number, prefix: string) {
    return sortedChildren(node).map((child) => {
      const key = prefix ? `${prefix}/${child.name}` : child.name;
      const isFile = child.path !== undefined;
      const pad = { paddingLeft: 8 + depth * 14 };

      if (isFile) {
        const active = child.path === selected;
        return (
          <button
            key={key}
            type="button"
            className={`pp-row pp-file${active ? " pp-active" : ""}`}
            style={pad}
            onClick={() => setSelected(child.path!)}
            title={child.path}
          >
            <File className="pp-ic" />
            <span className="pp-label">{child.name}</span>
          </button>
        );
      }

      const isCollapsed = collapsed.has(key);
      return (
        <div key={key}>
          <button
            type="button"
            className="pp-row pp-folder"
            style={pad}
            onClick={() => toggleFolder(key)}
          >
            <ChevronRight className={`pp-ic pp-chevron${isCollapsed ? "" : " pp-open"}`} />
            <Folder className="pp-ic" />
            <span className="pp-label">{child.name}</span>
          </button>
          {!isCollapsed && renderNode(child, depth + 1, key)}
        </div>
      );
    });
  }

  return (
    <div className="pp-root">
      <div className="pp-sidebar">
        <div className="pp-sidebar-head">
          <span className="pp-project-name" title={project.name}>
            {project.name || "Project"}
          </span>
          {editable && (
            <button
              type="button"
              className="pp-icon-btn"
              title="新建文件"
              onClick={() => {
                setAdding(true);
                setNewPath("");
              }}
            >
              <FilePlus className="pp-ic" />
            </button>
          )}
        </div>

        <div className="pp-tree">
          {adding && (
            <input
              className="pp-new-input"
              autoFocus
              placeholder="path/to/file.py"
              value={newPath}
              onChange={(e) => setNewPath(e.target.value)}
              onBlur={handleAddSubmit}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleAddSubmit();
                if (e.key === "Escape") {
                  setAdding(false);
                  setNewPath("");
                }
              }}
            />
          )}
          {project.files.length === 0 && !adding ? (
            <div className="pp-empty">暂无文件</div>
          ) : (
            renderNode(tree, 0, "")
          )}
        </div>
      </div>

      <div className="pp-main">
        <div className="pp-main-head">
          <span className="pp-path" title={selectedFile?.path}>
            {selectedFile?.path ?? "未选择文件"}
          </span>
          <div className="pp-actions">
            {editable && selectedFile && (
              <>
                <button
                  type="button"
                  className="pp-icon-btn"
                  title="重命名"
                  onClick={handleRename}
                >
                  <Pencil className="pp-ic" />
                </button>
                <button
                  type="button"
                  className="pp-icon-btn pp-danger"
                  title="删除"
                  onClick={handleDelete}
                >
                  <Trash2 className="pp-ic" />
                </button>
              </>
            )}
            {project.files.length > 0 && (
              <button
                type="button"
                className="pp-secondary"
                title="下载 ZIP"
                onClick={handleDownloadZip}
              >
                <Download className="pp-ic" />
                下载 ZIP
              </button>
            )}
            {onDeploy && (
              <button
                type="button"
                className="pp-deploy"
                onClick={handleDeploy}
                disabled={deploying}
              >
                {deploying ? (
                  <Loader2 className="pp-ic spin" />
                ) : (
                  <Rocket className="pp-ic" />
                )}
                部署到 AgentKit
              </button>
            )}
          </div>
        </div>

        {(deploying || deployResult || Object.keys(stageMap).length > 0) && (
          <ol className="pp-steps">
            {DEPLOY_STEPS.map((step, i) => {
              const activeIdx = activePhase
                ? DEPLOY_STEPS.findIndex((s) => s.phase === activePhase)
                : -1;
              const failed =
                !!deployError && (activeIdx === -1 ? i === 0 : i === activeIdx);
              let status: "pending" | "active" | "done" | "failed";
              if (deployResult) status = "done";
              else if (failed) status = "failed";
              else if (activeIdx === -1) status = deploying ? "active" : "pending";
              else if (i < activeIdx) status = "done";
              else if (i === activeIdx) status = deployError ? "failed" : "active";
              else status = "pending";
              const frame = stageMap[step.phase];
              return (
                <li key={step.phase} className={`pp-step is-${status}`}>
                  <span className="pp-step-dot">
                    {status === "active" ? (
                      <Loader2 className="pp-ic spin" />
                    ) : status === "done" ? (
                      "✓"
                    ) : status === "failed" ? (
                      "✕"
                    ) : (
                      i + 1
                    )}
                  </span>
                  <span className="pp-step-body">
                    <span className="pp-step-label">{step.label}</span>
                    {status === "active" && frame?.message && (
                      <span className="pp-step-msg">
                        {frame.message}
                        {typeof frame.pct === "number" ? ` (${frame.pct}%)` : ""}
                      </span>
                    )}
                  </span>
                </li>
              );
            })}
          </ol>
        )}

        {deployError && (
          <div className="pp-error">
            {activePhase
              ? `部署失败（${
                  DEPLOY_STEPS.find((s) => s.phase === activePhase)?.label ??
                  activePhase
                }阶段）：`
              : ""}
            {deployError}
          </div>
        )}

        {deployResult && (
          <div className="pp-deploy-result">
            <div className="pp-deploy-result-header">
              <span className="pp-deploy-result-icon">🎉</span>
              <span>部署成功！</span>
            </div>
            <div className="pp-deploy-result-body">
              <div className="pp-deploy-result-field">
                <label>Agent 名称</label>
                <code>{deployResult.agentName}</code>
              </div>
              <div className="pp-deploy-result-field">
                <label>API 端点</label>
                <code className="pp-deploy-result-url">{deployResult.url}</code>
              </div>
              <div className="pp-deploy-result-field">
                <label>API Key 名称</label>
                <code>{deployResult.apikey}</code>
              </div>
            </div>
            <button
              type="button"
              className="pp-deploy-result-btn"
              onClick={handleAddAgent}
              disabled={addingAgent}
            >
              {addingAgent ? <Loader2 className="pp-ic spin" /> : null}
              {addingAgent ? "连接中…" : "添加此 Agent"}
            </button>
          </div>
        )}

        <div className="pp-content">
          {selectedFile == null ? (
            <div className="pp-placeholder">选择左侧文件以查看内容</div>
          ) : editable ? (
            /* Editable mode: plain <textarea> with no overlay trick. The
               browser handles selection, caret, scrolling, and IME natively
               — so the selection rectangle can never drift away from the
               text (the bug that kept occurring with the previous
               transparent-textarea-over-highlighted-<pre> hack). Syntax
               coloring is sacrificed while editing; users still see colored
               code in read-only/compare views, and get pixel-perfect text
               editing here. */
            <textarea
              className="pp-textarea"
              spellCheck={false}
              value={selectedFile.content}
              onChange={(e) => handleEdit(e.target.value)}
            />
          ) : (
            <pre
              className="pp-pre hljs"
              dangerouslySetInnerHTML={{
                __html: highlight(selectedFile.content, selectedFile.path),
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
