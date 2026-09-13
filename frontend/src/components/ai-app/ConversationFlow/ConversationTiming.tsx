import { createContext, useCallback, useContext, useLayoutEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import type { ConversationMessage, ConversationStatus } from "./ConversationFlow.types";

type TimingKind = "message" | "step";
type Timing = { status?: ConversationStatus; durationMs?: number; startedAt?: number; endedAt?: number };
type TimingRecord = {
  input: Timing;
  running: boolean;
  startedAt?: number;
  endedAt?: number;
  anchorAt: number;
  anchorElapsed?: number;
  value?: number;
};
type Stop = { stopped: boolean; endedAt?: number };

function valid(value: number | undefined): number | undefined {
  return value !== undefined && Number.isFinite(value) && value >= 0 ? value : undefined;
}

function terminal(status: ConversationStatus | undefined): boolean {
  return status === undefined || status === "complete" || status === "error" || status === "cancelled";
}

function timingKey(kind: TimingKind, id: string, messageId: string): string {
  return JSON.stringify(kind === "message" ? [kind, id] : [kind, messageId, id]);
}

function elapsedAt(record: TimingRecord, now: number): number | undefined {
  return record.anchorElapsed === undefined ? undefined : Math.max(0, record.anchorElapsed + now - record.anchorAt);
}

function finalElapsed(input: Timing, record?: TimingRecord): number | undefined {
  const duration = valid(input.durationMs);
  if (duration !== undefined) return duration;
  const start = valid(input.startedAt) ?? record?.startedAt;
  const end = valid(input.endedAt);
  if (end !== undefined) return start !== undefined ? Math.max(0, end - start) : record ? elapsedAt(record, end) : undefined;
  return undefined;
}

/** One clock per flow; only subscribed time labels receive clock updates */
class ConversationTimingStore {
  private records = new Map<string, TimingRecord>();
  private listeners = new Map<string, Set<() => void>>();
  private registered = new Set<string>();
  private parents = new Map<string, Stop>();
  private fallback = new Map<string, { messageId: string; input: Timing }>();
  private timer: ReturnType<typeof setInterval> | undefined;
  private active = false;

  constructor(messages: readonly ConversationMessage[]) {
    this.reconcile(messages);
  }

  get(key: string): number | undefined { return this.records.get(key)?.value; }

  registerFallback(key: string, messageId: string, input: Timing): void {
    if (this.registered.has(key) || !this.parents.has(messageId)) return;
    this.fallback.set(key, { messageId, input });
    this.update(key, input, Date.now(), this.parents.get(messageId)!);
    this.schedule();
  }

  subscribe(key: string, listener: () => void): () => void {
    let listeners = this.listeners.get(key);
    if (!listeners) this.listeners.set(key, listeners = new Set());
    listeners.add(listener);
    this.refresh(key, Date.now());
    this.schedule();
    return () => {
      listeners.delete(listener);
      if (!listeners.size) this.listeners.delete(key);
      this.schedule();
    };
  }

  activate(): () => void {
    this.active = true;
    this.tick();
    this.schedule();
    return () => {
      this.active = false;
      this.schedule();
    };
  }

  reconcile(messages: readonly ConversationMessage[]): void {
    const now = Date.now();
    const seen = new Set<string>();
    this.parents.clear();
    const register = (key: string, input: Timing, parent: Stop = { stopped: false }) => {
      seen.add(key);
      this.update(key, input, now, parent);
    };
    for (const message of messages) {
      const messageKey = timingKey("message", message.id, message.id);
      if (message.role === "assistant") register(messageKey, message);
      const messageTiming = this.records.get(messageKey);
      const parent: Stop = message.role === "assistant" ? {
        stopped: terminal(message.status) || messageTiming?.endedAt !== undefined,
        endedAt: messageTiming?.endedAt,
      } : { stopped: false };
      this.parents.set(message.id, parent);
      const blocks = message.blocks ?? (message.role === "assistant" ? message.steps : undefined) ?? [];
      for (const block of blocks) {
        if (block.type !== "reasoning" && block.type !== "tool" && block.type !== "handoff") continue;
        const blockKey = timingKey("step", block.id, message.id);
        register(blockKey, block, parent);
        if (block.type === "handoff") {
          const blockTiming = this.records.get(blockKey);
          const nestedParent = parent.stopped ? parent : {
            stopped: terminal(block.status) || blockTiming?.endedAt !== undefined,
            endedAt: blockTiming?.endedAt,
          };
          for (const step of block.steps ?? []) register(timingKey("step", step.id, message.id), step, nestedParent);
        }
      }
    }
    this.registered = new Set(seen);
    for (const [key, fallback] of this.fallback) {
      if (!this.parents.has(fallback.messageId)) {
        this.fallback.delete(key);
      } else if (!seen.has(key)) {
        register(key, fallback.input, this.parents.get(fallback.messageId));
      }
    }
    for (const key of this.records.keys()) {
      if (seen.has(key)) continue;
      this.records.delete(key);
      this.notify(key);
    }
    this.schedule();
  }

  private update(key: string, input: Timing, now: number, parent: Stop): void {
    const previous = this.records.get(key);
    const duration = valid(input.durationMs);
    const start = valid(input.startedAt);
    const end = valid(input.endedAt);
    const newStart = start !== undefined && valid(previous?.input.startedAt) !== undefined && start !== valid(previous?.input.startedAt);
    const retry = input.status === "running" && previous && (terminal(previous.input.status) || newStart);
    const endedAt = retry && end === valid(previous.input.endedAt) ? undefined
      : previous?.running && end === valid(previous.input.endedAt) ? previous.endedAt : end;
    const running = input.status === "running" && !parent.stopped && endedAt === undefined;
    let startedAt = previous?.startedAt;
    let elapsed = previous?.value;

    if (running) {
      if (!previous?.running || newStart) {
        // A terminal -> running transition with the same id is a new attempt
        const reset = previous && (retry || previous.input.status === "running");
        startedAt = reset && start === valid(previous.input.startedAt) ? undefined : start;
        const baseline = reset && duration === valid(previous.input.durationMs) ? 0 : duration ?? 0;
        elapsed = Math.max(baseline, startedAt === undefined ? 0 : now - startedAt);
      } else {
        if (start !== valid(previous.input.startedAt)) startedAt = start;
        elapsed = Math.max(previous.value ?? 0, elapsedAt(previous, now) ?? 0);
        if (duration !== valid(previous.input.durationMs)) elapsed = Math.max(elapsed, duration ?? 0);
        if (startedAt !== undefined) elapsed = Math.max(elapsed, now - startedAt);
      }
    } else if (input.status === "pending") {
      startedAt = start;
      elapsed = duration;
    } else if (input.status === "running" && parent.stopped) {
      // The parent's terminal event stops unfinished children at the same instant
      if (!previous) elapsed = finalElapsed({ ...input, endedAt: parent.endedAt });
      else if (previous.running) elapsed = parent.endedAt === undefined
        ? Math.max(previous.value ?? 0, elapsedAt(previous, now) ?? 0)
        : elapsedAt(previous, parent.endedAt) ?? previous.value;
    } else {
      const changedDuration = duration !== valid(previous?.input.durationMs);
      const changedEnd = valid(input.endedAt) !== valid(previous?.input.endedAt);
      if (previous?.running || previous?.input.status === "running") {
        // A stop event may carry the last running snapshot rather than a final time
        elapsed = finalElapsed({
          durationMs: changedDuration ? duration : undefined,
          startedAt: previous.startedAt,
          endedAt: changedEnd ? input.endedAt : undefined,
        }, previous) ?? (previous.running ? Math.max(previous.value ?? 0, elapsedAt(previous, now) ?? 0) : previous.value);
      } else if (!previous || changedDuration || changedEnd || start !== valid(previous.input.startedAt)) {
        elapsed = finalElapsed(input, previous);
      }
      startedAt = start ?? startedAt;
    }

    const record: TimingRecord = {
      input: { status: input.status, durationMs: input.durationMs, startedAt: input.startedAt, endedAt: input.endedAt },
      running,
      startedAt,
      endedAt,
      anchorAt: running || !previous ? now : previous.anchorAt,
      anchorElapsed: running || !previous ? elapsed : previous.anchorElapsed,
      value: elapsed,
    };
    this.records.set(key, record);
    if (!Object.is(previous?.value, elapsed)) this.notify(key);
  }

  private notify(key: string): void { this.listeners.get(key)?.forEach(listener => listener()); }

  private refresh(key: string, now: number): void {
    const record = this.records.get(key);
    if (!record?.running) return;
    const value = Math.max(record.value ?? 0, elapsedAt(record, now) ?? 0);
    if (Object.is(value, record.value)) return;
    record.value = value;
    this.notify(key);
  }

  private tick = (): void => {
    const now = Date.now();
    for (const key of this.listeners.keys()) this.refresh(key, now);
  };

  private schedule(): void {
    const needed = this.active && Array.from(this.listeners.keys()).some(key => this.records.get(key)?.running);
    if (needed && this.timer === undefined) this.timer = setInterval(this.tick, 100);
    else if (!needed && this.timer !== undefined) {
      clearInterval(this.timer);
      this.timer = undefined;
    }
  }
}

const TimingContext = createContext<ConversationTimingStore | null>(null);
const MessageTimingContext = createContext("");

export function ConversationTimingProvider({ messages, children }: { messages: readonly ConversationMessage[]; children: ReactNode }) {
  const [store] = useState(() => new ConversationTimingStore(messages));
  useLayoutEffect(() => { store.reconcile(messages); });
  useLayoutEffect(() => store.activate(), [store]);
  return <TimingContext.Provider value={store}>{children}</TimingContext.Provider>;
}

export function ConversationMessageTimingScope({ messageId, children }: { messageId: string; children: ReactNode }) {
  return <MessageTimingContext.Provider value={messageId}>{children}</MessageTimingContext.Provider>;
}

export function useConversationElapsedTime(kind: TimingKind, id: string, timing: Timing): number | undefined {
  const store = useContext(TimingContext);
  const messageId = useContext(MessageTimingContext);
  const key = timingKey(kind, id, messageId);
  useLayoutEffect(() => {
    if (kind === "step") store?.registerFallback(key, messageId, timing);
  }, [store, kind, key, messageId, timing.status, timing.durationMs, timing.startedAt, timing.endedAt]);
  const fallback = finalElapsed(timing) ?? (timing.status === "running" ? 0 : undefined);
  const subscribe = useCallback((listener: () => void) => store?.subscribe(key, listener) ?? (() => {}), [store, key]);
  const snapshot = useCallback(() => store ? store.get(key) : fallback, [store, key, fallback]);
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}
