// Minimal Server-Sent-Events parser for `fetch` response bodies.
//
// The ADK `/run_sse` endpoint emits `data: <json>\n\n` frames. This async
// generator yields each parsed JSON payload as it arrives. When an upstream
// names the SSE event, the parsed payload includes a non-enumerable
// `__sseEvent` property so callers that care about transport control frames
// can react without changing normal event shape assertions.

export const SSE_EVENT_NAME = "__sseEvent";

export async function* parseSSE(
  response: Response,
): AsyncGenerator<unknown, void, unknown> {
  if (!response.body) throw new Error("Response has no body");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const rawDataExcerpt = (data: string): string => {
    const limit = 500;
    return data.length > limit
      ? adkT("sse.truncatedData", { data: data.slice(0, limit), count: data.length })
      : data;
  };

  const parseFrame = (frame: string, final = false): unknown | undefined => {
    const lines = frame.split(/\r?\n/);
    const eventName = lines
      .find((line) => line.startsWith("event:"))
      ?.slice(6)
      .trim();
    const data = lines
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (!data || data === "[DONE]" || data === "ping") return undefined;
    try {
      const parsed = JSON.parse(data);
      if (eventName && parsed && typeof parsed === "object") {
        Object.defineProperty(parsed, SSE_EVENT_NAME, {
          value: eventName,
          enumerable: false,
          configurable: true,
        });
      }
      return parsed;
    } catch {
      const rawData = rawDataExcerpt(data);
      if (final) {
        throw new Error(
          adkT("sse.incompleteEvent", { data: rawData }),
        );
      }
      throw new Error(
        adkT("sse.invalidEventJson", { data: rawData }),
      );
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames use a blank line separator. Accept both LF and CRLF.
      let separator = buffer.match(/\r?\n\r?\n/);
      while (separator?.index !== undefined) {
        const frame = buffer.slice(0, separator.index);
        buffer = buffer.slice(separator.index + separator[0].length);
        const event = parseFrame(frame);
        if (event !== undefined) yield event;
        separator = buffer.match(/\r?\n\r?\n/);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) {
      const event = parseFrame(buffer, true);
      if (event !== undefined) yield event;
    }
  } finally {
    try {
      await reader.cancel();
    } catch {
      // The response may already be closed; cleanup must not mask its result.
    } finally {
      reader.releaseLock();
    }
  }
}
import { adkT } from "./i18n";
