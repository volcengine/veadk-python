// Local skill picker: user uploads a folder (via <input webkitdirectory>) or a
// .zip file from their computer. Each skill directory must contain a SKILL.md
// with name/description frontmatter. Files are materialized client-side and
// embedded directly in SelectedSkill.localFiles so they survive YAML
// round-trip and project generation without any network round-trip.

import { useEffect, useRef, useState } from "react";
import { Check, FolderUp, Info, Plus } from "lucide-react";
import { readFolderSkills, readZipSkills, type LocalReadResult } from "./skills/local";
import type { SelectedSkill, SkillHit } from "./skills/types";

export function LocalPicker({
  selected,
  onChange,
}: {
  selected: SelectedSkill[];
  onChange: (next: SelectedSkill[]) => void;
}) {
  const folderRef = useRef<HTMLInputElement>(null);
  const zipRef = useRef<HTMLInputElement>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [foundHits, setFoundHits] = useState<SkillHit[]>([]);
  const [busy, setBusy] = useState(false);

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

  const onFolderChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setBusy(true);
    try {
      showResult(await readFolderSkills(files));
    } finally {
      setBusy(false);
      // reset so selecting the same folder again fires change
      if (folderRef.current) folderRef.current.value = "";
    }
  };

  const onZipChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      showResult(await readZipSkills(file));
    } finally {
      setBusy(false);
      if (zipRef.current) zipRef.current.value = "";
    }
  };

  return (
    <div className="cw-local">
      <div className="cw-local-actions">
        <button
          type="button"
          className="cw-btn cw-btn-soft"
          onClick={() => folderRef.current?.click()}
          disabled={busy}
        >
          <FolderUp className="cw-i" />
          上传文件夹
        </button>
        <button
          type="button"
          className="cw-btn cw-btn-soft"
          onClick={() => zipRef.current?.click()}
          disabled={busy}
        >
          <FolderUp className="cw-i" />
          上传 .zip
        </button>
        <input
          ref={folderRef}
          type="file"
          // @ts-expect-error - webkitdirectory is non-standard but widely supported
          webkitdirectory=""
          directory=""
          multiple
          hidden
          onChange={onFolderChange}
        />
        <input
          ref={zipRef}
          type="file"
          accept=".zip,application/zip"
          hidden
          onChange={onZipChange}
        />
      </div>

      <p className="cw-local-hint">
        每个技能需包含 SKILL.md（含 name / description frontmatter）。支持选择包含多个技能文件夹的目录。
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
                    <span className="cw-skill-result-desc">{hit.description}</span>
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
