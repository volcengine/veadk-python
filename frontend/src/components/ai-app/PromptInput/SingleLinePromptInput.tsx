import { forwardRef, useState, type CSSProperties, type InputHTMLAttributes } from "react";
import { PromptPlaceholder } from "./PromptPlaceholder";
import "./PromptInput.css";
import "./SingleLinePromptInput.css";

export interface SingleLinePromptInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "defaultValue" | "type" | "onSubmit"> {
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

export const SingleLinePromptInput = forwardRef<HTMLInputElement, SingleLinePromptInputProps>(function SingleLinePromptInput({
  value, defaultValue = "", onChange, onSend, sending = false, disabled = false,
  readOnly = false, sendLabel = "Send prompt", placeholder = "Add anything you need to adjust",
  className = "", containerStyle, placeholders, placeholderInterval = 3000,
  onCompositionStart, onCompositionEnd, ...props
}, ref) {
  const [draft, setDraft] = useState(defaultValue);
  const [composing, setComposing] = useState(false);
  const prompt = value ?? draft;
  const hints = placeholders?.filter(hint => hint.trim().length > 0) ?? [];
  const canSend = !disabled && !readOnly && !sending && prompt.trim().length > 0;
  return (
    <div className={`studio-single-line-prompt ${className}`} style={containerStyle} aria-busy={sending || undefined}>
      <input
        {...props}
        ref={ref}
        type="text"
        className="studio-single-line-prompt__text"
        aria-label={props["aria-label"] ?? "Prompt"}
        placeholder={hints[0] ?? placeholder}
        data-rotating-placeholder={hints.length > 0 || undefined}
        value={prompt}
        disabled={disabled}
        readOnly={readOnly}
        onChange={event => {
          if (value === undefined) setDraft(event.target.value);
          onChange?.(event);
        }}
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
      <button
        type="button"
        className="studio-prompt-input__send"
        aria-label={sendLabel}
        disabled={!canSend}
        onClick={() => { if (canSend) onSend?.(prompt); }}
      >
        <span className="studio-prompt-input__arrow" aria-hidden="true" />
      </button>
    </div>
  );
});
