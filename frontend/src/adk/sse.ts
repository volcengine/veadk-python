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

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (data) {
        try {
          yield JSON.parse(data);
        } catch {
          // Ignore non-JSON keep-alive frames.
        }
      }
    }
  }
}
