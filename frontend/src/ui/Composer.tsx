import { useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, FileText, ImageIcon, Loader2, Plus, X } from "lucide-react";
import { motion } from "motion/react";
import type { Attachment } from "../adk/client";

export interface ComposerProps {
  sessionId: string;
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean; // not connected yet
  busy: boolean; // a turn is streaming
  attachments: Attachment[];
  onAddFiles: (files: FileList | File[]) => void;
  onRemoveAttachment: (index: number) => void;
}

export function Composer({
  sessionId,
  value,
  onChange,
  onSubmit,
  disabled,
  busy,
  attachments,
  onAddFiles,
  onRemoveAttachment,
}: ComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  // Auto-grow the textarea up to a max height, then scroll.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const canSend =
    !disabled && !busy && (value.trim().length > 0 || attachments.length > 0);

  function pick(input: React.RefObject<HTMLInputElement>) {
    setMenuOpen(false);
    input.current?.click();
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length) onAddFiles(e.target.files);
    e.target.value = ""; // allow re-picking the same file
  }

  return (
    <div className="composer">
      {attachments.length > 0 && (
        <div className="attachment-row">
          {attachments.map((a, i) => (
            <AttachmentChip
              key={i}
              mimeType={a.mimeType}
              data={a.data}
              name={a.name}
              onRemove={() => onRemoveAttachment(i)}
            />
          ))}
        </div>
      )}

      <div className="composer-box">
        <div className="composer-menu-wrap">
          <button
            type="button"
            className="comp-icon"
            title="添加"
            aria-label="添加"
            disabled={disabled}
            onClick={() => setMenuOpen((o) => !o)}
          >
            <Plus className="icon" />
          </button>
          {menuOpen && (
            <>
              <div className="menu-scrim" onClick={() => setMenuOpen(false)} />
              <div className="composer-menu" role="menu">
                <button
                  type="button"
                  className="menu-item"
                  onClick={() => pick(imageInput)}
                >
                  <ImageIcon className="icon" />
                  上传图片
                </button>
                <button
                  type="button"
                  className="menu-item"
                  onClick={() => pick(fileInput)}
                >
                  <FileText className="icon" />
                  上传文件 (PDF)
                </button>
              </div>
            </>
          )}
        </div>

        <textarea
          ref={ref}
          className="comp-input scroll"
          rows={1}
          value={value}
          disabled={disabled}
          placeholder={disabled ? "请选择 Agent" : "给智能体发消息…"}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (canSend) onSubmit();
            }
          }}
        />
        <motion.button
          type="button"
          className="comp-send"
          disabled={!canSend}
          onClick={onSubmit}
          aria-label="发送"
          whileTap={canSend ? { scale: 0.9 } : undefined}
          transition={{ type: "spring", stiffness: 600, damping: 22 }}
        >
          {busy ? <Loader2 className="icon spin" /> : <ArrowUp className="icon" />}
        </motion.button>
      </div>

      <div className="composer-meta">
        <span className="composer-session-line">
          会话 ID：
          <span className="composer-session-id" title={sessionId || undefined}>
            {sessionId || "—"}
          </span>
        </span>
        <span className="composer-meta-separator" aria-hidden>
          |
        </span>
        <span>回答仅供参考</span>
      </div>

      {/* hidden pickers */}
      <input
        ref={imageInput}
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={onInputChange}
      />
      <input
        ref={fileInput}
        type="file"
        accept="application/pdf"
        multiple
        hidden
        onChange={onInputChange}
      />
    </div>
  );
}

function AttachmentChip({
  mimeType,
  data,
  name,
  onRemove,
}: {
  mimeType: string;
  data: string;
  name?: string;
  onRemove: () => void;
}) {
  const isImage = mimeType.startsWith("image/");
  return (
    <div className={isImage ? "attachment-thumb-wrap" : "attachment-file"}>
      {isImage ? (
        <img
          className="attachment-thumb"
          src={`data:${mimeType};base64,${data}`}
          alt={name ?? "image"}
        />
      ) : (
        <>
          <FileText className="icon" />
          <span className="attachment-file-name">{name ?? "file.pdf"}</span>
        </>
      )}
      <button
        type="button"
        className="attachment-remove"
        aria-label="移除"
        onClick={onRemove}
      >
        <X className="icon" />
      </button>
    </div>
  );
}
