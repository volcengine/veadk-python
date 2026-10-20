import { forwardRef, useState, type CSSProperties, type TextareaHTMLAttributes } from "react";
import { PromptPlaceholder } from "./PromptPlaceholder";
import "./PromptInput.css";

export interface PromptInputProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "value" | "defaultValue" | "onSubmit"> {
  value?: string;
  defaultValue?: string;
  onSend?: (prompt: string) => void;
  sending?: boolean;
  sendLabel?: string;
  containerStyle?: CSSProperties;
  /** 输入为空时循环显示的提示词列表，未传或为空时使用 placeholder */
  placeholders?: readonly string[];
  /** 提示词切换间隔，单位毫秒 */
  placeholderInterval?: number;
}

export const PromptInput = forwardRef<HTMLTextAreaElement, PromptInputProps>(function PromptInput({
  value, defaultValue = "", onChange, onKeyDown, onSend, sending = false,
  disabled = false, readOnly = false, sendLabel = "Send prompt",
  placeholder = "Describe the agent you want to create", className = "", containerStyle,
  placeholders, placeholderInterval = 3000, onCompositionStart, onCompositionEnd,
  ...props
}, ref) {
  const [draft, setDraft] = useState(defaultValue);
  const [composing, setComposing] = useState(false);
  const prompt = value ?? draft;
  const hints = placeholders?.filter(hint => hint.trim().length > 0) ?? [];
  const canSend = !disabled && !readOnly && !sending && prompt.trim().length > 0;
  function send() {
    if (canSend) onSend?.(prompt);
  }
  return (
    <div className={`studio-prompt-input ${className}`} style={containerStyle} aria-busy={sending || undefined}>
      <textarea
        {...props}
        ref={ref}
        aria-label={props["aria-label"] ?? "Prompt"}
        className="studio-prompt-input__text"
        placeholder={hints[0] ?? placeholder}
        data-rotating-placeholder={hints.length > 0 || undefined}
        value={prompt}
        disabled={disabled}
        readOnly={readOnly}
        onChange={(event) => {
          if (value === undefined) setDraft(event.target.value);
          onChange?.(event);
        }}
        onKeyDown={onKeyDown}
        onCompositionStart={event => {
          setComposing(true);
          onCompositionStart?.(event);
        }}
        onCompositionEnd={event => {
          setComposing(false);
          onCompositionEnd?.(event);
        }}
      />
      {prompt.length === 0 && !composing && hints.length > 0 && (
        <PromptPlaceholder key={JSON.stringify(hints)} items={hints} interval={placeholderInterval} paused={disabled || readOnly} />
      )}
      <div className="studio-prompt-input__actions">
        <button type="button" className="studio-prompt-input__send" aria-label={sendLabel} disabled={!canSend} onClick={send}>
          <span className="studio-prompt-input__arrow" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
});
