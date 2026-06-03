// Normalises ADK events into ordered display "blocks": thinking, text, tool
// calls, and A2UI surfaces.
//
// Streaming protocol (observed): incremental token events arrive with
// `partial: true` (one delta each); each content segment is then terminated by
// a single `partial: false` *consolidated* event carrying the full content.
// So we use partials only for a live preview, and when the consolidated event
// arrives we discard that preview and append the authoritative content. Stored
// history is all consolidated (partial falsey), which this same logic handles.

import type { AdkEvent, AdkPart } from "./adk/client";
import type { A2uiMessage } from "./a2ui/types";

const A2UI_TOOL = "send_a2ui_json_to_client";
const VALIDATED_JSON_KEY = "validated_a2ui_json";

export interface AttachmentView {
  mimeType?: string;
  data?: string; // base64 (no data: prefix)
  name?: string;
}

export type Block =
  | { kind: "thinking"; text: string; done: boolean }
  | { kind: "text"; text: string }
  | { kind: "tool"; name: string; args?: unknown; response?: unknown; done: boolean }
  | { kind: "a2ui"; messages: A2uiMessage[] }
  | { kind: "attachment"; files: AttachmentView[] };

/** Accumulator for one assistant turn. `liveStart` marks where the current
 *  streaming-preview blocks begin (everything before it is finalized). */
export interface Acc {
  blocks: Block[];
  liveStart: number;
}

export interface TurnMeta {
  tokens?: number;
  ts?: number; // epoch seconds
}

export interface Turn {
  role: "user" | "assistant";
  blocks: Block[];
  meta?: TurnMeta;
}

export function emptyAcc(): Acc {
  return { blocks: [], liveStart: 0 };
}

const fnCall = (p: AdkPart) => p.functionCall ?? p.function_call;
const fnResp = (p: AdkPart) => p.functionResponse ?? p.function_response;

/** Pull file attachments (inline_data) out of a message's parts. */
export function attachmentsFromParts(parts: AdkPart[]): AttachmentView[] {
  const files: AttachmentView[] = [];
  for (const p of parts) {
    const d = p.inlineData ?? p.inline_data;
    if (d && d.data) {
      files.push({
        mimeType: d.mimeType ?? d.mime_type,
        data: d.data,
        name: d.displayName ?? d.display_name,
      });
    }
  }
  return files;
}

function appendText(blocks: Block[], kind: "thinking" | "text", text: string) {
  const last = blocks[blocks.length - 1];
  if (last && last.kind === kind) last.text += text;
  else blocks.push(kind === "thinking" ? { kind, text, done: false } : { kind, text });
}

function closeThinking(blocks: Block[]) {
  for (const b of blocks) if (b.kind === "thinking") b.done = true;
}

/** Apply one ADK event to a turn accumulator, returning a new accumulator. */
export function applyEvent(acc: Acc, ev: AdkEvent): Acc {
  const blocks = acc.blocks.map((b) => ({ ...b }));
  let liveStart = acc.liveStart;
  const parts = ev.content?.parts ?? [];
  const hasFn = parts.some((p) => fnCall(p) || fnResp(p));

  if (ev.partial && !hasFn) {
    // Streaming delta: append into the live-preview region.
    for (const p of parts) {
      if (typeof p.text === "string" && p.text)
        appendText(blocks, p.thought ? "thinking" : "text", p.text);
    }
    return { blocks, liveStart };
  }

  // Consolidated / final event: drop the live preview and append authoritative
  // content (merging consecutive same-kind text parts into one block).
  blocks.length = liveStart;
  for (const p of parts) {
    const fc = fnCall(p);
    const fr = fnResp(p);
    if (typeof p.text === "string" && p.text) {
      appendText(blocks, p.thought ? "thinking" : "text", p.text);
    } else if (fc) {
      closeThinking(blocks);
      blocks.push({ kind: "tool", name: fc.name ?? "", args: fc.args, done: false });
    } else if (fr) {
      closeThinking(blocks);
      for (let i = blocks.length - 1; i >= 0; i--) {
        const b = blocks[i];
        if (b.kind === "tool" && !b.done && b.name === fr.name) {
          b.done = true;
          b.response = fr.response;
          break;
        }
      }
      if (fr.name === A2UI_TOOL) {
        const msgs = (fr.response?.[VALIDATED_JSON_KEY] as A2uiMessage[]) ?? [];
        if (msgs.length) {
          const last = blocks[blocks.length - 1];
          if (last && last.kind === "a2ui") last.messages.push(...msgs);
          else blocks.push({ kind: "a2ui", messages: msgs });
        }
      }
    }
  }
  closeThinking(blocks); // a consolidated thinking segment is complete
  liveStart = blocks.length;
  return { blocks, liveStart };
}

/** Replay stored session events into chat turns (for history). */
export function eventsToTurns(events: AdkEvent[]): Turn[] {
  const turns: Turn[] = [];
  let acc = emptyAcc();
  for (const ev of events) {
    // Classify by author only: function-response events are authored by the
    // agent but carry content.role === "user", so a role-based check would
    // mis-split the assistant turn and drop tool results.
    const isUser = ev.author === "user";
    if (isUser) {
      const parts = ev.content?.parts ?? [];
      const text = parts
        .map((p) => p.text)
        .filter((t): t is string => !!t)
        .join("");
      const files = attachmentsFromParts(parts);
      const blocks: Block[] = [];
      if (files.length) blocks.push({ kind: "attachment", files });
      if (text) blocks.push({ kind: "text", text });
      turns.push({ role: "user", blocks, meta: { ts: ev.timestamp } });
      acc = emptyAcc();
    } else {
      let last = turns[turns.length - 1];
      if (!last || last.role !== "assistant") {
        last = { role: "assistant", blocks: [], meta: {} };
        turns.push(last);
        acc = emptyAcc();
      }
      acc = applyEvent(acc, ev);
      last.blocks = acc.blocks;
      const usage = ev.usageMetadata ?? ev.usage_metadata;
      const meta = (last.meta ??= {});
      if (usage?.totalTokenCount) meta.tokens = usage.totalTokenCount;
      if (ev.timestamp) meta.ts = ev.timestamp;
    }
  }
  return turns;
}

/** First user message of a session, for the sidebar title. */
export function sessionTitle(events: AdkEvent[] | undefined): string {
  for (const ev of events ?? []) {
    if (ev.author === "user" || ev.content?.role === "user") {
      const t = (ev.content?.parts ?? []).map((p) => p.text).find(Boolean);
      if (t) return t;
    }
  }
  return "新会话";
}
