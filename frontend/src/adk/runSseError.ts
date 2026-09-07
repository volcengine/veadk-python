const SESSION_NOT_FOUND_PATTERN = /\brun_sse\s*failed\s*:\s*404\b/i;
const SESSION_DETAIL_PATTERN = /session not found/i;
const ROUTE_NOT_FOUND_PATTERN = /(?:^|[：:\s])not found\s*$/i;
const TOOL_ARGUMENT_JSON_PATTERN =
  /Expecting (?:'[^']+'|\w+)(?: delimiter)?: line \d+ column \d+ \(char \d+\)/i;
const RESOURCE_COLLECTION_EXPIRED_PATTERN =
  /Unknown or expired collection_id\s+'[^']+'\.\s*Call collect_resources first\./i;
const MODEL_QUOTA_PATTERN =
  /(?:RateLimitError|\bTPM\b|\bRPM\b|tokens? per minute|requests? per minute)[\s\S]*(?:\b429\b|limit|quota)|\b429\b[\s\S]*(?:model|RateLimitError|\bTPM\b|\bRPM\b)/i;

function appendHint(message: string, hint: string): string {
  return message.includes(hint) ? message : `${message}\n\n${hint}`;
}

/** Preserve the upstream error before appending diagnosis and recovery guidance. */
export function formatRunSseError(error: unknown): string {
  const message = String(error);
  const rawResponseLabel = adkT("runSse.rawResponseLabel");
  let formatted = message.includes(rawResponseLabel)
    ? message
    : `${rawResponseLabel}${message}`;
  if (TOOL_ARGUMENT_JSON_PATTERN.test(message)) {
    formatted = appendHint(formatted, adkT("runSse.toolArgumentHint"));
  } else if (RESOURCE_COLLECTION_EXPIRED_PATTERN.test(message)) {
    return appendHint(formatted, adkT("runSse.resourceCollectionExpiredHint"));
  } else if (MODEL_QUOTA_PATTERN.test(message)) {
    return appendHint(formatted, adkT("runSse.modelQuotaHint"));
  } else if (SESSION_NOT_FOUND_PATTERN.test(message)) {
    if (SESSION_DETAIL_PATTERN.test(message)) {
      formatted = appendHint(formatted, adkT("runSse.persistentMemoryHint"));
    } else if (ROUTE_NOT_FOUND_PATTERN.test(message)) {
      formatted = appendHint(formatted, adkT("runSse.unsupportedRouteHint"));
    }
  }
  return appendHint(formatted, adkT("runSse.networkConfigurationHint"));
}
import { adkT } from "./i18n";
