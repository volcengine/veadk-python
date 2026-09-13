import { useEffect, useState, type CSSProperties } from "react";

interface PromptPlaceholderProps {
  items: readonly string[];
  interval: number;
  paused: boolean;
}

export function PromptPlaceholder({ items, interval, paused }: PromptPlaceholderProps) {
  const [step, setStep] = useState(0);
  const delay = Number.isFinite(interval) && interval > 0 ? interval : 3000;

  useEffect(() => {
    if (paused || items.length < 2) return;
    const timer = window.setInterval(() => setStep(current => current + 1), delay);
    return () => window.clearInterval(timer);
  }, [delay, items.length, paused]);

  const index = step % items.length;
  const slide = step > 0 && items.length > 1;
  const style = { "--prompt-placeholder-duration": `${Math.min(700, delay)}ms` } as CSSProperties;

  return (
    <span className="studio-prompt-placeholder" style={style} aria-hidden="true">
      <span
        key={step}
        className={`studio-prompt-placeholder__track${slide ? " studio-prompt-placeholder__track--slide" : ""}`}
      >
        {slide && <span className="studio-prompt-placeholder__line studio-prompt-placeholder__line--outgoing">{items[(index + items.length - 1) % items.length]}</span>}
        <span className="studio-prompt-placeholder__line studio-prompt-placeholder__line--incoming">{items[index]}</span>
      </span>
    </span>
  );
}
