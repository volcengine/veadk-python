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

/** Browse and edit generated project files without leaving the deploy view. */
export function CodeBrowserDialog({
  project,
  open,
  onClose,
  onChange,
}: CodeBrowserDialogProps) {
  const [selected, setSelected] = useState<string | null>(
    project.files[0]?.path ?? null,
  );
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const tree = useMemo(() => buildTree(project.files), [project.files]);
  const selectedFile = project.files.find((file) => file.path === selected) ?? null;

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

  useEffect(() => {
    if (selectedFile || project.files.length === 0) return;
    setSelected(project.files[0].path);
  }, [project.files, selectedFile]);

  if (!open) return null;

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
    if (!selectedFile) return;
    onChange({
      ...project,
      files: project.files.map((file) =>
        file.path === selectedFile.path ? { ...file, content } : file,
      ),
    });
  }

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

        <div className="code-browser-workspace">
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
            </div>
            <div className="code-browser-editor">
              {selectedFile ? (
                <Suspense
                  fallback={<div className="code-browser-empty">正在加载编辑器…</div>}
                >
                  <CodeEditor
                    value={selectedFile.content}
                    path={selectedFile.path}
                    onChange={handleEdit}
                  />
                </Suspense>
              ) : (
                <div className="code-browser-empty">从左侧选择文件以查看代码</div>
              )}
            </div>
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
}

/** A compact source trigger intended for topology and deploy-card headers. */
export function ProjectCodeBrowser({
  project,
  onChange,
  className = "",
}: ProjectCodeBrowserProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        className={`code-browser-trigger ${className}`.trim()}
        onClick={() => setOpen(true)}
        aria-label="查看和编辑项目源码"
        title="查看源码"
      >
        <Code2 aria-hidden="true" />
        <span>查看源码</span>
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
