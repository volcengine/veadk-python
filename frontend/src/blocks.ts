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
  MessageFeedbackState,
} from "./adk/client";
import { i18n } from "./i18n/runtime";
import type { A2uiMessage } from "./a2ui/types";
import type { SandboxTokenUsage } from "./adk/sandbox";
import type { ProjectFile } from "./create/project";
import {
  applyBranchCompareProgress,
  parseBranchCompareProgress,
} from "./ui/builtin-tools/branchCompareData";
import {
  applyCodexSandboxProgress,
  hydrateCodexSandboxActivity,
  parseCodexSandboxProgress,
} from "./ui/builtin-tools/codexSandboxProgress";
import type { CodexSandboxProgress } from "./ui/builtin-tools/codexSandboxProgress";

const A2UI_TOOL = "send_a2ui_json_to_client";
const VALIDATED_JSON_KEY = "validated_a2ui_json";
/** ADK's special function call that requests OAuth/credentials for a tool. */
const REQUEST_EUC = "adk_request_credential";
const TRANSFER_AGENT_TOOL = "transfer_to_agent";

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
  previewUrl?: string;
}

export interface IntelligentDevelopmentReleaseRef {
  sessionId: string;
  projectId?: string;
  versionId?: string;
  parentVersionId?: string | null;
  artifactSha256: string;
  validationReportSha256: string;
  agentName: string;
  entryPoint: string;
  fileCount: number;
  artifactSize: number;
  validatedAt: string;
  gateSummary: string[];
  deployable: boolean;
  verified: boolean;
  validationSummary: string;
  environment?: {
    required: string[];
    optional: string[];
    defaults: Record<string, string>;
  };
  files?: ProjectFile[];
}

export interface CodexSandboxActivity {
  title: string;
  agentSessionId?: string;
  sandboxSessionId?: string;
  threadId?: string;
  items: Array<{ id: string; block: Block }>;
}

export type Block =
  | { kind: "progress"; text: string }
  | { kind: "thinking"; text: string; done: boolean }
  | { kind: "text"; text: string }
  | {
      kind: "tool";
      name: string;
      callId?: string;
      args?: unknown;
      response?: unknown;
      done: boolean;
      status?: "running" | "completed" | "failed";
      defaultOpen?: boolean;
      codexActivity?: CodexSandboxActivity;
    }
  | {
      kind: "plan";
      title: string;
      summary?: string;
      items: Array<{
        text: string;
        status: "pending" | "in_progress" | "completed" | "failed";
      }>;
      done: boolean;
    }
  | { kind: "agent-transfer"; agentName: string; done: boolean }
  | { kind: "a2ui"; messages: A2uiMessage[] }
  | { kind: "attachment"; files: AttachmentView[] }
  | {
      kind: "artifact";
      files: { filename: string; version: number }[];
    }
  | {
      kind: "delivery";
      value: IntelligentDevelopmentReleaseRef;
    }
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
  pendingCodexProgress: CodexSandboxProgress[];
}

export interface TurnMeta {
  author?: string;
  localId?: string;
  streaming?: boolean;
  tokens?: number;
  ts?: number; // epoch seconds
  eventId?: string;
  invocationId?: string;
  feedback?: MessageFeedbackState;
  sandboxUsage?: SandboxTokenUsage;
}

export interface TurnActivityDetail {
  label: string;
  value: string;
  code?: boolean;
}

export interface TurnActivity {
  id: string;
  title: string;
  details?: TurnActivityDetail[];
}

export interface Turn {
  role: "user" | "assistant" | "system";
  blocks: Block[];
  meta?: TurnMeta;
  activity?: TurnActivity;
}

export function emptyAcc(): Acc {
  return { blocks: [], liveStart: 0, pendingCodexProgress: [] };
}

const MAX_PENDING_CODEX_PROGRESS = 64;

function applyCodexProgressToTool(
  blocks: Block[],
  progress: CodexSandboxProgress,
): "applied" | "completed" | "unmatched" {
  // The successful function response owns the final assistant message. Older
  // servers may also stream it as Codex progress; do not duplicate it inside
  // the nested execution card.
  if (progress.event.finalAnswer) return "applied";
  let fallbackIndex = -1;
  for (let index = blocks.length - 1; index >= 0; index -= 1) {
    const block = blocks[index];
    if (block.kind !== "tool" || block.name !== progress.toolName) continue;
    if (block.callId === progress.requestId) {
      if (block.done) return "completed";
      block.codexActivity = applyCodexSandboxProgress(block.codexActivity, progress);
      block.status = progress.terminalStatus ?? "running";
      if (progress.terminalStatus) block.done = true;
      return "applied";
    }
    if (!block.done) {
      if (fallbackIndex >= 0) return "unmatched";
      fallbackIndex = index;
    }
  }
  // Older Studio-channel runtimes reported their transport request id instead
  // of the outer ADK function-call id. Bind only when the unfinished tool is
  // unambiguous; exact ids above always win when calls overlap.
  if (fallbackIndex >= 0) {
    const block = blocks[fallbackIndex];
    if (block.kind !== "tool") return "unmatched";
    block.codexActivity = applyCodexSandboxProgress(block.codexActivity, progress);
    block.status = progress.terminalStatus ?? "running";
    if (progress.terminalStatus) block.done = true;
    return "applied";
  }
  return "unmatched";
}

