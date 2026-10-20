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
      adkT("common.contentTypeMissing");
    const excerpt = text.trim().slice(0, 2000);
    const detail = excerpt ? `\n${adkT("common.response", { response: excerpt })}` : "";
    throw new Error(
      adkT("jsonResponse.nonJson", {
        fallback,
        status: response.status,
        contentType,
        detail,
      }),
    );
  }
}
import { adkT } from "./i18n";
