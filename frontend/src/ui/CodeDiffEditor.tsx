import { useEffect, useRef, useState } from "react";
import { EditorState } from "@codemirror/state";
import { MergeView, unifiedMergeView } from "@codemirror/merge";
import CodeMirror, { basicSetup, oneDark } from "@uiw/react-codemirror";
import { languageFor, type CodeWorkspaceTheme } from "./CodeEditor";

interface CodeDiffEditorProps {
  before: string;
  after: string;
  path: string;
  theme: CodeWorkspaceTheme;
}

const COMPACT_QUERY = "(max-width: 760px)";

function useCompactDiff(): boolean {
  const [compact, setCompact] = useState(() => (
    typeof window !== "undefined" && window.matchMedia(COMPACT_QUERY).matches
  ));

  useEffect(() => {
    const media = window.matchMedia(COMPACT_QUERY);
    const update = () => setCompact(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return compact;
}

function editorExtensions(path: string, theme: CodeWorkspaceTheme) {
  return [
    basicSetup({
      lineNumbers: true,
      foldGutter: true,
      highlightActiveLine: false,
      highlightActiveLineGutter: false,
      autocompletion: false,
    }),
    ...languageFor(path),
    EditorState.readOnly.of(true),
    ...(theme === "dark" ? [oneDark] : []),
  ];
}

function SideBySideDiff({ before, after, path, theme }: CodeDiffEditorProps) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!hostRef.current) return;
    const view = new MergeView({
      a: { doc: before, extensions: editorExtensions(path, theme) },
      b: { doc: after, extensions: editorExtensions(path, theme) },
      parent: hostRef.current,
      highlightChanges: true,
      gutter: true,
      collapseUnchanged: { margin: 3, minSize: 6 },
      diffConfig: { scanLimit: 2_000, timeout: 1_000 },
    });
    return () => view.destroy();
  }, [after, before, path, theme]);

  return <div ref={hostRef} className="code-browser-merge" />;
}

export default function CodeDiffEditor(props: CodeDiffEditorProps) {
  const compact = useCompactDiff();
  if (!compact) return <SideBySideDiff {...props} />;

  return (
    <CodeMirror
      value={props.after}
      height="100%"
      theme={props.theme}
      editable={false}
      extensions={[
        ...languageFor(props.path),
        ...unifiedMergeView({
          original: props.before,
          highlightChanges: true,
          gutter: true,
          mergeControls: false,
          allowInlineDiffs: true,
          collapseUnchanged: { margin: 3, minSize: 6 },
          diffConfig: { scanLimit: 2_000, timeout: 1_000 },
        }),
      ]}
      basicSetup={{
        lineNumbers: true,
        foldGutter: true,
        highlightActiveLine: false,
        highlightActiveLineGutter: false,
        autocompletion: false,
      }}
    />
  );
}