function codexResponseStatus(response: unknown): "completed" | "failed" {
  if (!response || typeof response !== "object" || Array.isArray(response)) {
    return "completed";
  }
  const result = response as Record<string, unknown>;
  const status = typeof result.status === "string" ? result.status.toLowerCase() : "";
  if (
    result.ok === false
    || ["error", "failed", "denied", "declined", "cancelled", "timeout"].includes(status)
  ) {
    return "failed";
  }
  return "completed";
}

function codexDirectAnswer(response: unknown): string {
  if (!response || typeof response !== "object" || Array.isArray(response)) return "";
  const result = response as Record<string, unknown>;
  if (result.ok !== true || typeof result.message !== "string") return "";
  return result.message.trim();
}

interface ActiveAssistantTurn {
  acc: Acc;
  localId: string;
  meta: TurnMeta;
}

export interface AssistantEventProjection {
  turn: Turn;
  completed: boolean;
  ignored?: boolean;
}

const fnCall = (p: AdkPart) => p.functionCall ?? p.function_call;
const fnResp = (p: AdkPart) => p.functionResponse ?? p.function_response;

function transferAgentName(args: unknown): string {
  if (!args || typeof args !== "object") return "";
  const record = args as Record<string, unknown>;
  const name = record.agentName ?? record.agent_name;
  return typeof name === "string" ? name : "";
}

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

