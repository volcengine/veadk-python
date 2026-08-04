import { useRef, useState } from "react";
import { TextShimmer } from "../text-shimmer/TextShimmer";
import { downloadSkillCandidate } from "./api";
import { SkillConversationStream } from "./SkillConversationStream";
import type {
  PublishSkillOptions,
  SkillCandidate,
  SkillCandidateStage,
  SkillCandidateStatus,
} from "./types";

const STAGE_LABELS: Record<SkillCandidateStage, string> = {
  provisioning: "正在准备 Sandbox",
  generating: "正在生成 Skill",
  validating: "正在校验结构",
  packaging: "正在打包",
  completed: "生成完成",
  failed: "生成失败",
};

const MAX_SKILL_PREVIEW_CHARS = 120_000;

interface SkillCandidatePaneProps {
  label: string;
  jobId: string;
  candidate: SkillCandidate;
  selected: boolean;
  publishing: boolean;
  publishDisabled: boolean;
  publishError?: string;
  onSelect: () => void;
  onPublish: (options: PublishSkillOptions) => void;
}

function StatusIcon({ status }: { status: SkillCandidateStatus }) {
  if (status === "succeeded") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <circle cx="10" cy="10" r="7" />
        <path d="m6.7 10.1 2.1 2.2 4.6-4.8" />
      </svg>
    );
  }
  if (status === "failed") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <circle cx="10" cy="10" r="7" />
        <path d="M10 6.2v4.5M10 13.6h.01" />
      </svg>
    );
  }
  return (
    <svg className="skill-candidate__spinner" viewBox="0 0 20 20" aria-hidden="true">
      <circle cx="10" cy="10" r="7" />
      <path d="M10 3a7 7 0 0 1 7 7" />
    </svg>
  );
}

function PreviewIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M4.2 3.5h7.1l4.5 4.6v8.4H4.2z" />
      <path d="M11.3 3.5v4.6h4.5M7 11h6M7 13.8h4.2" />
    </svg>
  );
}

function BackIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="m9 5-5 5 5 5M4.5 10H16" />
    </svg>
  );
}

function FilePreview({ candidate }: { candidate: SkillCandidate }) {
  const [activePath, setActivePath] = useState("SKILL.md");
  const skillFile = candidate.files.find((file) => file.path.endsWith("SKILL.md"));
  const files = candidate.skillMd && !skillFile
    ? [{ path: "SKILL.md", size: new Blob([candidate.skillMd]).size }, ...candidate.files]
    : candidate.files;
  const activeFile = files.find((file) => file.path === activePath) ?? files[0];
  const skillPreview = candidate.skillMd?.slice(0, MAX_SKILL_PREVIEW_CHARS);
  const skillPreviewTruncated = (candidate.skillMd?.length ?? 0) > MAX_SKILL_PREVIEW_CHARS;

  if (files.length === 0) return null;
  return (
    <div className="skill-files">
      <div className="skill-files__tabs" role="tablist" aria-label={`${candidate.name ?? "Skill"} 文件`}>
        {files.map((file) => (
          <button
            key={file.path}
            type="button"
            role="tab"
            aria-selected={activeFile?.path === file.path}
            className={activeFile?.path === file.path ? "is-active" : ""}
            onClick={() => setActivePath(file.path)}
          >
            {file.path}
          </button>
        ))}
      </div>
      {candidate.skillMd && activeFile?.path.endsWith("SKILL.md") ? (
        <>
          <pre className="skill-files__content"><code>{skillPreview}</code></pre>
          {skillPreviewTruncated ? (
            <p className="skill-files__truncated">预览内容较长，完整文件请下载 ZIP 查看。</p>
          ) : null}
        </>
      ) : (
        <div className="skill-files__unavailable">
          {activeFile ? `${activeFile.path} · ${activeFile.size.toLocaleString()} bytes` : "文件内容将在下载包中提供"}
        </div>
      )}
    </div>
  );
}

