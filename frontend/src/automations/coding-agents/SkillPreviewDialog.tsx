import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  getCodingAgentSkillPreview,
  type BundledCodingAgentSkill,
  type CodingAgentSkillPreview,
  type CodingAgentSkillPreviewFile,
} from "../../adk/codingAgents";

interface SkillPreviewDialogProps {
  skill: BundledCodingAgentSkill;
  onClose: () => void;
}

interface SkillFileGroup {
  directory: string;
  files: CodingAgentSkillPreviewFile[];
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="m4 4 8 8m0-8-8 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function DocumentIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M4 1.8h5l3 3V14H4z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
      <path d="M9 1.8V5h3M6 8h4M6 10.5h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}

function FolderIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M1.8 4.5h4l1.2-1.3h2.2l1.2 1.3h3.8v8H1.8z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
    </svg>
  );
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : "";
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`;
}

function fileName(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] ?? path;
}

function groupFiles(files: CodingAgentSkillPreviewFile[]): SkillFileGroup[] {
  const groups = new Map<string, CodingAgentSkillPreviewFile[]>();
  for (const file of files) {
    const parts = file.path.split("/");
    const directory = parts.length > 1 ? parts.slice(0, -1).join("/") : "";
    groups.set(directory, [...(groups.get(directory) ?? []), file]);
  }
  return Array.from(groups, ([directory, groupedFiles]) => ({
    directory,
    files: groupedFiles,
  })).sort((left, right) => {
    if (!left.directory) return -1;
    if (!right.directory) return 1;
    return left.directory.localeCompare(right.directory);
  });
}

export function SkillPreviewDialog({ skill, onClose }: SkillPreviewDialogProps) {
  const { t } = useTranslation("automations");
  const dialogRef = useRef<HTMLDialogElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const descriptionId = useId();
  const [preview, setPreview] = useState<CodingAgentSkillPreview | null>(null);
  const [selectedPath, setSelectedPath] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    previousFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
    return () => {
      if (dialog?.open) dialog.close();
      previousFocusRef.current?.focus();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setPreview(null);
    setSelectedPath("");
    void getCodingAgentSkillPreview(skill.id, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setPreview(result);
        const initialFile = result.files.find((file) => file.path === "SKILL.md")
          ?? result.files[0];
        setSelectedPath(initialFile?.path ?? "");
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted && !isAbortError(requestError)) {
          setError(errorMessage(requestError));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [reload, skill.id]);

  const groups = useMemo(() => groupFiles(preview?.files ?? []), [preview]);
  const selectedFile = preview?.files.find((file) => file.path === selectedPath) ?? null;
  const skillName = t(`codingAgents.skills.items.${skill.id}.name`, {
    defaultValue: skill.name,
  });

  return (
    <dialog
      ref={dialogRef}
      className="coding-agents-preview-dialog"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onMouseDown={(event) => {
        const bounds = event.currentTarget.getBoundingClientRect();
        const outside = event.clientX < bounds.left
          || event.clientX > bounds.right
          || event.clientY < bounds.top
          || event.clientY > bounds.bottom;
        if (outside) onClose();
      }}
    >
      <header className="coding-agents-preview-header">
        <span className="coding-agents-preview-mark"><FolderIcon /></span>
        <div>
          <h2 id={titleId}>{skillName}</h2>
          <p id={descriptionId}>{t("codingAgents.preview.description")}</p>
        </div>
        <button type="button" autoFocus aria-label={t("codingAgents.preview.close")} onClick={onClose}>
          <CloseIcon />
        </button>
      </header>

      {loading ? (
        <div className="coding-agents-preview-state"><i />{t("codingAgents.preview.loading")}</div>
      ) : error ? (
        <div className="coding-agents-preview-state is-error" role="alert">
          <span>{error || t("codingAgents.preview.error")}</span>
          <button type="button" onClick={() => setReload((value) => value + 1)}>{t("codingAgents.retry")}</button>
        </div>
      ) : (
        <div className="coding-agents-preview-layout">
          <nav className="coding-agents-preview-tree" aria-label={t("codingAgents.preview.skillFiles", { name: skillName })}>
            <div className="coding-agents-preview-tree-title">
              <span>{t("codingAgents.preview.files")}</span><small>{preview?.files.length ?? 0}</small>
            </div>
            <div className="coding-agents-preview-tree-scroll">
              {groups.map((group) => group.directory ? (
                <details key={group.directory} open>
                  <summary><FolderIcon /><span>{group.directory}</span></summary>
                  <div>
                    {group.files.map((file) => (
                      <button
                        type="button"
                        key={file.path}
                        className={selectedPath === file.path ? "is-selected" : ""}
                        aria-current={selectedPath === file.path ? "true" : undefined}
                        onClick={() => setSelectedPath(file.path)}
                      >
                        <DocumentIcon /><span>{fileName(file.path)}</span>
                      </button>
                    ))}
                  </div>
                </details>
              ) : group.files.map((file) => (
                <button
                  type="button"
                  key={file.path}
                  className={selectedPath === file.path ? "is-selected" : ""}
                  aria-current={selectedPath === file.path ? "true" : undefined}
                  onClick={() => setSelectedPath(file.path)}
                >
                  <DocumentIcon /><span>{file.path}</span>
                </button>
              )))}
            </div>
          </nav>

          <section className="coding-agents-preview-file" aria-label={t("codingAgents.preview.fileContent")}>
            {selectedFile ? (
              <>
                <header>
                  <strong>{selectedFile.path}</strong>
                  <span>{formatFileSize(selectedFile.size)}</span>
                </header>
                {selectedFile.previewable && selectedFile.content !== null ? (
                  <pre tabIndex={0}><code>{selectedFile.content}</code></pre>
                ) : (
                  <div className="coding-agents-preview-unavailable">
                    {t("codingAgents.preview.notPreviewable")}
                  </div>
                )}
              </>
            ) : (
              <div className="coding-agents-preview-unavailable">{t("codingAgents.preview.noFiles")}</div>
            )}
          </section>
        </div>
      )}
    </dialog>
  );
}
