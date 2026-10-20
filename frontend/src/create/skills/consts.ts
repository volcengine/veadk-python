import definitions from "../../../server/skills/consts.json";

export const STUDIO_SHARE_SPACE_NAME = definitions.share.name;
export const STUDIO_REVIEW_SPACE_NAME = definitions.review.name;
export const RESERVED_SKILL_SPACE_NAMES: readonly string[] = [
  STUDIO_SHARE_SPACE_NAME,
  STUDIO_REVIEW_SPACE_NAME,
];

export function isReservedSkillSpaceName(name: string): boolean {
  return RESERVED_SKILL_SPACE_NAMES.includes(name.trim().toLowerCase());
}

export function isReviewSkillSpace(space: { name: string }): boolean {
  return space.name === STUDIO_REVIEW_SPACE_NAME;
}
