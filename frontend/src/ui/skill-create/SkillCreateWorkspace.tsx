import { useEffect, useState } from "react";
import { getSkillJob, publishSkillCandidate } from "./api";
import { SkillCandidatePane } from "./SkillCandidatePane";
import {
  SKILL_MODELS,
  type PublishSkillOptions,
  type SkillCandidate,
  type SkillCreationJob,
} from "./types";
import "./skill-create.css";

const TERMINAL = new Set(["completed"]);

export interface SkillCreateWorkspaceProps {
  initialJob: SkillCreationJob;
  onStartOver: () => void;
}

function placeholderCandidate(model: string, index: number): SkillCandidate {
  return {
    id: `pending-${index}`,
    model,
    modelLabel: model,
    status: "queued",
    stage: "provisioning",
    files: [],
  };
}

export function SkillCreateWorkspace({ initialJob, onStartOver }: SkillCreateWorkspaceProps) {
  const [job, setJob] = useState(initialJob);
  const [pollError, setPollError] = useState("");
  const [selectedId, setSelectedId] = useState<string>();
  const [publishingId, setPublishingId] = useState<string>();
  const [publishedIds, setPublishedIds] = useState<Set<string>>(() => new Set());
  const [publishErrors, setPublishErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (TERMINAL.has(initialJob.status)) return;
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const updated = await getSkillJob(initialJob.id);
        if (!cancelled) {
          setJob({ ...updated, prompt: updated.prompt || initialJob.prompt });
          setPollError("");
          if (!TERMINAL.has(updated.status)) timer = window.setTimeout(poll, 1100);
        }
      } catch (error) {
        if (!cancelled) {
          setPollError(error instanceof Error ? error.message : String(error));
          timer = window.setTimeout(poll, 1100);
        }
      }
    };
    timer = window.setTimeout(poll, 1100);
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
        <div>
          <span className="skill-workspace__kicker">A/B Skill 创建</span>
          <h1>正在把需求变成可运行的 Skill</h1>
          <p>{job.prompt}</p>
        </div>
        <button type="button" className="skill-workspace__restart" onClick={onStartOver}>
          重新创建
        </button>
      </header>

      {pollError ? (
        <div className="skill-workspace__poll-error" role="alert">
          状态刷新失败：{pollError}。页面会继续重试。
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
