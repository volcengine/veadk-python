export function isValidModelApiBaseUrl(value: string | undefined): boolean {
  const raw = value?.trim();
  if (!raw) return true;
  try {
    const url = new URL(raw);
    return (
      (url.protocol === "https:" || url.protocol === "http:") &&
      url.hostname.length > 0 &&
      url.username === "" &&
      url.password === ""
    );
  } catch {
    return false;
  }
}
