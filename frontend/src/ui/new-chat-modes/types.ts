import type {
  SkillSpaceRef,
  SkillSpaceSkill,
} from "../../create/skills/skillspace";

export type NewChatMode = "agent" | "temporary";

export type NewChatTask = "ppt" | "image" | "video";

export type NewChatWorkspaceMode = "agent" | "skill" | "video";

export type NewChatSkillAction = "create" | "optimize";

export interface NewChatSkillTarget {
  space: SkillSpaceRef;
  skill: SkillSpaceSkill;
}
