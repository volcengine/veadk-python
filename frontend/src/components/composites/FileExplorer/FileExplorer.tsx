import { useEffect, useMemo, useRef, useState, type CSSProperties, type HTMLAttributes, type KeyboardEvent } from "react";
import type { CodeBlockProps } from "../CodeBlock";
import { ScrollArea } from "../../primitives/ScrollArea";
import { FileExplorerChevron, FileExplorerFileIcon, FileExplorerFolderIcon } from "./FileExplorerIcons";
import { FileExplorerPane, fileText, type FileDraft } from "./FileExplorerPane";
import "./FileExplorer.css";

export interface FileExplorerFile {
  /** 整棵文件树中稳定且唯一的标识 */
  id: string;
  name: string;
  type: "file";
  /** 文件文本，或 CodeBlock 支持的逐行内容与语法颜色 token */
  content: string | CodeBlockProps["lines"];
  /** 默认从文件名识别高亮语言，可显式覆盖；plaintext 显示纯文本 */
  language?: string;
}

export interface FileExplorerFolder {
  /** 整棵文件树中稳定且唯一的标识 */
  id: string;
  name: string;
  type: "folder";
  children: readonly FileExplorerEntry[];
}

export type FileExplorerEntry = FileExplorerFile | FileExplorerFolder;

export interface FileExplorerProps extends Omit<HTMLAttributes<HTMLDivElement>, "children" | "onSelect"> {
  entries: readonly FileExplorerEntry[];
  /** 受控打开的文件 id，null 表示尚未选择文件 */
  selectedId?: string | null;
  /** 非受控模式默认打开的文件 */
  defaultSelectedId?: string | null;
  onSelect?: (id: string, file: FileExplorerFile) => void;
  /** 受控展开的目录 id */
  expandedIds?: readonly string[];
  defaultExpandedIds?: readonly string[];
  onExpandedChange?: (ids: string[]) => void;
  /** 文件树的无障碍名称 */
  treeLabel?: string;
  /** 默认只读；开启后显示代码编辑器与保存按钮 */
  allowEdit?: boolean;
  /** 用户编辑时返回文件 id、新内容和原始文件条目 */
  onEdit?: (id: string, content: string, file: FileExplorerFile) => void;
  /** 保存草稿，可返回 Promise；未传入时保存按钮禁用 */
  onSave?: (id: string, content: string, file: FileExplorerFile) => void | Promise<void>;
  /** 默认 true，支持的语言打开时格式化；编辑过程中不自动重排 */
  autoFormat?: boolean;
  /** 默认 true，超长行按面板宽度折行，不增加行号 */
  wordWrap?: boolean;
}

interface TreeRow {
  entry: FileExplorerEntry;
  parentId?: string;
  depth: number;
  position: number;
  count: number;
}

function findFile(entries: readonly FileExplorerEntry[], id: string | null): FileExplorerFile | undefined {
  for (const entry of entries) {
    if (entry.type === "file" && entry.id === id) return entry;
    if (entry.type === "folder") {
      const found = findFile(entry.children, id);
      if (found) return found;
    }
  }
}

function visibleRows(entries: readonly FileExplorerEntry[], expanded: Set<string>, depth = 0, parentId?: string): TreeRow[] {
  return entries.flatMap((entry, index) => [
    { entry, depth, parentId, position: index + 1, count: entries.length },
    ...(entry.type === "folder" && expanded.has(entry.id) ? visibleRows(entry.children, expanded, depth + 1, entry.id) : []),
  ]);
}

