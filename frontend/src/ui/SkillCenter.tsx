const SKILL_URL = "https://findskill.com/";

/** Hand-drawn "skill center" mark: a compass rose (discover skills) in a ring. */
function SkillCenterIcon() {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="12" cy="12" r="8.6" />
      <path
        d="M12 6.4 13.25 10.75 17.6 12 13.25 13.25 12 17.6 10.75 13.25 6.4 12 10.75 10.75z"
        fill="currentColor"
        stroke="none"
      />
    </svg>
  );
}

/** Sidebar entry that opens the skill center view in the main panel. */
export function SkillCenterButton({ onClick }: { onClick: () => void }) {
  return (
    <button className="new-chat" onClick={onClick}>
      <SkillCenterIcon />
      技能中心
    </button>
  );
}

/** Full-panel embed of the external skill center. */
export function SkillCenterView() {
  return <iframe className="skill-frame" src={SKILL_URL} title="技能中心" />;
}
