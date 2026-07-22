import { useEffect, useState } from "react";
import {
  getSkillJob,
  publishSkillCandidate,
  SkillCreatorApiError,
} from "./api";
import { SkillCandidatePane } from "./SkillCandidatePane";
import {
  SKILL_MODELS,
  type PublishSkillOptions,
  type SkillCandidate,
  type SkillCreationJob,
} from "./types";
import "./skill-create.css";

const TERMINAL = new Set(["completed"]);
const POLL_INTERVAL_MS = 1_100;
const NOT_FOUND_GRACE_MS = 30_000;

export interface SkillCreateWorkspaceProps {
  initialJob: SkillCreationJob;
}

function placeholderCandidate(model: string, index: number): SkillCandidate {
  return {
    id: `pending-${index}`,
    model,
    modelLabel: model,
    status: "queued",
    stage: "provisioning",
    files: [],
    activities: [{
      id: "provisioning",
      kind: "status",
      text: "正在拉起 Sandbox",
      status: "running",
    }],
  };
}

export function SkillCreateWorkspace({ initialJob }: SkillCreateWorkspaceProps) {
  const [job, setJob] = useState(initialJob);
  const [pollError, setPollError] = useState("");
  const [pollingStopped, setPollingStopped] = useState(false);
  const [selectedId, setSelectedId] = useState<string>();
  const [publishingId, setPublishingId] = useState<string>();
  const [publishedIds, setPublishedIds] = useState<Set<string>>(() => new Set());
  const [publishErrors, setPublishErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    setJob(initialJob);
    setPollError("");
    setPollingStopped(false);
  }, [initialJob]);

  useEffect(() => {
    if (
      TERMINAL.has(initialJob.status) ||
      initialJob.id.startsWith("pending-")
    ) return;
    let cancelled = false;
    let timer: number | undefined;
    const notFoundDeadline = Date.now() + NOT_FOUND_GRACE_MS;
    const poll = async () => {
      try {
        const updated = await getSkillJob(initialJob.id);
        if (!cancelled) {
          setJob({ ...updated, prompt: updated.prompt || initialJob.prompt });
          setPollError("");
          if (!TERMINAL.has(updated.status)) {
            timer = window.setTimeout(poll, POLL_INTERVAL_MS);
          }
        }
      } catch (error) {
        if (!cancelled) {
          const apiError = error instanceof SkillCreatorApiError ? error : undefined;
          const awaitingSession =
            apiError?.status === 404 && Date.now() < notFoundDeadline;
          if (awaitingSession) {
            setPollError("");
            setPollingStopped(false);
            timer = window.setTimeout(poll, POLL_INTERVAL_MS);
            return;
          }
          const unavailable = apiError?.status === 403 || apiError?.status === 404;
          setPollError(
            apiError?.status === 403
              ? "当前标签页的登录身份与此任务不一致，请重新创建 Skill"
              : error instanceof Error ? error.message : String(error),
          );
          setPollingStopped(unavailable);
          if (!unavailable) timer = window.setTimeout(poll, POLL_INTERVAL_MS);
        }
      }
    };
    timer = window.setTimeout(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [initialJob.id, initialJob.status]);

  const candidates = SKILL_MODELS.map((model, index) =>
    job.candidates.find((candidate) => candidate.model === model) ??
      job.candidates[index] ??
      placeholderCandidate(model, index),
  );

  async function publish(candidate: SkillCandidate, options: PublishSkillOptions) {
    setPublishingId(candidate.id);
    setPublishErrors((current) => ({ ...current, [candidate.id]: "" }));
    try {
      await publishSkillCandidate(job.id, candidate.id, options);
      setPublishedIds((current) => new Set(current).add(candidate.id));
    } catch (error) {
      setPublishErrors((current) => ({
        ...current,
        [candidate.id]: error instanceof Error ? error.message : String(error),
      }));
    } finally {
      setPublishingId(undefined);
    }
  }

  return (
    <section className="skill-workspace">
      <header className="skill-workspace__intro">
        <h1>正在把需求变成可运行的 Skill</h1>
      </header>

      {pollError ? (
        <div className="skill-workspace__poll-error" role="alert">
          状态刷新失败：{pollError}。{pollingStopped ? "" : "页面会继续重试。"}
        </div>
      ) : null}

      <div className="skill-workspace__grid">
        {candidates.map((candidate, index) => {
          const published = publishedIds.has(candidate.id) || candidate.published;
          const view = published ? { ...candidate, published: true } : candidate;
          return (
            <SkillCandidatePane
              key={`${candidate.model}-${candidate.id}`}
              label={`方案 ${index === 0 ? "A" : "B"}`}
              jobId={job.id}
              candidate={view}
              selected={selectedId === candidate.id}
              publishing={publishingId === candidate.id}
              publishDisabled={publishingId !== undefined && publishingId !== candidate.id}
              publishError={publishErrors[candidate.id]}
              onSelect={() => setSelectedId(candidate.id)}
              onPublish={(options) => void publish(candidate, options)}
            />
          );
        })}
      </div>
    </section>
  );
}