export function FileExplorer({
  entries,
  selectedId,
  defaultSelectedId = null,
  onSelect,
  expandedIds,
  defaultExpandedIds = [],
  onExpandedChange,
  treeLabel = "文件",
  allowEdit = false,
  onEdit,
  onSave,
  autoFormat = true,
  wordWrap = true,
  className = "",
  ...props
}: FileExplorerProps) {
  const [localSelection, setLocalSelection] = useState(defaultSelectedId);
  const [localExpanded, setLocalExpanded] = useState(defaultExpandedIds);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<ReadonlyMap<string, FileDraft>>(new Map());
  const [savingIds, setSavingIds] = useState<ReadonlySet<string>>(new Set());
  const [errors, setErrors] = useState<ReadonlyMap<string, string | undefined>>(new Map());
  const savesInFlight = useRef(new Set<string>());
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const activeId = selectedId === undefined ? localSelection : selectedId;
  const expanded = useMemo(() => new Set(expandedIds ?? localExpanded), [expandedIds, localExpanded]);
  const rows = useMemo(() => visibleRows(entries, expanded), [entries, expanded]);
  const file = useMemo(() => findFile(entries, activeId), [entries, activeId]);
  const source = file ? fileText(file) : "";
  const storedDraft = file ? drafts.get(file.id) : undefined;
  // 保留未保存草稿；没有本地修改时接受调用方更新后的文件内容
  const draft = storedDraft && (storedDraft.content !== storedDraft.savedContent || source === storedDraft.source || source === storedDraft.savedContent) ? storedDraft : undefined;
  const tabStopId = rows.find(row => row.entry.id === focusedId)?.entry.id
    ?? rows.find(row => row.entry.id === activeId)?.entry.id
    ?? rows[0]?.entry.id;

  function editFile(content: string, baseline: string) {
    if (!file || !allowEdit) return;
    setDrafts(previous => new Map(previous).set(file.id, { source, content, savedContent: draft?.savedContent ?? baseline }));
    setErrors(previous => new Map(previous).set(file.id, undefined));
    onEdit?.(file.id, content, file);
  }

  async function saveFile(content: string) {
    if (!file || !allowEdit || !onSave || savesInFlight.current.has(file.id)) return;
    const savedFile = file;
    savesInFlight.current.add(savedFile.id);
    setSavingIds(new Set(savesInFlight.current));
    setErrors(previous => new Map(previous).set(savedFile.id, undefined));
    try {
      await onSave(savedFile.id, content, savedFile);
      if (mounted.current) setDrafts(previous => new Map(previous).set(savedFile.id, {
        source, content: previous.get(savedFile.id)?.content ?? content, savedContent: content,
      }));
    } catch {
      if (mounted.current) setErrors(previous => new Map(previous).set(savedFile.id, "保存失败，请重试"));
    } finally {
      savesInFlight.current.delete(savedFile.id);
      if (mounted.current) setSavingIds(new Set(savesInFlight.current));
    }
  }

  function toggleFolder(id: string) {
    const next = new Set(expanded);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    const ids = [...next];
    if (expandedIds === undefined) setLocalExpanded(ids);
    onExpandedChange?.(ids);
  }

  function activate(entry: FileExplorerEntry) {
    if (entry.type === "folder") toggleFolder(entry.id);
    else {
      if (selectedId === undefined) setLocalSelection(entry.id);
      onSelect?.(entry.id, entry);
    }
  }

  function focusRow(id: string | undefined) {
    if (!id) return;
    setFocusedId(id);
    const button = buttons.current.get(id);
    button?.focus({ preventScroll: true });
    button?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, row: TreeRow, index: number) {
    const { entry } = row;
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        focusRow(rows[Math.min(index + 1, rows.length - 1)]?.entry.id);
        break;
      case "ArrowUp":
        event.preventDefault();
        focusRow(rows[Math.max(index - 1, 0)]?.entry.id);
        break;
      case "ArrowRight":
        event.preventDefault();
        if (entry.type === "folder") {
          if (!expanded.has(entry.id)) toggleFolder(entry.id);
          else focusRow(entry.children[0]?.id);
        }
        break;
      case "ArrowLeft":
        event.preventDefault();
        if (entry.type === "folder" && expanded.has(entry.id)) toggleFolder(entry.id);
        else focusRow(row.parentId);
        break;
      case "Home":
        event.preventDefault();
        focusRow(rows[0]?.entry.id);
        break;
      case "End":
        event.preventDefault();
        focusRow(rows[rows.length - 1]?.entry.id);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        activate(entry);
        break;
    }
  }

  return (
    <div {...props} className={`studio-file-explorer ${className}`.trim()}>
      <ScrollArea className="studio-file-explorer__tree-area" aria-label={treeLabel}>
        <div role="tree" aria-label={treeLabel} className="studio-file-explorer__tree">
          {rows.map((row, index) => {
            const { entry } = row;
            const isFolder = entry.type === "folder";
            const isExpanded = isFolder && expanded.has(entry.id);
            const entryDraft = drafts.get(entry.id);
            return (
              <button
                key={entry.id}
                ref={button => { if (button) buttons.current.set(entry.id, button); else buttons.current.delete(entry.id); }}
                type="button"
                role="treeitem"
                className="studio-file-explorer__row"
                style={{ "--file-explorer-depth": row.depth } as CSSProperties}
                aria-level={row.depth + 1}
                aria-posinset={row.position}
                aria-setsize={row.count}
                aria-expanded={isFolder ? isExpanded : undefined}
                aria-selected={entry.type === "file" ? activeId === entry.id : undefined}
                tabIndex={tabStopId === entry.id ? 0 : -1}
                title={entry.name}
                onFocus={() => setFocusedId(entry.id)}
                onClick={() => { setFocusedId(entry.id); activate(entry); }}
                onKeyDown={event => handleKeyDown(event, row, index)}
              >
                <span className="studio-file-explorer__guides" aria-hidden="true">
                  {Array.from({ length: row.depth }, (_, level) => <span key={level} style={{ left: 16 + level * 20 }} />)}
                </span>
                <span className="studio-file-explorer__chevron" data-expanded={isExpanded || undefined}>
                  {isFolder && <FileExplorerChevron />}
                </span>
                <span className="studio-file-explorer__icon">
                  {isFolder ? <FileExplorerFolderIcon open={isExpanded} /> : <FileExplorerFileIcon name={entry.name} />}
                </span>
                <span className="studio-file-explorer__name">{entry.name}</span>
                {entry.type === "file" && entryDraft && entryDraft.content !== entryDraft.savedContent && <span className="studio-file-explorer__dirty" role="img" aria-label="未保存" title="未保存" />}
              </button>
            );
          })}
          {rows.length === 0 && <div className="studio-file-explorer__empty-tree">暂无文件</div>}
        </div>
      </ScrollArea>
        {file ? (
          <FileExplorerPane
            key={file.id}
            file={file} draft={draft} allowEdit={allowEdit} autoFormat={autoFormat} wordWrap={wordWrap}
            saving={savingIds.has(file.id)} error={errors.get(file.id)} canSave={Boolean(onSave)}
            onEdit={editFile} onSave={content => { void saveFile(content); }}
          />
        ) : <div className="studio-file-explorer__empty-content">选择文件查看内容</div>}
    </div>
  );
}
