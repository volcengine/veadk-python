import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { parseDocument, stringify } from "yaml";
import { Markdown } from "../Markdown";
import CodeEditor from "../CodeEditor";

export interface PreviewFile {
  path: string;
  size: number;
  content?: string;
  kind?: "text" | "image" | "binary";
  mimeType?: string;
}

interface TreeNode {
  name: string;
  path: string;
  file?: PreviewFile;
  children: TreeNode[];
}

interface MarkdownDocument {
  body: string;
  frontmatter: Array<{ key: string; value: string }>;
}

function parseMarkdownDocument(value: string): MarkdownDocument {
  const lines = value.split(/\r?\n/);
  if (lines[0]?.trim() !== "---") return { body: value, frontmatter: [] };
  const closing = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
  if (closing < 0) return { body: value, frontmatter: [] };
  const document = parseDocument(lines.slice(1, closing).join("\n"));
  if (document.errors.length > 0) return { body: value, frontmatter: [] };
  const metadata = document.toJS();
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
    return { body: value, frontmatter: [] };
  }
  return {
    body: lines.slice(closing + 1).join("\n").replace(/^\s*\n/, ""),
    frontmatter: Object.entries(metadata as Record<string, unknown>).map(([key, item]) => ({
      key,
      value: typeof item === "string" ? item : stringify(item).trim(),
    })),
  };
}

function FolderIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M2.75 5.5h5l1.5 1.75h8v7.25a1.75 1.75 0 0 1-1.75 1.75h-11a1.75 1.75 0 0 1-1.75-1.75v-9Z" />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M5 2.75h6l4 4v10.5H5z" />
      <path d="M11 2.75v4h4" />
    </svg>
  );
}

function buildTree(files: PreviewFile[]): TreeNode[] {
  const root: TreeNode = { name: "", path: "", children: [] };
  for (const file of files) {
    let parent = root;
    const parts = file.path.split("/").filter(Boolean);
    parts.forEach((part, index) => {
      let node = parent.children.find((child) => child.name === part);
      if (!node) {
        const path = parts.slice(0, index + 1).join("/");
        node = { name: part, path, children: [] };
        parent.children.push(node);
      }
      if (index === parts.length - 1) node.file = file;
      parent = node;
    });
  }
  const sort = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => {
      const folderOrder = Number(Boolean(a.file)) - Number(Boolean(b.file));
      return folderOrder || a.name.localeCompare(b.name);
    });
    nodes.forEach((node) => sort(node.children));
  };
  sort(root.children);
  return root.children;
}

function FileRows({
  nodes,
  depth,
  activePath,
  onSelect,
}: {
  nodes: TreeNode[];
  depth: number;
  activePath: string;
  onSelect: (file: PreviewFile) => void;
}) {
  return nodes.map((node) => (
    <div key={node.path}>
      {node.file ? (
        <button
          type="button"
          className={`skill-file-tree__row${node.path === activePath ? " is-active" : ""}`}
          style={{ paddingLeft: `${12 + depth * 16}px` }}
          onClick={() => onSelect(node.file as PreviewFile)}
          title={node.path}
        >
          <FileIcon />
          <span>{node.name}</span>
          <small>{node.file.size.toLocaleString()} B</small>
        </button>
      ) : (
        <div
          className="skill-file-tree__row is-folder"
          style={{ paddingLeft: `${12 + depth * 16}px` }}
          title={node.path}
        >
          <FolderIcon />
          <span>{node.name}</span>
        </div>
      )}
      {node.children.length > 0 ? (
        <FileRows
          nodes={node.children}
          depth={depth + 1}
          activePath={activePath}
          onSelect={onSelect}
        />
      ) : null}
    </div>
  ));
}

function downloadFile(file: PreviewFile) {
  if (file.content === undefined) return;
  if (file.content.startsWith("data:")) {
    const link = document.createElement("a");
    link.href = file.content;
    link.download = file.path.split("/").pop() || "skill-file";
    link.click();
    return;
  }
  const url = URL.createObjectURL(new Blob([file.content]));
  const link = document.createElement("a");
  link.href = url;
  link.download = file.path.split("/").pop() || "skill-file";
  link.click();
  URL.revokeObjectURL(url);
}

export function SkillFileTree({ files }: { files: PreviewFile[] }) {
  const { t, i18n } = useTranslation("skills");
  const tree = useMemo(() => buildTree(files), [files]);
  const [activePath, setActivePath] = useState(files[0]?.path || "");
  const [markdownMode, setMarkdownMode] = useState<"preview" | "source">("preview");
  const active = files.find((file) => file.path === activePath) || files[0];
  const lower = active?.path.toLowerCase() || "";
  const markdown = lower.endsWith(".md") || lower.endsWith(".markdown");
  const image = /\.(png|jpe?g|gif|webp|svg)$/.test(lower);
  const markdownDocument = useMemo(
    () => parseMarkdownDocument(markdown && active?.content !== undefined ? active.content : ""),
    [active?.content, markdown],
  );

  return (
    <div className="skill-file-browser">
      <aside className="skill-file-tree" aria-label={t("fileTree.ariaLabel")}>
        <FileRows
          nodes={tree}
          depth={0}
          activePath={active?.path || ""}
          onSelect={(file) => setActivePath(file.path)}
        />
      </aside>
      <section className="skill-file-preview">
        {active ? (
          <>
            <header>
              <span title={active.path}>{active.path}</span>
              <div>
                {markdown ? (
                  <button type="button" onClick={() => setMarkdownMode((mode) => mode === "preview" ? "source" : "preview")}>
                    {markdownMode === "preview" ? t("fileTree.viewSource") : t("fileTree.viewPreview")}
                  </button>
                ) : null}
                <button type="button" disabled={active.content === undefined} onClick={() => downloadFile(active)}>{t("fileTree.download")}</button>
              </div>
            </header>
            <div className="skill-file-preview__body">
              {active.kind === "binary" || active.content === undefined ? (
                <div className="skill-file-preview__binary">
                  <strong>{t("fileTree.binaryFile")}</strong>
                  <span>{t("fileTree.bytes", { value: new Intl.NumberFormat(i18n.resolvedLanguage).format(active.size) })}</span>
                  <span>{t("fileTree.binaryDescription")}</span>
                </div>
              ) : image ? (
                <img src={active.content.startsWith("data:") ? active.content : `data:image/svg+xml;charset=utf-8,${encodeURIComponent(active.content)}`} alt={active.path} />
              ) : markdown && markdownMode === "preview" ? (
                <div className="skill-file-preview__markdown">
                  {markdownDocument.frontmatter.length > 0 ? (
                    <dl className="skill-file-preview__frontmatter" aria-label={t("fileTree.metadata")}>
                      {markdownDocument.frontmatter.map((item) => (
                        <div key={item.key}>
                          <dt>{item.key}</dt>
                          <dd>{item.value}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : null}
                  <Markdown text={markdownDocument.body} allowRawHtml={false} className="skill-file-preview__markdown-body" />
                </div>
              ) : (
                <CodeEditor value={active.content} path={active.path} readOnly onChange={() => undefined} />
              )}
            </div>
          </>
        ) : (
          <div className="skill-file-preview__binary">{t("fileTree.noFiles")}</div>
        )}
      </section>
    </div>
  );
}
