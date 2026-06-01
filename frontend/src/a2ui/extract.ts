// Extract A2UI messages from an ADK event.
//
// On the ADK API server path, A2UI arrives as the function response of the
// `send_a2ui_json_to_client` tool: response = { validated_a2ui_json: [...] }.

import type { AdkEvent, AdkPart } from "../adk/client";
import type { A2uiMessage } from "./types";

// Literals defined by the a2ui SDK (send_a2ui_to_client_toolset.py).
const A2UI_TOOL_NAME = "send_a2ui_json_to_client";
const VALIDATED_JSON_KEY = "validated_a2ui_json";

function functionResponse(part: AdkPart) {
  return part.functionResponse ?? part.function_response;
}

/** Pull any A2UI messages out of an ADK event (may be empty). */
export function extractA2uiMessages(event: AdkEvent): A2uiMessage[] {
  const parts = event.content?.parts ?? [];
  const messages: A2uiMessage[] = [];
  for (const part of parts) {
    const fr = functionResponse(part);
    if (!fr || fr.name !== A2UI_TOOL_NAME) continue;
    const payload = fr.response?.[VALIDATED_JSON_KEY];
    if (Array.isArray(payload)) {
      messages.push(...(payload as A2uiMessage[]));
    }
  }
  return messages;
}

/** Concatenate plain-text parts of an event (for the chat transcript). */
export function extractText(event: AdkEvent): string {
  const parts = event.content?.parts ?? [];
  return parts
    .map((p) => p.text)
    .filter((t): t is string => typeof t === "string" && t.length > 0)
    .join("");
}
