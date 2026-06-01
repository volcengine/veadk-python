import { useLayoutEffect, useRef } from "react";
import { ArrowUp, Loader2, Plus } from "lucide-react";
import { motion } from "motion/react";

export interface ComposerProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean; // not connected yet
  busy: boolean; // a turn is streaming
}

export function Composer({ value, onChange, onSubmit, disabled, busy }: ComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  // Auto-grow the textarea up to a max height, then scroll.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const canSend = !disabled && !busy && value.trim().length > 0;

  return (
    <div className="composer">
      <div className="composer-box">
        <button type="button" className="comp-icon" title="添加" tabIndex={-1}>
          <Plus className="icon" />
        </button>
        <textarea
          ref={ref}
          className="comp-input scroll"
          rows={1}
          value={value}
          disabled={disabled}
          placeholder={disabled ? "连接中…" : "让智能体用 UI 回答，比如「给我一张航班状态卡片」"}
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
    </div>
  );
}
