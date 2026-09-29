import { createContext, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { ConversationBlock, ConversationMessage, ConversationStatus, ConversationStep } from "./ConversationFlow.types";

interface EntranceContext {
  seen: Set<string>;
  path: readonly string[];
}

const Context = createContext<EntranceContext | null>(null);

function rememberSteps(seen: Set<string>, path: readonly string[], blocks: readonly (ConversationBlock | ConversationStep)[]) {
  for (const block of blocks) {
    if (block.type !== "reasoning" && block.type !== "tool" && block.type !== "handoff") continue;
    const stepPath = [...path, block.id];
    seen.add(JSON.stringify(stepPath));
    if (block.type === "handoff" && block.steps) rememberSteps(seen, stepPath, block.steps);
  }
}

function rememberMessages(seen: Set<string>, messages: readonly ConversationMessage[]) {
  for (const message of messages) {
    rememberSteps(seen, [message.id], message.blocks ?? (message.role === "assistant" ? message.steps : undefined) ?? []);
  }
}

export function ConversationStepEntranceProvider({ messages, children }: { messages: readonly ConversationMessage[]; children: ReactNode }) {
  const registry = useRef<Set<string> | null>(null);
  if (registry.current === null) {
    registry.current = new Set();
    rememberMessages(registry.current, messages);
  }
  const seen = registry.current;
  const value = useMemo(() => ({ seen, path: [] }), [seen]);
  // Retain collapsed steps, but forget removed runs so a retry can reuse their IDs
  useLayoutEffect(() => {
    seen.clear();
    rememberMessages(seen, messages);
  }, [seen, messages]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function ConversationMessageEntranceScope({ messageId, children }: { messageId: string; children: ReactNode }) {
  const parent = useContext(Context);
  const value = useMemo(() => parent && ({ seen: parent.seen, path: [messageId] }), [parent, messageId]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function ConversationStepEntrance({ stepId, type, status, className = "", children }: {
  stepId: string;
  type: "reasoning" | "tool" | "handoff";
  status: ConversationStatus;
  className?: string;
  children: ReactNode;
}) {
  const parent = useContext(Context);
  const value = useMemo(() => parent && ({ seen: parent.seen, path: [...parent.path, stepId] }), [parent, stepId]);
  const [entering, setEntering] = useState(() => Boolean(value && !value.seen.has(JSON.stringify(value.path)) &&
    (typeof window === "undefined" || !window.matchMedia("(prefers-reduced-motion: reduce)").matches)));

  useEffect(() => {
    if (!entering) return;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const stopForReducedMotion = () => { if (preference.matches) setEntering(false); };
    stopForReducedMotion();
    preference.addEventListener("change", stopForReducedMotion);
    return () => preference.removeEventListener("change", stopForReducedMotion);
  }, [entering]);

  return <Context.Provider value={value}>
    <div className={`studio-conversation-step ${className}`.trim()} data-step-id={stepId} data-type={type} data-status={status} data-entering={entering || undefined}
      onFocusCapture={() => setEntering(false)} onPointerDownCapture={() => setEntering(false)}>
      <div className="studio-conversation-step__entry-content" onAnimationEnd={event => {
        if (event.target === event.currentTarget && event.animationName === "studio-conversation-step-content-in") setEntering(false);
      }}>{children}</div>
    </div>
  </Context.Provider>;
}
