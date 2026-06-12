import { useState } from "react";
import { MoreHorizontal, Plus, Trash2 } from "lucide-react";
import type { AdkSession } from "../adk/client";
import { sessionTitle } from "../blocks";
import { SkillCenterButton } from "./SkillCenter";
import { SearchButton } from "./Search";
import volcengineLogo from "../assets/volcengine.svg";

/** Hand-drawn "quick create" mark: a lightning bolt (speed) with a spark. */
function QuickCreateIcon() {
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
      <path d="M12.5 3 5.5 13h5l-1 8 8-11h-5l.5-7z" fill="currentColor" stroke="none" />
      <path d="M19 4.5v3M17.5 6h3" opacity="0.85" />
    </svg>
  );
}

export interface SidebarProps {
  sessions: AdkSession[];
  currentSessionId: string;
  onNewChat: () => void;
  onSearch: () => void;
  onQuickCreate: () => void;
  onSkillCenter: () => void;
  onAddAgent: () => void;
  onPickSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
}

export function Sidebar({
  sessions,
  currentSessionId,
  onNewChat,
  onSearch,
  onQuickCreate,
  onSkillCenter,
  onAddAgent,
  onPickSession,
  onDeleteSession,
}: SidebarProps) {
  // onAddAgent is now reached through the "添加 Agent" chooser, not a direct
  // sidebar button; kept in the props contract for the App-level handler.
  void onAddAgent;
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const sorted = [...sessions].sort(
    (a, b) => (b.lastUpdateTime ?? 0) - (a.lastUpdateTime ?? 0),
  );
  return (
    <aside className="sidebar">
      <div className="sidebar-top">
        <div className="brand">
          <img className="brand-logo" src={volcengineLogo} alt="" aria-hidden />
          VeADK
        </div>
        <button className="new-chat" onClick={onNewChat}>
          <Plus className="icon" />
          新会话
        </button>
        <SearchButton onClick={onSearch} />
        <button className="new-chat" onClick={onQuickCreate}>
          <QuickCreateIcon />
          添加 Agent
        </button>
        <SkillCenterButton onClick={onSkillCenter} />
      </div>

      <div className="sidebar-history">
        <div className="history-head">
          <span>历史会话</span>
        </div>
        <div className="history-list">
          {sorted.length === 0 && (
            <div className="history-empty">暂无会话</div>
          )}
          {sorted.map((s) => (
            <div
              key={s.id}
              className={`history-item ${s.id === currentSessionId ? "active" : ""}`}
            >
              <button
                className="history-item-btn"
                onClick={() => onPickSession(s.id)}
                title={s.id}
              >
                <span className="history-title">{sessionTitle(s.events)}</span>
              </button>
              <button
                className="history-more"
                title="更多"
                onClick={() => setMenuFor((m) => (m === s.id ? null : s.id))}
              >
                <MoreHorizontal className="icon" />
              </button>
              {menuFor === s.id && (
                <>
                  <div className="menu-scrim" onClick={() => setMenuFor(null)} />
                  <div className="history-menu">
                    <button
                      className="menu-item menu-item--danger"
                      onClick={() => {
                        setMenuFor(null);
                        onDeleteSession(s.id);
                      }}
                    >
                      <Trash2 className="icon" /> 删除
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
