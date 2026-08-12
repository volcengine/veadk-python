import type { CloudProvider } from "./cloudProvider";

interface ModelContextRule {
  pattern: RegExp;
  tokens: number;
}

const SHARED_RULES: readonly ModelContextRule[] = [
  { pattern: /(?:^|[-_.])glm[-_.]?5[-_.]?2(?:[-_.]|$)/, tokens: 1_024_000 },
  { pattern: /(?:^|[-_.])deepseek[-_.]?v4(?:[-_.]|$)/, tokens: 1_024_000 },
];

const VOLCENGINE_RULES: readonly ModelContextRule[] = [
  { pattern: /doubao[-_.]seed[-_.]evolving(?:[-_.]|$)/, tokens: 1_024_000 },
  { pattern: /doubao[-_.]seed[-_.]translation(?:[-_.]|$)/, tokens: 4_000 },
  { pattern: /doubao[-_.]seed[-_.]character(?:[-_.]|$)/, tokens: 128_000 },
  { pattern: /doubao[-_.]1[-_.]?5[-_.]pro[-_.]32k[-_.]character(?:[-_.]|$)/, tokens: 32_000 },
  { pattern: /doubao[-_.]1[-_.]?5[-_.]pro[-_.]32k(?:[-_.]|$)/, tokens: 128_000 },
  { pattern: /doubao[-_.]1[-_.]?5[-_.](?:lite[-_.]32k|vision[-_.]pro[-_.]32k)(?:[-_.]|$)/, tokens: 32_000 },
  { pattern: /doubao[-_.]seed[-_.]2[-_.][01](?:[-_.]|$)/, tokens: 256_000 },
  { pattern: /doubao[-_.]seed[-_.](?:1[-_.][68]|code[-_.]preview)(?:[-_.]|$)/, tokens: 256_000 },
  { pattern: /(?:^|[-_.])glm[-_.]?4[-_.]?7(?:[-_.]|$)/, tokens: 200_000 },
];

const BYTEPLUS_RULES: readonly ModelContextRule[] = [
  { pattern: /dola[-_.]seed[-_.]2[-_.]1(?:[-_.]|$)/, tokens: 256_000 },
  { pattern: /(?:^|[-_.])seed[-_.]2[-_.]0(?:[-_.]|$)/, tokens: 256_000 },
  { pattern: /(?:^|[-_.])seed[-_.]1[-_.][68](?:[-_.]|$)/, tokens: 256_000 },
  { pattern: /(?:^|[-_.])glm[-_.]?4[-_.]?7(?:[-_.]|$)/, tokens: 256_000 },
  { pattern: /(?:^|[-_.])deepseek[-_.]?v3[-_.]?2(?:[-_.]|$)/, tokens: 128_000 },
  { pattern: /(?:^|[-_.])gpt[-_.]?oss[-_.]?120b(?:[-_.]|$)/, tokens: 128_000 },
];

function explicitContextSuffix(modelName: string): number | null {
  const match = modelName.match(/(?:^|[-_.])(\d+(?:\.\d+)?)(k|m)(?:[-_.]|$)/i);
  if (!match) return null;
  const amount = Number(match[1]);
  if (!Number.isFinite(amount) || amount <= 0) return null;
  return Math.round(amount * (match[2].toLowerCase() === "m" ? 1_000_000 : 1_000));
}

/**
 * Ark model context windows published by Volcengine and BytePlus.
 * Values intentionally use the providers' decimal K convention.
 * Volcengine: https://docs.volcengine.com/docs/82379/1330310?lang=zh
 * BytePlus: https://docs.byteplus.com/en/docs/ModelArk/1330310
 */
export function contextWindowForModel(
  modelName: string,
  cloudProvider: CloudProvider,
): number | null {
  const normalized = modelName.trim().toLowerCase().split("/").pop() ?? "";
  if (!normalized) return null;
  const providerRules = cloudProvider === "byteplus"
    ? BYTEPLUS_RULES
    : VOLCENGINE_RULES;
  for (const rule of [...providerRules, ...SHARED_RULES]) {
    if (rule.pattern.test(normalized)) return rule.tokens;
  }
  return explicitContextSuffix(normalized);
}
