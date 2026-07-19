// Normalises ADK events into ordered display "blocks": thinking, text, tool
// calls, and A2UI surfaces.
//
// Streaming protocol (observed): incremental token events arrive with
// `partial: true` (one delta each); each content segment is then terminated by
// a single `partial: false` *consolidated* event carrying the full content.
// So we use partials only for a live preview, and when the consolidated event
// arrives we discard that preview and append the authoritative content. Stored
// history is all consolidated (partial falsey), which this same logic handles.

import type {
  AdkEvent,
  AdkPart,
  AgentNodeType,
  AgentSkill,
  AgentTarget,
  FrontendInvocation,
} from "./adk/client";
import type { A2uiMessage } from "./a2ui/types";

const A2UI_TOOL = "send_a2ui_json_to_client";
const VALIDATED_JSON_KEY = "validated_a2ui_json";
/** ADK's special function call that requests OAuth/credentials for a tool. */
const REQUEST_EUC = "adk_request_credential";

/** Pull the OAuth2 authorize URL out of an ADK AuthConfig (camelCase over
 *  /run_sse, snake_case in stored history — handle both). */
export function authUriOf(authConfig: unknown): string | undefined {
  const c = authConfig as Record<string, any> | undefined;
  const o =
    c?.exchangedAuthCredential?.oauth2 ??
    c?.exchanged_auth_credential?.oauth2 ??
    c?.rawAuthCredential?.oauth2 ??
    c?.raw_auth_credential?.oauth2;
  return o?.authUri ?? o?.auth_uri;
}

export interface AttachmentView {
  id: string;
  mimeType?: string;
  data?: string; // base64 (no data: prefix)
  uri?: string;
  name?: string;
  sizeBytes?: number;
}

export type Block =
  | { kind: "thinking"; text: string; done: boolean }
  | { kind: "text"; text: string }
  | { kind: "tool"; name: string; args?: unknown; response?: unknown; done: boolean }
  | { kind: "a2ui"; messages: A2uiMessage[] }
  | { kind: "attachment"; files: AttachmentView[] }
  | { kind: "invocation"; value: FrontendInvocation }
  | {
      kind: "auth";
      callId: string;
      /** The toolset requesting auth (e.g. "McpToolset"), from functionCallId. */
      label?: string;
      authUri?: string;
      authConfig: unknown;
      done: boolean;
    };

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

/** ADK/genai serialises inline_data bytes as URL-safe base64 (-_), but a
 *  `data:` URI requires standard base64 (+/). Convert so reloaded images
 *  render instead of failing to a broken <img>. */
function toStdBase64(b64: string): string {
  return b64.replace(/-/g, "+").replace(/_/g, "/");
}

/** Pull file attachments (inline_data) out of a message's parts. */
export function attachmentsFromParts(parts: AdkPart[]): AttachmentView[] {
  const files: AttachmentView[] = [];
  for (const [index, p] of parts.entries()) {
    const metadata = (p.partMetadata ?? p.part_metadata) as
      | Record<string, unknown>
      | undefined;
    const transport = metadata?.veadkTransport as Record<string, unknown> | undefined;
    if (transport?.hidden === true) continue;
    const stored = metadata?.veadkMedia as Record<string, unknown> | undefined;
    if (typeof stored?.uri === "string") {
      files.push({
        id: String(stored.id ?? stored.uri),
        mimeType: typeof stored.mimeType === "string" ? stored.mimeType : undefined,
        uri: stored.uri,
        name: typeof stored.name === "string" ? stored.name : undefined,
        sizeBytes: typeof stored.sizeBytes === "number" ? stored.sizeBytes : undefined,
      });
      continue;
    }
    const d = p.inlineData ?? p.inline_data;
    if (d && d.data) {
      files.push({
        id: `inline-${index}-${d.displayName ?? d.display_name ?? "media"}`,
        mimeType: d.mimeType ?? d.mime_type,
        data: toStdBase64(d.data),
        name: d.displayName ?? d.display_name,
      });
      continue;
    }
    const f = p.fileData ?? p.file_data;
    const uri = f?.fileUri ?? f?.file_uri;
    if (f && uri) {
      files.push({
        id: uri,
        mimeType: f.mimeType ?? f.mime_type,
        uri,
        name: f.displayName ?? f.display_name,
      });
    }
  }
  return files;
}

function visiblePartText(part: AdkPart): string | undefined {
  const metadata = (part.partMetadata ?? part.part_metadata) as
    | Record<string, unknown>
    | undefined;
  const transport = metadata?.veadkTransport as Record<string, unknown> | undefined;
  return transport?.hideText === true ? undefined : part.text;
}

const AGENT_NODE_TYPES = new Set<AgentNodeType>([
  "llm",
  "sequential",
  "parallel",
  "loop",
  "a2a",
]);

