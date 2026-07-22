import { InsightIcon } from "./icons/InsightIcon";
import "./SandboxSession.css";

export interface SandboxEntryButtonProps {
  variant: "composer" | "header";
  active?: boolean;
  onClick: () => void;
}

export function SandboxEntryButton({
  variant,
  active = false,
  onClick,
}: SandboxEntryButtonProps) {
  return (
    <button
      type="button"
      className={`sandbox-entry sandbox-entry--${variant}${active ? " is-active" : ""}`}
      onClick={onClick}
      disabled={active}
      aria-label={active ? "灵光一现临时会话已开启" : "开启灵光一现临时会话"}
    >
      <InsightIcon />
      <span>{active ? "临时会话中" : "灵光一现"}</span>
    </button>
  );
}

export function SandboxSessionWarning({ onExit }: { onExit: () => void }) {
  return (
    <div className="sandbox-session-warning" role="status">
      <span className="sandbox-session-warning-dot" aria-hidden="true" />
      <span className="sandbox-session-warning-copy">
        当前为临时会话，退出后对话内容消失
      </span>
      <button type="button" onClick={onExit}>
        退出临时会话
      </button>
    </div>
  );
}
