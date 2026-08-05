import type { Turn } from "../blocks";
import type { TraceSpan } from "./client";

export type IssueFeedbackIssue =
  | "slow"
  | "crash"
  | "incorrect"
  | "tool_error"
  | "page_slow"
  | "feature_unavailable"
  | "display_error"
  | "no_response"
  | "other";

export type IssueFeedbackSource = "agent_exec" | "platform";
export type IssueFeedbackModule =
  | "conversation"
  | "agents"
  | "applications"
  | "search"
  | "other";

export interface IssueFeedbackToolCall {
  name: string;
  args?: unknown;
  response?: unknown;
  done: boolean;
}

export interface IssueFeedbackReport {
  source: IssueFeedbackSource;
  module: IssueFeedbackModule;
  issues: IssueFeedbackIssue[];
  problem: string;
  description: string;
  page: string;
  appName: string;
  runtimeId: string;
  region: string;
  sessionId: string;
  eventId: string;
  invocationId: string;
  input: string;
  output: string;
  toolCalls: IssueFeedbackToolCall[];
  trace: TraceSpan[];
}

export function issueFeedbackToolCalls(turn: Turn): IssueFeedbackToolCall[] {
  return turn.blocks.flatMap((block) =>
    block.kind === "tool"
      ? [{
          name: block.name,
          args: block.args,
          response: block.response,
          done: block.done,
        }]
      : [],
  );
}

function spanInvocationId(span: TraceSpan): string {
  const attributes = span.attributes;
  return String(
    attributes["invocation.id"] ??
    attributes["gen_ai.invocation.id"] ??
    attributes["gcp.vertex.agent.invocation_id"] ??
    "",
  );
}

export function traceForInvocation(
  spans: TraceSpan[],
  invocationId: string,
): TraceSpan[] {
  if (!invocationId) return spans;
  const matchingTraceIds = new Set(
    spans
      .filter((span) => spanInvocationId(span) === invocationId)
      .map((span) => span.trace_id),
  );
  const matchingSpans = spans.filter((span) =>
    matchingTraceIds.has(span.trace_id),
  );
  return matchingSpans.length > 0 ? matchingSpans : spans;
}
