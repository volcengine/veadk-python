import { useMemo } from "react";
import { EditorView } from "@codemirror/view";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags } from "@lezer/highlight";
import CodeEditor from "../../../ui/CodeEditor";

const theme = EditorView.theme({
  "&": { backgroundColor: "transparent", color: "var(--studio-code-text)", fontSize: "13px" },
  "&.cm-focused": { outline: "none" },
  ".cm-scroller": { fontFamily: '"Geist Mono", "Noto Sans SC", monospace', lineHeight: "19.5px", overflow: "visible" },
  ".cm-content": { padding: "12px 0 16px", caretColor: "var(--studio-text-primary)" },
  ".cm-line": { padding: "0 16px" },
  ".cm-gutters": { backgroundColor: "var(--studio-surface-input)", color: "var(--studio-code-line-number)", border: "none" },
  ".cm-lineNumbers .cm-gutterElement": { minWidth: "26px", padding: "0 4px" },
  ".cm-activeLine, .cm-activeLineGutter": { backgroundColor: "var(--studio-fill-hover)" },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--studio-text-primary)" },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection": { backgroundColor: "var(--studio-fill-active)" },
});

const highlighting = syntaxHighlighting(HighlightStyle.define([
  { tag: tags.comment, color: "var(--studio-code-comment)" },
  { tag: [tags.keyword, tags.operatorKeyword], color: "var(--studio-code-keyword)" },
  { tag: [tags.string, tags.attributeValue], color: "var(--studio-code-string)" },
  { tag: [tags.number, tags.bool, tags.null], color: "var(--studio-code-number)" },
  { tag: [tags.function(tags.variableName), tags.function(tags.propertyName)], color: "var(--studio-code-function)" },
  { tag: [tags.typeName, tags.className], color: "var(--studio-code-constant)" },
  { tag: [tags.tagName, tags.attributeName], color: "var(--studio-code-variable)" },
]));

export function FileExplorerEditor({ value, name, language, wordWrap, onChange }: {
  value: string;
  name: string;
  language?: string;
  wordWrap: boolean;
  onChange: (content: string) => void;
}) {
  const extensions = useMemo(() => [theme, highlighting, EditorView.contentAttributes.of({ "aria-label": `${name} 编辑器` }), ...(wordWrap ? [EditorView.lineWrapping] : [])], [name, wordWrap]);
  const languageExtensions: Record<string, string> = { javascript: "jsx", typescript: "tsx", python: "py", markdown: "md", yaml: "yaml", json: "json" };
  const extension = language && Object.prototype.hasOwnProperty.call(languageExtensions, language) ? languageExtensions[language] : undefined;
  const path = language === "plaintext" ? "file.txt" : extension ? `file.${extension}` : name;
  return <div className="studio-file-explorer__editor">
    <CodeEditor value={value} path={path} theme="none" height="auto" extensions={extensions} onChange={onChange} />
  </div>;
}
