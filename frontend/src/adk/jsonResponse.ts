/** Parse a successful JSON API response without hiding HTML gateway errors. */
export async function parseJsonResponse<T>(
  response: Response,
  fallback: string,
): Promise<T> {
  const text = await response.text().catch(() => "");
  try {
    return JSON.parse(text) as T;
  } catch {
    const contentType =
      response.headers.get("content-type")?.split(";", 1)[0] ||
      "Content-Type 缺失";
    const excerpt = text.trim().slice(0, 2000);
    const detail = excerpt ? `\n响应：${excerpt}` : "";
    throw new Error(
      `${fallback}：服务端返回非 JSON 响应（HTTP ${response.status}，${contentType}）${detail}`,
    );
  }
}
