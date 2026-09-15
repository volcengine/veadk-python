import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { Block } from "../blocks";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import { ToolDisclosureIcon } from "../ui/builtin-tools/icons";
import { developmentProcessGroups, developmentToolLabel } from "./developmentPresentation";
import "./DevelopmentProcess.css";

function ProcessGroup({ blocks, active, status, render }: {
  blocks: Block[]; active: boolean; status: string; render: (blocks: Block[]) => ReactNode;
}) {
  const { t } = useTranslation("adk");
  const [open, setOpen] = useState(false);
  const running = [...blocks].reverse().find((block) => "done" in block && !block.done);
  const failures = blocks.filter((block) => block.kind === "tool" && block.status === "failed");
  const duration = blocks.reduce((sum, block) => sum + (block.durationMs || 0), 0);
  let title = t("developmentRuns.processSummary", { count: blocks.length });
  if (active) {
    title = status || (running?.kind === "thinking" ? t("developmentRuns.thinking")
      : running?.kind === "tool" ? developmentToolLabel(running)
      : running?.kind === "plan" ? t("developmentRuns.plan")
      : running?.kind === "diff" ? t("developmentRuns.diff") : t("developmentRuns.processing"));
  }
  return <section className="development-process">
    <button type="button" className="development-process__toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
      <ToolDisclosureIcon className={`tool-chevron${open ? " is-open" : ""}`} />
      {active ? <TextShimmer className="development-process__title" aria-live="polite">{title}</TextShimmer> : <span className="development-process__title">{title}</span>}
      {!active && duration > 0 && <span className="development-process__duration">{t("developmentRuns.duration", { seconds: (duration / 1000).toFixed(1) })}</span>}
    </button>
    {failures.length > 0 && <div className="development-process__failure">{t("developmentRuns.failedTools", { count: failures.length })} · {failures.map((block) => block.kind === "tool" ? developmentToolLabel(block) : "").join(" · ")}</div>}
    <div className="development-process__items" hidden={!open}>{render(blocks)}</div>
  </section>;
}
export function DevelopmentProcess({ blocks, active, status = "", render }: {
  blocks: Block[]; active: boolean; status?: string; render: (blocks: Block[]) => ReactNode;
}) {
  const { t } = useTranslation("adk");
  const groups = developmentProcessGroups(blocks);
  const last = groups[groups.length - 1];
  const progress = [...blocks].reverse().find((block) => block.kind === "progress");
  const liveStatus = status || (progress?.kind === "progress" ? progress.text : "");
  return <>
    {groups.map((group) => group.process
      ? <ProcessGroup key={group.id} blocks={group.blocks} active={active && group === last} status={liveStatus} render={render} />
      : <div key={group.id} data-assistant-phase={group.blocks[0].phase}>{render(group.blocks)}</div>)}
    {active && !last?.process && <div className="development-process__status" role="status"><TextShimmer>{liveStatus || t("developmentRuns.processing")}</TextShimmer></div>}
  </>;
}
