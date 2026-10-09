import { useEffect, useState } from "react";
import type { AgentInfo, AgentSkill } from "../../adk/client";
import { SkillManagementApiError } from "../../adk/skills";
import { listSkillsInSpacePage } from "../../create/skills/skillspace";
import { SkillDocumentEditor } from "./SkillDocumentEditor";
import type { SkillDocumentTarget } from "../../adk/skillDocuments";
import { AgentInfoPanel, type AgentInfoPanelProps } from "../AgentTopology";

export interface BoundSkill extends AgentSkill {
  spaceId: string;
  region: string;
  skillId: string;
  version: string;
  lookupByName?: boolean;
}

export interface BoundSkillState {
  skills: BoundSkill[];
  loading: boolean;
  complete: boolean;
  error?: "error" | "forbidden" | "unsupported" | "degraded";
}

export function MpaAgentInfoRail(props: AgentInfoPanelProps) {
  if (props.info?.agentCategory !== "mpa") return null;
  const metadata = props.info.mpa;
  const identity = JSON.stringify([
    metadata?.skillSpacesStatus,
    metadata?.skillSpaces,
  ]);
  return <MpaRail key={identity} {...props} info={props.info} />;
}

function MpaRail(props: AgentInfoPanelProps & { info: AgentInfo }) {
  const [selected, setSelected] = useState<SkillDocumentTarget | null>(null);
  const [reload, setReload] = useState(0);
  const [state, setState] = useState<BoundSkillState>({
    skills: [],
    loading: true,
    complete: false,
  });
  const metadata = props.info.mpa;
  useEffect(() => {
    const controller = new AbortController();
    if (metadata?.skillSpacesStatus !== "ready") {
      setState({
        skills: [],
        loading: false,
        complete: false,
        error: metadata?.skillSpacesStatus ?? "unsupported",
      });
      return () => controller.abort();
    }
    setState((current) => ({ ...current, loading: true, error: undefined }));
    const collected = new Map<string, BoundSkill>();
    void (async () => {
      let degraded = false;
      for (const space of metadata.skillSpaces) {
        let scanned = 0;
        for (let page = 1; ; page++) {
          if (page > 100) throw new Error("Skill pagination limit reached");
          const result = await listSkillsInSpacePage(space.id, {
            region: space.region,
            page,
            pageSize: 100,
            signal: controller.signal,
          });
          if (controller.signal.aborted) return;
          if (
            !Array.isArray(result.items) ||
            !Number.isInteger(result.totalCount) ||
            result.totalCount < 0
          ) {
            throw new Error("Invalid SkillSpace page");
          }
          const previousSize = collected.size;
          for (const skill of result.items) {
            if (typeof skill.skillName !== "string" || !skill.skillName.trim())
              throw new Error("Invalid skill name");
            collected.set(
              `${space.region}:${space.id}:${skill.skillId || skill.skillName}`,
              {
                spaceId: space.id,
                region: space.region,
                skillId: skill.skillId,
                version: skill.version,
                lookupByName: skill.lookupByName,
                name: skill.skillName,
                description: skill.skillDescription || "",
              },
            );
          }
          scanned += result.items.length;
          degraded ||= result.degraded === true;
          setState({
            skills: [...collected.values()],
            loading: true,
            complete: false,
          });
          if (scanned >= result.totalCount) break;
          if (!result.items.length || collected.size === previousSize)
            throw new Error("Skill pagination made no progress");
        }
      }
      if (!controller.signal.aborted)
        setState({
          skills: [...collected.values()],
          loading: false,
          complete: !degraded,
          error: degraded ? "degraded" : undefined,
        });
    })().catch((error: unknown) => {
      if (controller.signal.aborted) return;
      const forbidden =
        error instanceof SkillManagementApiError &&
        [401, 403].includes(error.status);
      setState((current) => ({
        skills: forbidden
          ? []
          : collected.size
            ? [...collected.values()]
            : current.skills,
        loading: false,
        complete: false,
        error: forbidden ? "forbidden" : "error",
      }));
    });
    return () => controller.abort();
  }, [metadata, reload]);

  return (
    <>
      <AgentInfoPanel
        {...props}
        boundSkills={state}
        onOpenSkill={(index) => setSelected(state.skills[index])}
        onRefresh={() => {
          if (props.onRefresh) props.onRefresh();
          else setReload((value) => value + 1);
        }}
      />
      {selected && (
        <SkillDocumentEditor
          target={selected}
          onClose={() => setSelected(null)}
          onSaved={() => setReload((value) => value + 1)}
        />
      )}
    </>
  );
}
