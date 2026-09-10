import { forwardRef, useState, type CSSProperties, type TextareaHTMLAttributes } from "react";
import "./PromptInput.css";

export interface PromptInputProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "value" | "defaultValue" | "onSubmit"> {
  value?: string;
  defaultValue?: string;
  onSend?: (prompt: string) => void;
  sending?: boolean;
  sendLabel?: string;
  containerStyle?: CSSProperties;
}

export const PromptInput = forwardRef<HTMLTextAreaElement, PromptInputProps>(function PromptInput({
  value, defaultValue = "", onChange, onKeyDown, onSend, sending = false,
  disabled = false, readOnly = false, sendLabel = "Send prompt",
  placeholder = "Describe the agent you want to create", className = "", containerStyle,
  ...props
}, ref) {
  const [draft, setDraft] = useState(defaultValue);
  const prompt = value ?? draft;
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
        placeholder={placeholder}
        value={prompt}
        disabled={disabled}
        readOnly={readOnly}
        onChange={(event) => {
          if (value === undefined) setDraft(event.target.value);
          onChange?.(event);
        }}
        onKeyDown={onKeyDown}
      />
      <div className="studio-prompt-input__actions">
        <button type="button" className="studio-prompt-input__send" aria-label={sendLabel} disabled={!canSend} onClick={send}>
          <span className="studio-prompt-input__arrow" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
});
