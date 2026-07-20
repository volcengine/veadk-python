import { useEffect, useMemo, useRef, useState } from "react";
import {
  BlockTypeSelect,
  BoldItalicUnderlineToggles,
  headingsPlugin,
  listsPlugin,
  ListsToggle,
  markdownShortcutPlugin,
  MDXEditor,
  type MDXEditorMethods,
  quotePlugin,
  toolbarPlugin,
  UndoRedo,
} from "@mdxeditor/editor";
import "@mdxeditor/editor/style.css";

const TRANSLATIONS: Record<string, string> = {
  "toolbar.undo": "撤销 {{shortcut}}",
  "toolbar.redo": "重做 {{shortcut}}",
  "toolbar.blockTypes.paragraph": "正文",
  "toolbar.blockTypes.quote": "引用",
  "toolbar.blockTypes.heading": "标题 {{level}}",
  "toolbar.blockTypeSelect.selectBlockTypeTooltip": "选择文本类型",
  "toolbar.blockTypeSelect.placeholder": "文本类型",
  "toolbar.bold": "加粗",
  "toolbar.removeBold": "取消加粗",
  "toolbar.italic": "斜体",
  "toolbar.removeItalic": "取消斜体",
  "toolbar.bulletedList": "无序列表",
  "toolbar.numberedList": "有序列表",
};

function translate(
  key: string,
  defaultValue: string,
  interpolations?: Record<string, unknown>,
) {
  let value = TRANSLATIONS[key] ?? defaultValue;
  for (const [name, replacement] of Object.entries(interpolations ?? {})) {
    value = value.split(`{{${name}}}`).join(String(replacement));
  }
  return value;
}

export default function MarkdownPromptEditor({
  value,
  onChange,
  invalid = false,
}: {
  value: string;
  onChange: (value: string) => void;
  invalid?: boolean;
}) {
  const editorRef = useRef<MDXEditorMethods>(null);
  const lastPublishedValue = useRef(value);
  const [parseError, setParseError] = useState("");
  const plugins = useMemo(
    () => [
      headingsPlugin({ allowedHeadingLevels: [1, 2, 3] }),
      listsPlugin(),
      quotePlugin(),
      markdownShortcutPlugin(),
      toolbarPlugin({
        toolbarClassName: "cw-markdown-toolbar",
        toolbarContents: () => (
          <>
            <UndoRedo />
            <BlockTypeSelect />
            <BoldItalicUnderlineToggles options={["Bold", "Italic"]} />
            <ListsToggle options={["bullet", "number"]} />
          </>
        ),
      }),
    ],
    [],
  );

  useEffect(() => {
    if (value !== lastPublishedValue.current) {
      editorRef.current?.setMarkdown(value);
      lastPublishedValue.current = value;
      setParseError("");
    }
  }, [value]);

  return (
    <div>
      <MDXEditor
        ref={editorRef}
        className={`cw-markdown-editor${invalid ? " is-error" : ""}`}
        contentEditableClassName="cw-markdown-content"
        markdown={value}
        placeholder="输入系统提示词；键入 ## 加空格可创建二级标题…"
        plugins={plugins}
        suppressHtmlProcessing
        trim={false}
        translation={translate}
        onChange={(markdown, initialMarkdownNormalize) => {
          lastPublishedValue.current = markdown;
          setParseError("");
          if (!initialMarkdownNormalize) {
            onChange(markdown);
          }
        }}
        onError={({ error }) => setParseError(error)}
      />
      {parseError && (
        <span className="cw-markdown-error" role="alert">
          Markdown 内容暂时无法解析，请检查未闭合的语法。
        </span>
      )}
    </div>
  );
}
