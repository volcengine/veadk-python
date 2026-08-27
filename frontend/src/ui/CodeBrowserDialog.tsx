import {
  lazy,
  Suspense,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import type { AgentProject, ProjectFile } from "../create/project";
import type { CodeWorkspaceTheme } from "./CodeEditor";
import {
  codeChangeLabel,
  compareProjectFiles,
  type CodeChangeStatus,
} from "./codeComparison";
import {
  SourceChevronIcon,
  SourceCloseIcon,
  SourceCodeIcon,
  SourceDarkThemeIcon,
  SourceFileIcon,
  SourceFolderIcon,
  SourceLightThemeIcon,
} from "./icons/SourceWorkspaceIcons";
import "./CodeBrowserDialog.css";

const CodeEditor = lazy(() => import("./CodeEditor"));
const CodeDiffEditor = lazy(() => import("./CodeDiffEditor"));
const CODE_THEME_KEY = "veadk-code-workspace-theme";

interface TreeNode {
  name: string;
  path?: string;
  children: Map<string, TreeNode>;
}

function buildTree(files: ProjectFile[]): TreeNode {
  const root: TreeNode = { name: "", children: new Map() };
  for (const file of files) {
    const parts = file.path.split("/").filter(Boolean);
    let node = root;
    parts.forEach((part, index) => {
      let child = node.children.get(part);
      if (!child) {
        child = { name: part, children: new Map() };
        node.children.set(part, child);
      }
      if (index === parts.length - 1) child.path = file.path;
      node = child;
    });
  }
  return root;
}

function sortedChildren(node: TreeNode, filesFirst = false): TreeNode[] {
  return [...node.children.values()].sort((a, b) => {
    const aFolder = a.children.size > 0 && a.path === undefined;
    const bFolder = b.children.size > 0 && b.path === undefined;
    if (aFolder !== bFolder) {
      return filesFirst ? (aFolder ? 1 : -1) : aFolder ? -1 : 1;
    }
    return a.name.localeCompare(b.name);
  });
}

function initialTheme(): CodeWorkspaceTheme {
  if (typeof window === "undefined") return "light";
  try {
    const stored = window.localStorage.getItem(CODE_THEME_KEY);
    return stored === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

function lineCount(content: string): number {
  return content === "" ? 0 : content.split("\n").length;
}

export interface CodeBrowserComparison {
  baseProject: AgentProject;
  baseLabel?: string;
  targetLabel?: string;
}

export interface CodeBrowserDialogProps {
  project: AgentProject;
  open: boolean;
  onClose: () => void;
  onChange: (project: AgentProject) => void;
  readOnly?: boolean;
  comparison?: CodeBrowserComparison;
}

/** Browse, edit, or compare project source without leaving the current workflow. */
export function CodeBrowserDialog({
  project,
  open,
  onClose,
  onChange,
  readOnly = false,
  comparison,
}: CodeBrowserDialogProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  const [theme, setTheme] = useState<CodeWorkspaceTheme>(initialTheme);
  const changes = useMemo(
    () => comparison
      ? compareProjectFiles(comparison.baseProject.files, project.files)
      : [],
    [comparison, project.files],
  );
  const displayFiles = useMemo<ProjectFile[]>(
    () => comparison
      ? changes.map((change) => ({
          path: change.path,
          content: change.status === "deleted" ? change.before : change.after,
        }))
      : project.files,
    [changes, comparison, project.files],
  );
  const statusByPath = useMemo(
    () => new Map(changes.map((change) => [change.path, change.status])),
    [changes],
  );
  const [selected, setSelected] = useState<string | null>(
    displayFiles[0]?.path ?? null,
  );
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const tree = useMemo(() => buildTree(displayFiles), [displayFiles]);
  const selectedFile = displayFiles.find((file) => file.path === selected) ?? null;
  const selectedChange = changes.find((change) => change.path === selected) ?? null;
  onCloseRef.current = onClose;

  useEffect(() => {
    try {
      window.localStorage.setItem(CODE_THEME_KEY, theme);
    } catch {
      // Theme persistence is optional; the active workspace remains usable.
    }
  }, [theme]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )].filter((item) => item.offsetParent !== null);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [open]);

  useEffect(() => {
    if (selectedFile || displayFiles.length === 0) return;
    setSelected(displayFiles[0].path);
  }, [displayFiles, selectedFile]);

  if (!open) return null;

  function toggleFolder(key: string) {
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function renderStatus(status: CodeChangeStatus | undefined) {
    if (!status) return null;
    return (
      <span className={`code-browser-change is-${status}`}>
        {codeChangeLabel(status)}
      </span>
    );
  }

  function renderNode(node: TreeNode, depth: number, parentKey: string) {
    return sortedChildren(node, depth === 0).map((child) => {
      const key = parentKey ? `${parentKey}/${child.name}` : child.name;
      const isFolder = child.children.size > 0 && child.path === undefined;
      if (!isFolder && child.path) {
        const status = statusByPath.get(child.path);
        return (
          <button
            type="button"
            key={key}
            className={`code-browser-file${selected === child.path ? " is-active" : ""}`}
            style={{ paddingLeft: `${12 + depth * 16}px` }}
            onClick={() => setSelected(child.path ?? null)}
            title={child.path}
            aria-pressed={selected === child.path}
          >
            <SourceFileIcon />
            <span>{child.name}</span>
            {renderStatus(status)}
          </button>
        );
      }
      const isCollapsed = collapsed.has(key);
      return (
        <div key={key}>
          <button
            type="button"
            className="code-browser-folder"
            style={{ paddingLeft: `${10 + depth * 16}px` }}
            onClick={() => toggleFolder(key)}
            aria-expanded={!isCollapsed}
          >
            <SourceChevronIcon className={isCollapsed ? "" : "is-open"} />
            <SourceFolderIcon />
            <span>{child.name}</span>
          </button>
          {!isCollapsed && renderNode(child, depth + 1, key)}
        </div>
      );
    });
  }

  function handleEdit(content: string) {
    if (!selectedFile || comparison) return;
    onChange({
      ...project,
      files: project.files.map((file) =>
        file.path === selectedFile.path ? { ...file, content } : file,
      ),
    });
  }

  const nextTheme = theme === "light" ? "dark" : "light";
  const emptyMessage = comparison
    ? "两个版本的源码没有差异"
    : "从左侧选择文件以查看代码";

  return createPortal(
    <div
      className="code-browser-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className={`code-browser-dialog is-${theme}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className="code-browser-head">
          <div className="code-browser-title-wrap">
            <span className="code-browser-title-icon"><SourceCodeIcon /></span>
            <div>
              <h2 id={titleId}>{comparison ? "版本对比" : "源码工作区"}</h2>
              <p title={project.name}>{project.name || "Agent 项目"}</p>
            </div>
          </div>
          <div className="code-browser-head-actions">
            <button
              type="button"
              className="code-browser-icon-button"
              onClick={() => setTheme(nextTheme)}
              aria-label="切换源码主题"
              title={`切换为${nextTheme === "dark" ? "深色" : "浅色"}主题`}
            >
              {theme === "light" ? <SourceDarkThemeIcon /> : <SourceLightThemeIcon />}
            </button>
            <button
              ref={closeButtonRef}
              type="button"
              className="code-browser-icon-button"
              onClick={onClose}
              aria-label="关闭源码工作区"
              title="关闭"
            >
              <SourceCloseIcon />
            </button>
          </div>
        </header>

        <div className="code-browser-workspace">
          <aside className="code-browser-sidebar" aria-label={comparison ? "变更文件" : "项目文件"}>
            <div className="code-browser-sidebar-head">
              <span>{comparison ? "变更" : "文件"}</span>
              <span>{displayFiles.length}</span>
            </div>
            <div className="code-browser-tree">
              {displayFiles.length > 0 ? (
                renderNode(tree, 0, "")
              ) : (
                <div className="code-browser-empty">{emptyMessage}</div>
              )}
            </div>
          </aside>

          <main className="code-browser-main">
            <div className="code-browser-tabs" role="tablist" aria-label="打开的文件">
              {selectedFile ? (
                <div className="code-browser-tab" role="tab" aria-selected="true">
                  <SourceFileIcon />
                  <span>{selectedFile.path.split("/").pop()}</span>
                  {renderStatus(selectedChange?.status)}
                </div>
              ) : null}
            </div>
            <div className="code-browser-path">
              <SourceFileIcon />
              <span>{selectedFile?.path ?? "未选择文件"}</span>
            </div>
            {comparison ? (
              <div className="code-browser-diff-labels" aria-label="对比方向">
                <span>{comparison.baseLabel ?? "优化前"}</span>
                <span>{comparison.targetLabel ?? "优化后"}</span>
              </div>
            ) : null}
            <div className="code-browser-editor">
              {selectedFile ? (
                <Suspense fallback={<div className="code-browser-empty">正在加载编辑器…</div>}>
                  {selectedChange ? (
                    <CodeDiffEditor
                      before={selectedChange.before}
                      after={selectedChange.after}
                      path={selectedChange.path}
                      theme={theme}
                    />
                  ) : (
                    <CodeEditor
                      value={selectedFile.content}
                      path={selectedFile.path}
                      onChange={handleEdit}
                      readOnly={readOnly}
                      theme={theme}
                    />
                  )}
                </Suspense>
              ) : (
                <div className="code-browser-empty">{emptyMessage}</div>
              )}
            </div>
            <footer className="code-browser-statusbar">
              <span>{comparison ? `${changes.length} 个文件有变更` : `${project.files.length} 个文件`}</span>
              <span>{selectedFile ? `${lineCount(selectedFile.content)} 行 · UTF-8` : "UTF-8"}</span>
            </footer>
          </main>
        </div>
      </section>
    </div>,
    document.body,
  );
}

export interface ProjectCodeBrowserProps {
  project: AgentProject;
  onChange: (project: AgentProject) => void;
  className?: string;
  label?: string;
}

/** A compact source trigger intended for topology and deploy-card headers. */
export function ProjectCodeBrowser({
  project,
  onChange,
  className = "",
  label = "查看源码",
}: ProjectCodeBrowserProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        className={`code-browser-trigger ${className}`.trim()}
        onClick={() => setOpen(true)}
        aria-label="查看和编辑项目源码"
        title={label}
      >
        <SourceCodeIcon />
        <span>{label}</span>
      </button>
      <CodeBrowserDialog
        project={project}
        open={open}
        onClose={() => setOpen(false)}
        onChange={onChange}
      />
    </>
  );
}
