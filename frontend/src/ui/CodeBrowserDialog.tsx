import {
  lazy,
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import {
  ChevronRight,
  Code2,
  FileCode2,
  Folder,
  X,
} from "lucide-react";
import type { AgentProject, ProjectFile } from "../create/project";
import "./CodeBrowserDialog.css";
import { Markdown } from "./Markdown";

const CodeEditor = lazy(() => import("./CodeEditor"));

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

function sortedChildren(node: TreeNode): TreeNode[] {
  return [...node.children.values()].sort((a, b) => {
    const aFolder = a.children.size > 0 && a.path === undefined;
    const bFolder = b.children.size > 0 && b.path === undefined;
    if (aFolder !== bFolder) return aFolder ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

export interface CodeBrowserDialogProps {
  project: AgentProject;
  open: boolean;
  onClose: () => void;
  onChange: (project: AgentProject) => void;
}

export interface CodeBrowserWorkspaceProps {
  project: AgentProject;
  onChange?: (project: AgentProject) => void;
  readOnly?: boolean;
  renderMarkdown?: boolean;
  className?: string;
}

/** Reusable file tree and editor surface for editable projects and read-only artifacts. */
export function CodeBrowserWorkspace({
  project,
  onChange,
  readOnly = false,
  renderMarkdown = false,
  className = "",
}: CodeBrowserWorkspaceProps) {
  const [selected, setSelected] = useState<string | null>(
    project.files[0]?.path ?? null,
  );
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const tree = useMemo(() => buildTree(project.files), [project.files]);
  const selectedFile = project.files.find((file) => file.path === selected) ?? null;

  useEffect(() => {
    if (selectedFile || project.files.length === 0) return;
    setSelected(project.files[0].path);
  }, [project.files, selectedFile]);

  function toggleFolder(key: string) {
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function renderNode(node: TreeNode, depth: number, parentKey: string) {
    return sortedChildren(node).map((child) => {
      const key = parentKey ? `${parentKey}/${child.name}` : child.name;
      const isFolder = child.children.size > 0 && child.path === undefined;
      if (!isFolder && child.path) {
        return (
          <button
            type="button"
            key={key}
            className={`code-browser-file${selected === child.path ? " is-active" : ""}`}
            style={{ paddingLeft: `${12 + depth * 16}px` }}
            onClick={() => setSelected(child.path ?? null)}
            title={child.path}
          >
            <FileCode2 aria-hidden="true" />
            <span>{child.name}</span>
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
            <ChevronRight
              className={isCollapsed ? "" : "is-open"}
              aria-hidden="true"
            />
            <Folder aria-hidden="true" />
            <span>{child.name}</span>
          </button>
          {!isCollapsed && renderNode(child, depth + 1, key)}
        </div>
      );
    });
  }

  function handleEdit(content: string) {
    if (!selectedFile || readOnly || !onChange) return;
    onChange({
      ...project,
      files: project.files.map((file) =>
        file.path === selectedFile.path ? { ...file, content } : file,
      ),
    });
  }

  return (
    <div className={`code-browser-workspace ${className}`.trim()}>
      <aside className="code-browser-sidebar" aria-label="项目文件">
        <div className="code-browser-sidebar-head">
          文件 <span>{project.files.length}</span>
        </div>
        <div className="code-browser-tree">
          {project.files.length > 0 ? (
            renderNode(tree, 0, "")
          ) : (
            <div className="code-browser-empty">暂无项目文件</div>
          )}
        </div>
      </aside>

      <main className="code-browser-main">
        <div className="code-browser-path">
          <FileCode2 aria-hidden="true" />
          <span>{selectedFile?.path ?? "未选择文件"}</span>
          {readOnly ? <span className="code-browser-readonly">只读</span> : null}
        </div>
        <div className="code-browser-editor">
          {selectedFile ? (
            renderMarkdown && /\.md(?:own)?$/i.test(selectedFile.path) ? (
              <Markdown
                text={selectedFile.content}
                className="code-browser-markdown"
                allowRawHtml={false}
              />
            ) : (
              <Suspense
                fallback={<div className="code-browser-empty">正在加载编辑器…</div>}
              >
                <CodeEditor
                  value={selectedFile.content}
                  path={selectedFile.path}
                  onChange={handleEdit}
                  readOnly={readOnly}
                />
              </Suspense>
            )
          ) : (
            <div className="code-browser-empty">从左侧选择文件以查看内容</div>
          )}
        </div>
      </main>
    </div>
  );
}

/** Browse and edit generated project files without leaving the deploy view. */
export function CodeBrowserDialog({
  project,
  open,
  onClose,
  onChange,
}: CodeBrowserDialogProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, open]);

  if (!open) return null;

  return createPortal(
    <div
      className="code-browser-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="code-browser-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="code-browser-title"
      >
        <header className="code-browser-head">
          <div className="code-browser-title-wrap">
            <span className="code-browser-title-icon" aria-hidden="true">
              <Code2 />
            </span>
            <div>
              <h2 id="code-browser-title">项目代码</h2>
              <p>{project.name || "Agent 项目"}</p>
            </div>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="code-browser-close"
            onClick={onClose}
            aria-label="关闭代码浏览器"
          >
            <X aria-hidden="true" />
          </button>
        </header>

        <CodeBrowserWorkspace project={project} onChange={onChange} />
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
        <Code2 aria-hidden="true" />
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
