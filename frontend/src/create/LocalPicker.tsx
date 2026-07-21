// Local skill picker: user uploads a folder (via <input webkitdirectory>) or a
// .zip file from their computer. Each skill directory must contain a SKILL.md
// with name/description frontmatter. Files are materialized client-side and
// embedded directly in SelectedSkill.localFiles so they survive YAML
// round-trip and project generation without any network round-trip.

import { useEffect, useRef, useState } from "react";
import { Check, FolderUp, Info, Plus } from "lucide-react";
import { readFolderSkills, readZipSkills, type LocalReadResult } from "./skills/local";
import type { SelectedSkill, SkillHit } from "./skills/types";
import { displayDescription } from "./displayText";

interface DroppedEntry {
  isFile: boolean;
  isDirectory: boolean;
  name: string;
}

interface DroppedFileEntry extends DroppedEntry {
  file: (
    success: (file: File) => void,
    failure?: (error: DOMException) => void,
  ) => void;
}

interface DroppedDirectoryReader {
  readEntries: (
    success: (entries: DroppedEntry[]) => void,
    failure?: (error: DOMException) => void,
  ) => void;
}

interface DroppedDirectoryEntry extends DroppedEntry {
  createReader: () => DroppedDirectoryReader;
}

interface DroppedFile {
  file: File;
  path: string;
}