function appendArtifacts(blocks: Block[], files: { filename: string; version: number }[]) {
  if (!files.length) return;
  const last = blocks[blocks.length - 1];
  if (last?.kind === "artifact") {
    for (const file of files) {
      if (!last.files.some((item) =>
        item.filename === file.filename && item.version === file.version
      )) last.files.push(file);
    }
    return;
  }
  blocks.push({ kind: "artifact", files });
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
  let pendingCodexProgress = acc.pendingCodexProgress.slice();
  const parts = ev.content?.parts ?? [];
  const progressUpdates = parts.flatMap((part) => {
    const progress = parseBranchCompareProgress(
      part.partMetadata ?? part.part_metadata,
    );
    return progress ? [progress] : [];
  });
  const codexProgressUpdates = parts.flatMap((part) => {
    const progress = parseCodexSandboxProgress(
      part.partMetadata ?? part.part_metadata,
    );
    return progress ? [progress] : [];
  });
  if (progressUpdates.length > 0 || codexProgressUpdates.length > 0) {
    for (const progress of progressUpdates) {
      for (let index = blocks.length - 1; index >= 0; index -= 1) {
        const block = blocks[index];
        if (
          block.kind !== "tool"
          || block.done
          || block.name !== progress.toolName
          || (progress.requestId && block.callId && block.callId !== progress.requestId)
        ) {
          continue;
        }
        block.response = applyBranchCompareProgress(block.args, block.response, progress);
        block.status = "running";
        break;
      }
    }
    for (const progress of codexProgressUpdates) {
      const outcome = applyCodexProgressToTool(blocks, progress);
      if (outcome === "unmatched") {
        pendingCodexProgress = [...pendingCodexProgress, progress]
          .slice(-MAX_PENDING_CODEX_PROGRESS);
      }
    }
    return { blocks, liveStart, pendingCodexProgress };
  }
  const hasFn = parts.some((p) => fnCall(p) || fnResp(p));

  if (ev.partial && !hasFn) {
    // Streaming delta: append into the live-preview region.
    for (const p of parts) {
      const text = visiblePartText(p);
      if (typeof text === "string" && text)
        appendText(blocks, p.thought ? "thinking" : "text", text);
    }
    return { blocks, liveStart, pendingCodexProgress };
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
      if (fc.name === TRANSFER_AGENT_TOOL) {
        const agentName =
          transferAgentName(fc.args) ||
          ev.actions?.transferToAgent ||
          ev.actions?.transfer_to_agent ||
          i18n.t("app:common.unknownAgent");
        blocks.push({ kind: "agent-transfer", agentName, done: false });
      } else if (fc.name === REQUEST_EUC) {
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
        const toolBlock: Extract<Block, { kind: "tool" }> = {
          kind: "tool",
          name: fc.name ?? "",
          callId: fc.id,
          args: fc.args,
          done: false,
        };
        blocks.push(toolBlock);
        if (toolBlock.callId) {
          const stillPending: CodexSandboxProgress[] = [];
          for (const progress of pendingCodexProgress) {
            if (
              progress.toolName === toolBlock.name
              && progress.requestId === toolBlock.callId
            ) {
              applyCodexProgressToTool(blocks, progress);
            } else {
              stillPending.push(progress);
            }
          }
          pendingCodexProgress = stillPending;
        }
      }
    } else if (fr) {
      closeThinking(blocks);
      if (fr.name === TRANSFER_AGENT_TOOL) {
        for (let i = blocks.length - 1; i >= 0; i--) {
          const b = blocks[i];
          if (b.kind === "agent-transfer" && !b.done) {
            b.done = true;
            break;
          }
        }
      }
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
        const isCodexTool = b.kind === "tool" && b.name === "delegate_to_codex_sandbox";
        if (
          b.kind === "tool"
          && (!b.done || isCodexTool)
          && b.name === fr.name
          && (!fr.id || !b.callId || b.callId === fr.id)
        ) {
          const previousAnswer = isCodexTool
            ? codexDirectAnswer(b.response)
            : "";
          b.done = true;
          b.response = fr.response;
          if (isCodexTool) {
            b.codexActivity = hydrateCodexSandboxActivity(
              b.codexActivity,
              fr.response,
            );
            b.status = codexResponseStatus(fr.response);
            const answer = codexDirectAnswer(fr.response);
            if (answer && answer !== previousAnswer) {
              appendText(blocks, "text", answer);
            }
          }
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
  const artifactDelta = ev.actions?.artifactDelta ?? ev.actions?.artifact_delta;
  if (artifactDelta) {
    appendArtifacts(
      blocks,
      Object.entries(artifactDelta).map(([filename, version]) => ({ filename, version })),
    );
  }
  closeThinking(blocks); // a consolidated thinking segment is complete
  liveStart = blocks.length;
  return { blocks, liveStart, pendingCodexProgress };
}

function completesAssistantResponse(ev: AdkEvent, blocks: Block[]): boolean {
  if (ev.partial === true) return false;
  const parts = ev.content?.parts ?? [];
  const hasFinalAnswerPart = parts.some((part) => {
    const text = visiblePartText(part);
    return (
      (!part.thought && typeof text === "string" && text.trim().length > 0) ||
      attachmentsFromParts([part]).length > 0
    );
  });
  const hasA2ui = parts.some((part) => {
    const response = fnResp(part);
    return response?.name === A2UI_TOOL &&
      Array.isArray(response.response?.[VALIDATED_JSON_KEY]) &&
      response.response[VALIDATED_JSON_KEY].length > 0;
  });
  const artifactDelta = ev.actions?.artifactDelta ?? ev.actions?.artifact_delta;
  const hasArtifact = Boolean(artifactDelta && Object.keys(artifactDelta).length > 0);
  const agentEnded = Boolean(
    ev.actions?.endOfAgent ?? ev.actions?.end_of_agent ?? ev.actions?.escalate
  );
  const hasAnswerBlock = blocks.some((block) =>
    block.kind === "text" ||
    block.kind === "attachment" ||
    block.kind === "artifact" ||
    block.kind === "a2ui" ||
    block.kind === "delivery"
  );
  return hasFinalAnswerPart || hasA2ui || hasArtifact || (agentEnded && hasAnswerBlock);
}

function eventAffectsAssistantTurn(ev: AdkEvent): boolean {
  const artifactDelta = ev.actions?.artifactDelta ?? ev.actions?.artifact_delta;
  if (artifactDelta && Object.keys(artifactDelta).length > 0) return true;
  return (ev.content?.parts ?? []).some((part) =>
    Boolean(
      visiblePartText(part) ||
      attachmentsFromParts([part]).length > 0 ||
      fnCall(part) ||
      fnResp(part)
    )
  );
}

/** Keep one mutable stream accumulator per active Agent response. Parallel
 *  Agents can interleave token events, so a single "current author" loses
 *  content and creates one turn per author switch. A completed response closes
 *  only that author's accumulator, allowing Loop Agents to start a later turn
 *  with the same author. */
export function createAssistantEventProjector(
  localIdPrefix = "adk-stream",
  initialTurn?: Turn,
) {
  let sequence = 0;
  const active = new Map<string, ActiveAssistantTurn>();
  let seededKey: string | undefined;

  const keyFor = (author: string, invocationId: string) =>
    `${invocationId}\u0000${author}`;

  if (initialTurn?.role === "assistant") {
    const author = initialTurn.meta?.author ?? "";
    const invocationId = initialTurn.meta?.invocationId ?? "";
    const localId = initialTurn.meta?.localId ?? `${localIdPrefix}-${sequence++}`;
    const acc = emptyAcc();
    acc.blocks = initialTurn.blocks;
    acc.liveStart = initialTurn.blocks.length;
    seededKey = keyFor(author, invocationId);
    active.set(seededKey, {
      acc,
      localId,
      meta: {
        ...initialTurn.meta,
        localId,
        streaming: true,
        eventId: undefined,
      },
    });
  }

  return {
    project(ev: AdkEvent): AssistantEventProjection {
      const author = ev.author && ev.author !== "user" ? ev.author : "";
      const invocationId = ev.invocationId ?? ev.invocation_id ?? "";
      const key = keyFor(author, invocationId);
      let state = active.get(key);
      if (!state && seededKey) {
        const seeded = active.get(seededKey);
        if (seeded && (!seeded.meta.author || seeded.meta.author === author)) {
          active.delete(seededKey);
          seededKey = undefined;
          state = seeded;
        }
      }
      if (!state && !eventAffectsAssistantTurn(ev)) {
        return {
          turn: { role: "assistant", blocks: [] },
          completed: false,
          ignored: true,
        };
      }
      if (!state) {
        const localId = `${localIdPrefix}-${sequence++}`;
        state = {
          acc: emptyAcc(),
          localId,
          meta: { author: author || undefined, invocationId: invocationId || undefined },
        };
      }

      state.acc = applyEvent(state.acc, ev);
      const usage = ev.usageMetadata ?? ev.usage_metadata;
      const completed = completesAssistantResponse(ev, state.acc.blocks);
      state.meta = {
        ...state.meta,
        author: author || state.meta.author,
        localId: state.localId,
        streaming: !completed,
        tokens: usage?.totalTokenCount || state.meta.tokens,
        ts: ev.timestamp || state.meta.ts,
        invocationId: invocationId || state.meta.invocationId,
        eventId: completed && ev.id ? ev.id : state.meta.eventId,
      };
      const turn: Turn = {
        role: "assistant",
        blocks: state.acc.blocks,
        meta: state.meta,
      };
      if (completed) {
        active.delete(key);
        seededKey = undefined;
      } else {
        active.set(key, state);
      }
      return { turn, completed };
    },

    finish(): Turn[] {
      const turns = [...active.values()].map((state): Turn => ({
        role: "assistant",
        blocks: state.acc.blocks,
        meta: { ...state.meta, streaming: false },
      }));
      active.clear();
      return turns;
    },
  };
}

export function upsertProjectedAssistantTurn(turns: Turn[], projected: Turn): Turn[] {
  const localId = projected.meta?.localId;
  if (!localId) return [...turns, projected];
  const index = turns.findIndex((turn) => turn.meta?.localId === localId);
  if (index < 0) return [...turns, projected];
  const next = turns.slice();
  next[index] = projected;
  return next;
}

/** Replay stored session events into chat turns (for history). */
export function eventsToTurns(
  events: AdkEvent[],
  sessionState: Record<string, unknown> = {},
): Turn[] {
  let turns: Turn[] = [];
  let projector = createAssistantEventProjector("adk-history");
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
        continue;
      }
      for (const unfinished of projector.finish()) {
        turns = upsertProjectedAssistantTurn(turns, unfinished);
      }
      const blocks: Block[] = [];
      if (invocation) blocks.push({ kind: "invocation", value: invocation });
      if (files.length) blocks.push({ kind: "attachment", files });
      if (text) blocks.push({ kind: "text", text });
      turns.push({ role: "user", blocks, meta: { ts: ev.timestamp } });
      projector = createAssistantEventProjector("adk-history");
    } else {
      const projection = projector.project(ev);
      if (!projection.ignored) {
        turns = upsertProjectedAssistantTurn(turns, projection.turn);
      }
    }
  }
  for (const unfinished of projector.finish()) {
    turns = upsertProjectedAssistantTurn(turns, unfinished);
  }
  for (const turn of turns) {
    const meta = turn.meta;
    const eventId = meta?.eventId;
    if (!eventId) continue;
    const feedback = sessionState[`veadk_feedback:${eventId}`];
    if (!feedback || typeof feedback !== "object") continue;
    const record = feedback as Record<string, unknown>;
    if (record.rating !== "good" && record.rating !== "bad") continue;
    meta.feedback = feedback as MessageFeedbackState;
  }
  return turns;
}

/** First user message of a session, for the sidebar title. */
export function sessionTitle(
  events: AdkEvent[] | undefined,
  fallback = i18n.t("app:titles.newConversation"),
): string {
  for (const ev of events ?? []) {
    if (ev.author === "user" || ev.content?.role === "user") {
      const t = (ev.content?.parts ?? []).map((p) => p.text).find(Boolean);
      if (t) return t;
    }
  }
  return fallback;
}
