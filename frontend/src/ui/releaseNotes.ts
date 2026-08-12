const RELEASE_NOTE_SEPARATOR = /[;；]/;

export function splitReleaseNotes(notes: readonly string[]): string[] {
  const uniqueNotes = new Set<string>();
  for (const note of notes) {
    for (const item of note.split(RELEASE_NOTE_SEPARATOR)) {
      const normalized = item.trim();
      if (normalized) uniqueNotes.add(normalized);
    }
  }
  return [...uniqueNotes];
}

export function parseReleaseNotes(value: string | undefined): string[] {
  if (!value?.trim()) return [];
  try {
    const parsed: unknown = JSON.parse(value);
    if (Array.isArray(parsed)) {
      return splitReleaseNotes(
        parsed.filter((item): item is string => typeof item === "string"),
      );
    }
  } catch {
    // Older local builds may provide the release summary as a plain string.
  }
  return splitReleaseNotes([value]);
}