function fileFromEntry(entry: DroppedFileEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

async function directoryEntries(
  entry: DroppedDirectoryEntry,
): Promise<DroppedEntry[]> {
  const reader = entry.createReader();
  const entries: DroppedEntry[] = [];
  while (true) {
    const chunk = await new Promise<DroppedEntry[]>((resolve, reject) =>
      reader.readEntries(resolve, reject),
    );
    if (chunk.length === 0) return entries;
    entries.push(...chunk);
  }
}

async function collectDroppedFiles(
  entry: DroppedEntry,
  parentPath = "",
): Promise<DroppedFile[]> {
  const path = parentPath ? `${parentPath}/${entry.name}` : entry.name;
  if (entry.isFile) {
    return [{ file: await fileFromEntry(entry as DroppedFileEntry), path }];
  }
  if (!entry.isDirectory) return [];
  const children = await directoryEntries(entry as DroppedDirectoryEntry);
  return (await Promise.all(
    children.map((child) => collectDroppedFiles(child, path)),
  )).flat();
}

export function LocalPicker({
  selected,
  onChange,
}: {
  selected: SelectedSkill[];
  onChange: (next: SelectedSkill[]) => void;
}) {
  const [errors, setErrors] = useState<string[]>([]);
  const [foundHits, setFoundHits] = useState<SkillHit[]>([]);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const dragDepthRef = useRef(0);

  // Match by folder name (frontmatter `name`), the de-dup key for local uploads.
  const isSelectedByFolder = (folder: string) =>
    selected.some((s) => s.source === "local" && s.folder === folder);

  const toggleHit = (hit: SkillHit) => {
    if (!hit.localFiles) return;
    if (isSelectedByFolder(hit.folder || hit.name)) {
      onChange(
        selected.filter(
          (s) => !(s.source === "local" && s.folder === (hit.folder || hit.name)),
        ),
      );
    } else {
      onChange([
        ...selected,
        {
          source: "local",
          folder: hit.folder || hit.name,
          name: hit.name,
          description: hit.description,
          localFiles: hit.localFiles,
        },
      ]);
    }
  };

  // Use refs so the async change handlers always see the latest state when
  // they run (useState closures would otherwise capture stale state across
  // multiple uploads in a row).
  const foundHitsRef = useRef<SkillHit[]>([]);
  const selectedRef = useRef<SelectedSkill[]>(selected);
  useEffect(() => {
    foundHitsRef.current = foundHits;
  }, [foundHits]);
  useEffect(() => {
    selectedRef.current = selected;
  }, [selected]);

  const showResult = (res: LocalReadResult) => {
    // Merge new hits into the displayed list (append, don't replace) so
    // repeated uploads accumulate. De-dupe by folder name (frontmatter
    // `name`) across both the displayed list and already-selected skills.
    const existing = new Set([
      ...foundHitsRef.current.map((h) => h.folder || h.name),
      ...selectedRef.current
        .filter((s) => s.source === "local")
        .map((s) => s.folder),
    ]);
    const duplicateNames: string[] = [];
    const fresh: SkillHit[] = [];
    for (const hit of res.hits) {
      const key = hit.folder || hit.name;
      if (existing.has(key)) {
        duplicateNames.push(hit.name);
        continue;
      }
      existing.add(key);
      fresh.push(hit);
    }
    setFoundHits((prev) => [...prev, ...fresh]);

    // Surface duplicates as a banner line (combined with any parse errors).
    const allErrors = [...res.errors];
    if (duplicateNames.length > 0) {
      allErrors.push(`已跳过重复技能：${duplicateNames.join("、")}`);
    }
    setErrors(allErrors);

    // Auto-add single-hit uploads for convenience (but not duplicates).
    if (fresh.length === 1 && res.errors.length === 0 && duplicateNames.length === 0) {
      const hit = fresh[0];
      if (hit.localFiles) {
        onChange([
          ...selectedRef.current,
          {
            source: "local",
            folder: hit.folder || hit.name,
            name: hit.name,
            description: hit.description,
            localFiles: hit.localFiles,
          },
        ]);
      }
    }
  };

  const onDragEnter = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragDepthRef.current += 1;
    setDragging(true);
  };

  const onDragLeave = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setDragging(false);
  };

  const onDrop = async (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragDepthRef.current = 0;
    setDragging(false);
    if (busy) return;

    const entries = Array.from(event.dataTransfer.items)
      .map((item) => item.webkitGetAsEntry?.() as DroppedEntry | null)
      .filter((entry): entry is DroppedEntry => entry !== null);
    if (entries.length === 0) {
      setErrors(["请拖入包含 SKILL.md 的文件夹或一个 .zip 文件"]);
      return;
    }

    setBusy(true);
    try {
      const dropped = (await Promise.all(
        entries.map((entry) => collectDroppedFiles(entry)),
      )).flat();
      const includesDirectory = entries.some((entry) => entry.isDirectory);
      if (
        !includesDirectory &&
        dropped.length === 1 &&
        dropped[0].file.name.toLowerCase().endsWith(".zip")
      ) {
        showResult(await readZipSkills(dropped[0].file));
        return;
      }
      if (!includesDirectory) {
        setErrors(["请拖入包含 SKILL.md 的文件夹或一个 .zip 文件"]);
        return;
      }
      const paths = new Map(dropped.map(({ file, path }) => [file, path]));
      showResult(await readFolderSkills(dropped.map(({ file }) => file), paths));
    } catch (error) {
      setErrors([
        `读取失败：${error instanceof Error ? error.message : String(error)}`,
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="cw-local">
      <div
        className={`cw-local-dropzone ${dragging ? "is-dragging" : ""}`}
        role="group"
        aria-label="拖入文件夹或 ZIP，自动识别 Skill"
        onDragEnter={onDragEnter}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={onDragLeave}
        onDrop={(event) => void onDrop(event)}
      >
        <FolderUp className="cw-local-drop-icon" aria-hidden />
        <p className="cw-local-drop-hint">
          拖入文件夹或 ZIP，自动识别 Skill
        </p>
      </div>

      <p className="cw-local-hint">
        每个技能需包含 SKILL.md（含 name / description frontmatter）。支持包含多个技能的目录。
      </p>

      {busy && <p className="cw-empty-line">正在读取文件…</p>}

      {errors.length > 0 && (
        <div className="cw-banner">
          <Info className="cw-i" />
          <span>{errors.join("；")}</span>
        </div>
      )}

      {foundHits.length > 0 && (
        <div className="cw-skill-results">
          {foundHits.map((hit) => {
            const on = isSelectedByFolder(hit.folder || hit.name);
            return (
              <button
                key={hit.id}
                type="button"
                className={`cw-skill-result ${on ? "is-on" : ""}`}
                onClick={() => toggleHit(hit)}
                aria-pressed={on}
              >
                <span className="cw-skill-result-icon" aria-hidden>
                  {on ? (
                    <Check className="cw-i cw-i-sm" />
                  ) : (
                    <Plus className="cw-i cw-i-sm" />
                  )}
                </span>
                <span className="cw-skill-result-meta">
                  <span className="cw-skill-result-name">{hit.name}</span>
                  {hit.description && (
                    <span className="cw-skill-result-desc">
                      {displayDescription(hit.description)}
                    </span>
                  )}
                  <span className="cw-skill-result-repo">
                    本地 · {hit.localFiles?.length ?? 0} 个文件
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
