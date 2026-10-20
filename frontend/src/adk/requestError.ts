export function formatRequestError(
  cause: unknown,
  action: string,
  request?: string,
): string {
  const detail = cause instanceof Error
    ? `${cause.name}: ${cause.message}`
    : String(cause || adkT("common.unknownError"));
  return [
    adkT("requestError.actionFailed", { action }),
    adkT("requestError.detail", { detail }),
    request ? adkT("requestError.request", { request }) : "",
  ].filter(Boolean).join("\n");
}
import { adkT } from "./i18n";
