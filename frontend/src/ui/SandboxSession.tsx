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
      aria-label={active ? "Codex 智能体会话已开启" : "开启 Codex 智能体会话"}
    >
      <InsightIcon />
      <span>{active ? "Codex 智能体会话中" : "灵光一现"}</span>
    </button>
  );
}

export function SandboxSessionWarning({ onExit }: { onExit: () => void }) {
  return (
    <div className="sandbox-session-warning" role="status">
      <span className="sandbox-session-warning-dot" aria-hidden="true" />
      <span className="sandbox-session-warning-copy">
        当前已连接 Codex 智能体，返回列表不会删除沙箱
      </span>
      <button type="button" onClick={onExit}>
        返回智能体列表
      </button>
    </div>
  );
}