/** Restore slash-skill and @agent selections persisted in part metadata. */
export function invocationFromParts(parts: AdkPart[]): FrontendInvocation | undefined {
  for (const part of parts) {
    const raw = (part.partMetadata ?? part.part_metadata)?.veadkInvocation;
    if (!raw || typeof raw !== "object") continue;
    const metadata = raw as Record<string, unknown>;
    const skills = Array.isArray(metadata.skills)
      ? metadata.skills.flatMap<AgentSkill>((item) => {
          if (!item || typeof item !== "object") return [];
          const skill = item as Record<string, unknown>;
          return typeof skill.name === "string"
            ? [{
                name: skill.name,
                description: typeof skill.description === "string" ? skill.description : "",
              }]
            : [];
        })
      : [];

    let targetAgent: AgentTarget | undefined;
    const rawTarget = metadata.targetAgent;
    if (rawTarget && typeof rawTarget === "object") {
      const target = rawTarget as Record<string, unknown>;
      const type = target.type;
      if (
        typeof target.name === "string" &&
        typeof type === "string" &&
        AGENT_NODE_TYPES.has(type as AgentNodeType) &&
        Array.isArray(target.path)
      ) {
        targetAgent = {
          name: target.name,
          description: typeof target.description === "string" ? target.description : "",
          type: type as AgentNodeType,
          path: target.path.filter((item): item is string => typeof item === "string"),
        };
      }
    }
    if (skills.length > 0 || targetAgent) return { skills, targetAgent };
  }
  return undefined;
}

function appendAttachments(blocks: Block[], files: AttachmentView[]) {
  if (!files.length) return;
  const last = blocks[blocks.length - 1];
  if (last?.kind === "attachment") last.files.push(...files);
  else blocks.push({ kind: "attachment", files });
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
      const text = visiblePartText(p);
      if (typeof text === "string" && text)
        appendText(blocks, p.thought ? "thinking" : "text", text);
    }
    return { blocks, liveStart };
  }

  // Consolidated / final event: drop the live preview and append authoritative
  // content (merging consecutive same-kind text parts into one block).
  blocks.length = liveStart;
  for (const p of parts) {
    const fc = fnCall(p);
    const fr = fnResp(p);
    const files = attachmentsFromParts([p]);
    const text = visiblePartText(p);
    if (typeof text === "string" && text) {
      appendText(blocks, p.thought ? "thinking" : "text", text);
    } else if (files.length) {
      closeThinking(blocks);
      appendAttachments(blocks, files);
    } else if (fc) {
      closeThinking(blocks);
      if (fc.name === REQUEST_EUC) {
        // MCP/tool OAuth: render a dedicated auth card instead of a tool row.
        const args = (fc.args ?? {}) as Record<string, any>;
        const authConfig = args.authConfig ?? args.auth_config ?? args;
        // functionCallId looks like "_adk_toolset_auth_McpToolset"; surface the
        // toolset name so the card can say what is being authorized.
        const rawId = String(args.functionCallId ?? args.function_call_id ?? "");
        const label = rawId.replace(/^_adk_toolset_auth_/, "") || undefined;
        blocks.push({
          kind: "auth",
          callId: fc.id ?? "",
          label,
          authUri: authUriOf(authConfig),
          authConfig,
          done: false,
        });
      } else {
        blocks.push({ kind: "tool", name: fc.name ?? "", args: fc.args, done: false });
      }
    } else if (fr) {
      closeThinking(blocks);
      // A credential response resolves the matching auth card.
      if (fr.name === REQUEST_EUC) {
        for (let i = blocks.length - 1; i >= 0; i--) {
          const b = blocks[i];
          if (b.kind === "auth" && !b.done) {
            b.done = true;
            break;
          }
        }
      }
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
      // A credential (adk_request_credential) response is an internal resume,
      // not a user message — resolve the prior assistant turn's auth card.
      if (parts.some((p) => fnResp(p)?.name === REQUEST_EUC)) {
        for (let i = turns.length - 1; i >= 0; i--) {
          if (turns[i].role !== "assistant") continue;
          for (let j = turns[i].blocks.length - 1; j >= 0; j--) {
            const b = turns[i].blocks[j];
            if (b.kind === "auth") { b.done = true; break; }
          }
          break;
        }
      }
      const text = parts
        .map(visiblePartText)
        .filter((t): t is string => !!t)
        .join("");
      const files = attachmentsFromParts(parts);
      const invocation = invocationFromParts(parts);
      // Skip pure function-response turns (no text/files) — they're internal.
      if (!text && !files.length && !invocation) {
        acc = emptyAcc();
        continue;
      }
      const blocks: Block[] = [];
      if (invocation) blocks.push({ kind: "invocation", value: invocation });
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
