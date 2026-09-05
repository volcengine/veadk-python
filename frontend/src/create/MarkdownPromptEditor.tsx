import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
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

const TRANSLATION_KEYS: Record<string, string> = {
  "toolbar.undo": "promptEditor.toolbar.undo",
  "toolbar.redo": "promptEditor.toolbar.redo",
  "toolbar.blockTypes.paragraph": "promptEditor.toolbar.paragraph",
  "toolbar.blockTypes.quote": "promptEditor.toolbar.quote",
  "toolbar.blockTypes.heading": "promptEditor.toolbar.heading",
  "toolbar.blockTypeSelect.selectBlockTypeTooltip": "promptEditor.toolbar.selectBlockType",
  "toolbar.blockTypeSelect.placeholder": "promptEditor.toolbar.blockType",
  "toolbar.bold": "promptEditor.toolbar.bold",
  "toolbar.removeBold": "promptEditor.toolbar.removeBold",
  "toolbar.italic": "promptEditor.toolbar.italic",
  "toolbar.removeItalic": "promptEditor.toolbar.removeItalic",
  "toolbar.bulletedList": "promptEditor.toolbar.bulletedList",
  "toolbar.numberedList": "promptEditor.toolbar.numberedList",
};

export default function MarkdownPromptEditor({
  value,
  onChange,
  invalid = false,
}: {
  value: string;
  onChange: (value: string) => void;
  invalid?: boolean;
}) {
  const { t } = useTranslation("create");
  const editorRef = useRef<MDXEditorMethods>(null);
  const lastPublishedValue = useRef(value);
  const [plainTextFallback, setPlainTextFallback] = useState(false);
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
  const translate = useMemo(
    () => (
      key: string,
      defaultValue: string,
      interpolations?: Record<string, unknown>,
    ) => {
      const translationKey = TRANSLATION_KEYS[key];
      if (!translationKey) return defaultValue;
      return t(translationKey, interpolations);
    },
    [t],
  );

  useEffect(() => {
    if (value !== lastPublishedValue.current) {
      if (!plainTextFallback) {
        editorRef.current?.setMarkdown(value);
      }
      lastPublishedValue.current = value;
    }
  }, [plainTextFallback, value]);

  if (plainTextFallback) {
    return (
      <div>
        <textarea
          className={`cw-markdown-fallback${invalid ? " is-error" : ""}`}
          value={value}
          aria-invalid={invalid}
          spellCheck={false}
          onChange={(event) => {
            const nextValue = event.target.value;
            lastPublishedValue.current = nextValue;
            onChange(nextValue);
          }}
        />
      </div>
    );
  }

  return (
    <div>
      <MDXEditor
        ref={editorRef}
        className={`cw-markdown-editor${invalid ? " is-error" : ""}`}
        contentEditableClassName="cw-markdown-content"
        markdown={value}
        placeholder={t("promptEditor.placeholder")}
        plugins={plugins}
        suppressHtmlProcessing
        trim={false}
        translation={translate}
        onChange={(markdown, initialMarkdownNormalize) => {
          lastPublishedValue.current = markdown;
          if (!initialMarkdownNormalize) {
            onChange(markdown);
          }
        }}
        onError={() => setPlainTextFallback(true)}
      />
    </div>
  );
}
