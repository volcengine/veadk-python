// Minimal Server-Sent-Events parser for `fetch` response bodies.
//
// The ADK `/run_sse` endpoint emits `data: <json>\n\n` frames. This async
// generator yields each parsed JSON payload as it arrives.

export async function* parseSSE(
  response: Response,
): AsyncGenerator<unknown, void, unknown> {
  if (!response.body) throw new Error("Response has no body");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

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
        const data = frame
          .split(/\r?\n/)
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (data) {
          try {
            yield JSON.parse(data);
          } catch {
            if (data !== "[DONE]" && data !== "ping") {
              console.debug(
                `parseSSE: dropping unparseable frame (${data.length} chars):`,
                data.slice(0, 200),
              );
            }
          }
        }
        separator = buffer.match(/\r?\n\r?\n/);
      }
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