export function SkillCandidatePane({
  label,
  jobId,
  candidate,
  selected,
  publishing,
  publishDisabled,
  publishError,
  onSelect,
  onPublish,
}: SkillCandidatePaneProps) {
  const [view, setView] = useState<"conversation" | "preview">("conversation");
  const [publishOpen, setPublishOpen] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState("");
  const [skillSpaces, setSkillSpaces] = useState("");
  const [projectName, setProjectName] = useState("");
  const [skillId, setSkillId] = useState("");
  const previewButtonRef = useRef<HTMLButtonElement>(null);
  const backButtonRef = useRef<HTMLButtonElement>(null);
  const running = candidate.status === "queued" || candidate.status === "running";
  const succeeded = candidate.status === "succeeded";
  const validation = candidate.validation;

  return (
    <article
      className={`skill-candidate skill-candidate--${candidate.status}${selected ? " is-selected" : ""}`}
      aria-label={`${label} ${candidate.model}`}
    >
      <header className="skill-candidate__header">
        <h2>{candidate.model}</h2>
        {selected ? <span className="skill-candidate__selected">已选方案</span> : null}
      </header>

      {view === "conversation" ? (
        <div className="skill-candidate__view skill-candidate__view--conversation">
          <div className="skill-candidate__status" aria-live="polite">
            <span className="skill-candidate__status-icon"><StatusIcon status={candidate.status} /></span>
            {running ? (
              <TextShimmer duration={2.2} spread={16}>
                {STAGE_LABELS[candidate.stage]}
              </TextShimmer>
            ) : (
              <span>{STAGE_LABELS[candidate.stage]}</span>
            )}
            {candidate.durationMs !== undefined && succeeded ? (
              <span className="skill-candidate__duration">{(candidate.durationMs / 1000).toFixed(1)} 秒</span>
            ) : null}
          </div>

          <SkillConversationStream activities={candidate.activities} />

          {candidate.error ? <div className="skill-candidate__error">{candidate.error}</div> : null}

          {succeeded ? (
            <div className="skill-candidate__view-actions">
              <button
                ref={previewButtonRef}
                type="button"
                className="skill-action skill-action--preview"
                onClick={() => {
                  setView("preview");
                  requestAnimationFrame(() => backButtonRef.current?.focus());
                }}
              >
                <PreviewIcon />
                查看 Skill
              </button>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="skill-candidate__view skill-candidate__view--preview">
          <div className="skill-candidate__preview-nav">
            <button
              ref={backButtonRef}
              type="button"
              className="skill-candidate__back"
              onClick={() => {
                setView("conversation");
                requestAnimationFrame(() => previewButtonRef.current?.focus());
              }}
            >
              <BackIcon />
              返回对话
            </button>
          </div>
          <div className="skill-candidate__result">
            <div className="skill-candidate__summary">
              <div>
                <span>Skill</span>
                <strong>{candidate.name ?? "未命名 Skill"}</strong>
              </div>
              <div>
                <span>文件</span>
                <strong>{candidate.files.length}</strong>
              </div>
              <div>
                <span>校验</span>
                <strong className={validation?.valid === false ? "is-invalid" : "is-valid"}>
                  {validation?.valid === false ? "未通过" : "已通过"}
                </strong>
              </div>
            </div>
            {candidate.description ? (
              <p className="skill-candidate__description">{candidate.description}</p>
            ) : null}
            {validation && (validation.errors.length > 0 || validation.warnings.length > 0) ? (
              <details className="skill-validation">
                <summary>查看校验详情</summary>
                {[...validation.errors, ...validation.warnings].map((message, index) => (
                  <div key={`${message}-${index}`}>{message}</div>
                ))}
              </details>
            ) : null}
            <FilePreview candidate={candidate} />
            <div className="skill-candidate__actions">
              <button
                type="button"
                className="skill-action skill-action--select"
                aria-pressed={selected}
                onClick={onSelect}
              >
                {selected ? "已采用此方案" : "采用此方案"}
              </button>
              <button
                type="button"
                className="skill-action"
                disabled={downloading}
                onClick={() => {
                  setDownloading(true);
                  setDownloadError("");
                  void downloadSkillCandidate(jobId, candidate.id)
                    .catch((error) => {
                      setDownloadError(error instanceof Error ? error.message : String(error));
                    })
                    .finally(() => setDownloading(false));
                }}
              >
                {downloading ? "正在下载…" : "下载 ZIP"}
              </button>
              <button
                type="button"
                className="skill-action"
                disabled={!selected || publishing || publishDisabled || candidate.published}
                title={!selected ? "请先采用此方案" : undefined}
                onClick={() => setPublishOpen((open) => !open)}
              >
                {candidate.published
                  ? "已添加到 AgentKit"
                  : publishing
                    ? "正在添加…"
                    : "添加到 AgentKit"}
              </button>
            </div>
            {downloadError ? <div className="skill-candidate__error">{downloadError}</div> : null}
            {publishOpen && selected && !candidate.published ? (
              <form
                className="skill-publish-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  const skillSpaceIds = skillSpaces
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean);
                  onPublish({
                    skillSpaceIds,
                    ...(projectName.trim() ? { projectName: projectName.trim() } : {}),
                    ...(skillId.trim() ? { skillId: skillId.trim() } : {}),
                  });
                }}
              >
                <label>
                  <span>SkillSpace ID（可选）</span>
                  <input
                    value={skillSpaces}
                    onChange={(event) => setSkillSpaces(event.target.value)}
                    placeholder="多个 ID 用英文逗号分隔"
                  />
                </label>
                <div className="skill-publish-form__optional">
                  <label>
                    <span>项目名称（可选）</span>
                    <input
                      value={projectName}
                      onChange={(event) => setProjectName(event.target.value)}
                    />
                  </label>
                  <label>
                    <span>已有 Skill ID（可选）</span>
                    <input
                      value={skillId}
                      onChange={(event) => setSkillId(event.target.value)}
                    />
                  </label>
                </div>
                <button
                  type="submit"
                  className="skill-action skill-action--select"
                  disabled={publishing}
                >
                  {publishing ? "正在添加…" : "确认添加"}
                </button>
              </form>
            ) : null}
            {publishError ? <div className="skill-candidate__error">{publishError}</div> : null}
          </div>
        </div>
      )}
    </article>
  );
}
