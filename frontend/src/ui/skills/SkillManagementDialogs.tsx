import { useEffect, useRef, useState } from "react";
import type { SkillSpaceRef } from "../../create/skills/skillspace";
import {
  createSkillSpace,
  updateSkillSpace,
  uploadSkillArchive,
  validateSkillArchive,
} from "../../adk/skills";
import { normalizeSkillError, SkillErrorDetails } from "./SkillErrorDetails";

function DialogFrame({
  title,
  children,
  onClose,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  className?: string;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="skill-dialog-backdrop" onMouseDown={onClose}>
      <section className={`skill-dialog${className ? ` ${className}` : ""}`} role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <header><h2>{title}</h2><button ref={closeRef} type="button" onClick={onClose} aria-label="关闭">关闭</button></header>
        {children}
      </section>
    </div>
  );
}

export function CreateSkillSpaceDialog({ region, onClose, onCreated }: { region: string; onClose: () => void; onCreated: (space: SkillSpaceRef) => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const submit = async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      onCreated(await createSkillSpace({ name: name.trim(), description: description.trim() || undefined, region }));
    } catch (reason) {
      setError(normalizeSkillError(reason, "创建 Skill 空间失败"));
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <DialogFrame title="新建 Skill 空间" onClose={onClose}>
      <div className="skill-dialog__body">
        <label><span>名称</span><input autoFocus value={name} maxLength={128} onChange={(event) => setName(event.target.value)} /></label>
        <label><span>描述（可选）</span><textarea value={description} maxLength={1024} onChange={(event) => setDescription(event.target.value)} /></label>
        {error ? <div className="skill-inline-error"><SkillErrorDetails error={error} /></div> : null}
      </div>
      <footer><button type="button" className="skill-button" onClick={onClose}>取消</button><button type="button" className="skill-button skill-button--primary" disabled={!name.trim() || submitting} onClick={() => void submit()}>{submitting ? "创建中…" : "创建"}</button></footer>
    </DialogFrame>
  );
}

export function EditSkillSpaceDialog({
  space,
  region,
  onClose,
  onUpdated,
}: {
  space: SkillSpaceRef;
  region: string;
  onClose: () => void;
  onUpdated: (space: SkillSpaceRef) => void;
}) {
  const [name, setName] = useState(space.name);
  const [description, setDescription] = useState(space.description || "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const submit = async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await updateSkillSpace({
        spaceId: space.id,
        name: name.trim(),
        description: description.trim() || undefined,
        region,
      });
      onUpdated({ ...space, ...updated, skillCount: space.skillCount });
    } catch (reason) {
      setError(normalizeSkillError(reason, "更新 Skill 空间失败"));
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <DialogFrame title="编辑 Skill 空间" onClose={onClose}>
      <div className="skill-dialog__body">
        <label><span>名称</span><input autoFocus value={name} maxLength={128} onChange={(event) => setName(event.target.value)} /></label>
        <label><span>描述（可选）</span><textarea value={description} maxLength={1024} onChange={(event) => setDescription(event.target.value)} /></label>
        {error ? <div className="skill-inline-error"><SkillErrorDetails error={error} /></div> : null}
      </div>
      <footer><button type="button" className="skill-button" onClick={onClose}>取消</button><button type="button" className="skill-button skill-button--primary" disabled={!name.trim() || submitting} onClick={() => void submit()}>{submitting ? "保存中…" : "保存"}</button></footer>
    </DialogFrame>
  );
}

export function UploadSkillDialog({ space, region, onClose, onUploaded }: { space: SkillSpaceRef; region: string; onClose: () => void; onUploaded: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [validation, setValidation] = useState<{ name: string; fileCount: number } | null>(null);
  const [validating, setValidating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [dragging, setDragging] = useState(false);
  const validationRequest = useRef(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const selectFile = async (selected: File | null) => {
    const request = validationRequest.current + 1;
    validationRequest.current = request;
    setFile(selected);
    setValidation(null);
    setError(null);
    setValidating(Boolean(selected));
    if (!selected) return;
    try {
      const result = await validateSkillArchive(selected);
      if (validationRequest.current === request) {
        setValidation({ name: result.name, fileCount: result.files.length });
      }
    } catch (reason) {
      if (validationRequest.current === request) {
        setError(normalizeSkillError(reason, "Skill ZIP 格式校验失败"));
      }
    } finally {
      if (validationRequest.current === request) setValidating(false);
    }
  };
  const upload = async () => {
    if (!file || !validation) return;
    setSubmitting(true);
    setError(null);
    try {
      await uploadSkillArchive({ spaceId: space.id, region, project: space.projectName, file });
      onUploaded();
    } catch (reason) {
      setError(normalizeSkillError(reason, "上传 Skill 失败"));
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <DialogFrame title={`上传到 ${space.name}`} className="skill-upload-dialog" onClose={onClose}>
      <div className="skill-dialog__body">
        <input
          ref={fileInputRef}
          className="skill-upload-dialog__input"
          type="file"
          accept=".zip,application/zip"
          onChange={(event) => void selectFile(event.target.files?.[0] || null)}
        />
        <button
          type="button"
          className={`skill-upload-dropzone${dragging ? " is-dragging" : ""}`}
          onClick={() => fileInputRef.current?.click()}
          onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
          onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; setDragging(true); }}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
          }}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            void selectFile(event.dataTransfer.files?.[0] || null);
          }}
        >
          <strong>{file ? file.name : "拖拽 Skill ZIP 到这里"}</strong>
          <span>{file ? `${file.size.toLocaleString()} 字节` : "或点击选择本地文件"}</span>
        </button>
        <p>ZIP 根目录需要包含 SKILL.md，也可以只包含一层包装目录。选择后仅检查格式，不会自动上传。</p>
        {validating ? <div className="skill-inline-notice">正在检查文件格式…</div> : null}
        {validation ? <div className="skill-inline-notice">格式检查通过：{validation.name}，共 {validation.fileCount} 个文件</div> : null}
        {error ? <div className="skill-inline-error"><SkillErrorDetails error={error} /></div> : null}
      </div>
      <footer><button type="button" className="skill-button" onClick={onClose}>取消</button><button type="button" className="skill-button skill-button--primary" disabled={!file || !validation || validating || submitting} onClick={() => void upload()}>{submitting ? "上传中…" : "上传"}</button></footer>
    </DialogFrame>
  );
}
