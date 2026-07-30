export const RUNTIME_DESCRIPTION_MAX_BYTES = 255;

const allowedRuntimeDescriptionCharacter = /[\p{L}\p{M}\p{N}\p{P}\p{Zs}]/u;

export function normalizeRuntimeDescription(value: string): string {
  const singleLine = value.normalize("NFKC").replace(/\s+/gu, " ").trim();
  const encoder = new TextEncoder();
  let byteLength = 0;
  let normalized = "";

  for (const character of singleLine) {
    if (!allowedRuntimeDescriptionCharacter.test(character)) continue;
    const characterBytes = encoder.encode(character).byteLength;
    if (byteLength + characterBytes > RUNTIME_DESCRIPTION_MAX_BYTES) break;
    normalized += character;
    byteLength += characterBytes;
  }

  return normalized.replace(/ +/g, " ").trimEnd();
}
