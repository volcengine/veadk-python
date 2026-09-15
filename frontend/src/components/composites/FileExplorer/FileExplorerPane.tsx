import { lazy, Suspense, useEffect, useState } from "react";
import { CodeBlock } from "../CodeBlock";
import { Button } from "../../primitives/Button";
import { Loading } from "../../primitives/Loading";
import { formatFileContent } from "./formatFileContent";
import { filePresentation } from "./FileExplorerFileTypes";
import type { FileExplorerFile } from "./FileExplorer";

const FileExplorerEditor = lazy(() => import("./FileExplorerEditor").then(module => ({ default: module.FileExplorerEditor })));

export function fileText(file: FileExplorerFile): string {
  return typeof file.content === "string" ? file.content : file.content.map(line => typeof line === "string" ? line : line.map(token => token.text).join("")).join("\n");
}

export interface FileDraft {
  source: string;
  content: string;
  savedContent: string;
}

function SaveIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 3.5h11L20.5 8v11a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19V5A1.5 1.5 0 0 1 5 3.5Z" />
    <path d="M7.5 3.5v6h8v-6M7.5 20.5v-7h9v7M13 5.5v2" />
  </svg>;
}

export function FileExplorerPane({ file, draft, allowEdit, autoFormat, wordWrap, saving, error, canSave, onEdit, onSave }: {
  file: FileExplorerFile;
  draft?: FileDraft;
  allowEdit: boolean;
  autoFormat: boolean;
  wordWrap: boolean;
  saving: boolean;
  error?: string;
  canSave: boolean;
  onEdit: (content: string, baseline: string) => void;
  onSave: (content: string) => void;
}) {
  const source = fileText(file);
  const language = file.language ?? filePresentation(file.name).language;
  const hasDraft = draft !== undefined;
  const [formatted, setFormatted] = useState<{ source: string; language?: string; name: string; content: string; error?: string }>();
  useEffect(() => {
    if (!autoFormat || hasDraft) return;
    let cancelled = false;
    formatFileContent(source, file.name, language).then(content => {
      if (!cancelled) setFormatted({ source, language, name: file.name, content });
    }, () => {
      if (!cancelled) setFormatted({ source, language, name: file.name, content: source, error: "无法格式化，已保留原文" });
    });
    return () => { cancelled = true; };
  }, [source, file.name, language, autoFormat, hasDraft]);
  const ready = !autoFormat || (formatted?.source === source && formatted.language === language && formatted.name === file.name);
  const baseline = autoFormat && ready ? formatted?.content ?? source : source;
  const content = draft?.content ?? baseline;
  const dirty = draft ? draft.content !== draft.savedContent : false;
  const loading = <div className="studio-file-explorer__editor-loading"><Loading size={28} /></div>;

  return <div className="studio-file-explorer__pane">
    <CodeBlock
      className="studio-file-explorer__code"
      title={file.name}
      language={language}
      wordWrap={wordWrap}
      scrollAreaProps={{ orientation: wordWrap ? "vertical" : "both", className: "studio-file-explorer__content", "aria-label": `${file.name} 文件内容`, tabIndex: 0 }}
      lines={!draft && !autoFormat && typeof file.content !== "string" ? file.content : content.split("\n")}
      onKeyDown={event => {
        if (allowEdit && (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s" && !event.nativeEvent.isComposing) {
          event.preventDefault();
          if (canSave && dirty && !saving) onSave(content);
        }
      }}
      actions={allowEdit ? <Button
        variant="ghost" iconOnly startIcon={<SaveIcon />}
        aria-label={`保存 ${file.name}`} title={!canSave ? "未配置保存操作" : dirty ? "保存文件" : "没有未保存的修改"}
        disabled={!canSave || !dirty} loading={saving} onClick={() => onSave(content)}
      /> : undefined}
    >
      {allowEdit ? (ready || draft ? <Suspense fallback={loading}>
        <FileExplorerEditor name={file.name} language={language} value={content} wordWrap={wordWrap} onChange={value => onEdit(value, baseline)} />
      </Suspense> : loading) : undefined}
    </CodeBlock>
    {error ? <div className="studio-file-explorer__message studio-file-explorer__message--error" role="alert">{error}</div>
      : autoFormat && ready && formatted?.error ? <div className="studio-file-explorer__message" role="status">{formatted.error}</div> : null}
  </div>;
}
