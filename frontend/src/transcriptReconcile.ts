import type { Turn } from "./blocks";

function latestAssistantTurn(turns: Turn[]): Turn | undefined {
  for (let index = turns.length - 1; index >= 0; index -= 1) {
    if (turns[index].role === "assistant") return turns[index];
  }
  return undefined;
}

/**
 * Replace the live transcript only when persistence has caught up with the
 * exact reply that triggered the refresh and no newer local reply has started.
 */
export function reconcilePersistedTranscript(
  current: Turn[],
  persisted: Turn[],
  expectedEventId: string,
): Turn[] {
  if (!expectedEventId) return current;
  const persistedHasExpectedReply = persisted.some(
    (turn) =>
      turn.role === "assistant" && turn.meta?.eventId === expectedEventId,
  );
  if (!persistedHasExpectedReply) return current;

  const latestLocalReply = latestAssistantTurn(current);
  if (latestLocalReply?.meta?.eventId !== expectedEventId) return current;
  return persisted;
}
