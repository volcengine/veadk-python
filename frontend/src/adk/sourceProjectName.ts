export const SOURCE_NAME_MAX_LENGTH = 128;

export function normalizeSourceName(value: string): string {
  return value.normalize("NFC").trim();
}

export function sourceNameError(value: string): "required" | "tooLong" | "invalidCharacters" | null {
  if (/[<>\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u.test(value)) return "invalidCharacters";
  const name = normalizeSourceName(value);
  if (!name) return "required";
  if (Array.from(name).length > SOURCE_NAME_MAX_LENGTH) return "tooLong";
  return null;
}
