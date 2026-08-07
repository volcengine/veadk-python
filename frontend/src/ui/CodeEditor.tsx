import { useMemo } from "react";
import { StreamLanguage } from "@codemirror/language";
import type { Extension } from "@codemirror/state";
import { javascript } from "@codemirror/lang-javascript";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { python } from "@codemirror/lang-python";
import { yaml } from "@codemirror/lang-yaml";
import { shell } from "@codemirror/legacy-modes/mode/shell";
import CodeMirror from "@uiw/react-codemirror";

interface CodeEditorProps {
  value: string;
  path: string;
  onChange: (value: string) => void;
  readOnly?: boolean;
}

function languageFor(path: string): Extension[] {
  const lower = path.toLowerCase();
  const file = lower.split("/").pop() ?? lower;
  const extension = file.includes(".") ? file.split(".").pop() : "";

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
  if (["sh", "bash", "zsh"].includes(extension ?? "")) {
    return [StreamLanguage.define(shell)];
  }
  return [];
}

export default function CodeEditor({
  value,
  path,
  onChange,
  readOnly = false,
}: CodeEditorProps) {
  const extensions = useMemo(() => languageFor(path), [path]);
  const editorOptions = { editable: !readOnly };

  return (
    <CodeMirror
      {...editorOptions}
      value={value}
      height="100%"
      theme="light"
      extensions={extensions}
      onChange={onChange}
      basicSetup={{
        lineNumbers: true,
        foldGutter: true,
        highlightActiveLine: true,
        highlightActiveLineGutter: true,
        autocompletion: false,
      }}
    />
  );
}
