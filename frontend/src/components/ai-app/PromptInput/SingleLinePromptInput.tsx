import { forwardRef, useState, type CSSProperties, type InputHTMLAttributes } from "react";
import "./PromptInput.css";
import "./SingleLinePromptInput.css";

export interface SingleLinePromptInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "defaultValue" | "type" | "onSubmit"> {
  value?: string;
  defaultValue?: string;
  onSend?: (prompt: string) => void;
  sending?: boolean;
  sendLabel?: string;
  containerStyle?: CSSProperties;
}

export const SingleLinePromptInput = forwardRef<HTMLInputElement, SingleLinePromptInputProps>(function SingleLinePromptInput({
  value, defaultValue = "", onChange, onSend, sending = false, disabled = false,
  readOnly = false, sendLabel = "Send prompt", placeholder = "Add anything you need to adjust",
  className = "", containerStyle, ...props
}, ref) {
  const [draft, setDraft] = useState(defaultValue);
  const prompt = value ?? draft;
  const canSend = !disabled && !readOnly && !sending && prompt.trim().length > 0;
  return (
    <div className={`studio-single-line-prompt ${className}`} style={containerStyle} aria-busy={sending || undefined}>
      <input
        {...props}
        ref={ref}
        type="text"
        className="studio-single-line-prompt__text"
        aria-label={props["aria-label"] ?? "Prompt"}
        placeholder={placeholder}
        value={prompt}
        disabled={disabled}
        readOnly={readOnly}
        onChange={event => {
          if (value === undefined) setDraft(event.target.value);
          onChange?.(event);
        }}
      />
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
