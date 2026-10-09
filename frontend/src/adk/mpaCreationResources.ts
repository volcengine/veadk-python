export function validPgTarget(host = "", port = ""): boolean {
  const selectedHost = host.trim();
  const selectedPort = port.trim();
  return (
    (!selectedHost && !selectedPort) ||
    (selectedHost.length <= 255 &&
      /^[A-Za-z0-9][A-Za-z0-9.-]*$/.test(selectedHost) &&
      !selectedHost.includes("..") &&
      /^[0-9]{1,5}$/.test(selectedPort) &&
      Number(selectedPort) >= 1 &&
      Number(selectedPort) <= 65535)
  );
}

export function validOpenViking(url = "", resourceId = "", apiKey = ""): boolean {
  const selectedUrl = url.trim();
  const selectedId = resourceId.trim();
  if (!selectedUrl && !selectedId && !apiKey) return true;
  if (!selectedUrl || !selectedId || !apiKey.trim()) return false;
  if (selectedUrl.length > 1024 || /\s/.test(selectedUrl)) return false;
  const authority = selectedUrl.replace(/^https:\/\//, "").split("/", 1)[0];
  if (authority.includes(":")) return false;
  try {
    const parsed = new URL(selectedUrl);
    return (
      parsed.protocol === "https:" &&
      !!parsed.hostname &&
      !parsed.username &&
      !parsed.password &&
      !parsed.port &&
      !parsed.search &&
      !parsed.hash &&
      selectedId.length <= 128 && /^ov-[a-zA-Z0-9_-]+$/.test(selectedId)
    );
  } catch {
    return false;
  }
}
