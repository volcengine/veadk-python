import { useMemo } from "react";
import type { Extension } from "@codemirror/state";
import { StreamLanguage } from "@codemirror/language";
import { lineNumbers } from "@codemirror/view";
import { javascript } from "@codemirror/lang-javascript";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { python } from "@codemirror/lang-python";
import { yaml } from "@codemirror/lang-yaml";
import { dockerFile } from "@codemirror/legacy-modes/mode/dockerfile";
import CodeMirror from "@uiw/react-codemirror";

interface CodeEditorProps {
  value: string;
  path: string;
  onChange: (value: string) => void;
  readOnly?: boolean;
  theme?: CodeWorkspaceTheme;
  lineNumberStart?: number;
  height?: string;
  minHeight?: string;
  maxHeight?: string;
}

export type CodeWorkspaceTheme = "light" | "dark";

export function languageFor(path: string): Extension[] {
  const lower = path.toLowerCase();
  const file = lower.split("/").pop() ?? lower;
  const extension = file.includes(".") ? file.split(".").pop() : "";

  if (
    file === "dockerfile" ||
    file.startsWith("dockerfile.") ||
    file.endsWith(".dockerfile")
  ) {
    return [StreamLanguage.define(dockerFile)];
  }
  if (extension === "py" || extension === "pyi") return [python()];
  if (["ts", "tsx", "mts", "cts"].includes(extension ?? "")) {
    return [javascript({ typescript: true, jsx: extension === "tsx" })];
  }
  if (["js", "jsx", "mjs", "cjs"].includes(extension ?? "")) {
    return [javascript({ jsx: extension === "jsx" })];
  }
  if (extension === "json" || extension === "jsonc") return [json()];
  if (extension === "yaml" || extension === "yml") return [yaml()];
  if (["md", "markdown"].includes(extension ?? "")) return [markdown()];
  return [];
}

export default function CodeEditor({
  value,
  path,
  onChange,
  readOnly = false,
  theme = "light",
  lineNumberStart = 1,
  height = "100%",
  minHeight,
  maxHeight,
}: CodeEditorProps) {
  const extensions = useMemo(
    () => [
      ...languageFor(path),
      ...(lineNumberStart === 1
        ? []
        : [lineNumbers({ formatNumber: (lineNumber) => String(lineNumber + lineNumberStart - 1) })]),
    ],
    [lineNumberStart, path],
  );

  return (
    <CodeMirror
      value={value}
      height={height}
      minHeight={minHeight}
      maxHeight={maxHeight}
      theme={theme}
      extensions={extensions}
      editable={!readOnly}
      onChange={onChange}
      basicSetup={{
        lineNumbers: lineNumberStart === 1,
        foldGutter: true,
        highlightActiveLine: true,
        highlightActiveLineGutter: true,
        autocompletion: false,
      }}
    />
  );
}
