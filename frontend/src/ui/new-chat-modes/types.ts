import type {
  SkillSpaceRef,
  SkillSpaceSkill,
} from "../../create/skills/skillspace";

export type NewChatMode = "agent" | "temporary" | "deepseek-harness";

export type NewChatTask = "ppt" | "image" | "video";

export type NewChatWorkspaceMode = "agent" | "vibe" | "skill" | "video";

export type NewChatSkillAction = "create" | "optimize";

export interface NewChatSkillTarget {
  space: SkillSpaceRef;
  skill: SkillSpaceSkill;
}
