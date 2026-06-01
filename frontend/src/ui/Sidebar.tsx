import { useState } from "react";
import { Loader2, MoreHorizontal, Plus, RefreshCw, Trash2 } from "lucide-react";
import type { AdkSession } from "../adk/client";
import { sessionTitle } from "../blocks";

export interface SidebarProps {
  apps: string[];
  appName: string;
  onAppChange: (app: string) => void;
  sessions: AdkSession[];
  currentSessionId: string;
  onNewChat: () => void;
  onPickSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onRefresh: () => void;
  loadingSessions: boolean;
}

export function Sidebar({
  apps,
  appName,
  onAppChange,
  sessions,
  currentSessionId,
  onNewChat,
  onPickSession,
  onDeleteSession,
  onRefresh,
  loadingSessions,
}: SidebarProps) {
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const sorted = [...sessions].sort(
    (a, b) => (b.lastUpdateTime ?? 0) - (a.lastUpdateTime ?? 0),
  );
  return (
    <aside className="sidebar">
      <div className="sidebar-top">
        <div className="brand">VeADK Web</div>
        <button className="new-chat" onClick={onNewChat}>
          <Plus className="icon" />
          新会话
        </button>
        <select
          className="agent-select"
          value={appName}
          onChange={(e) => onAppChange(e.target.value)}
        >
          {apps.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
      </div>

      <div className="sidebar-history">
        <div className="history-head">
          <span>历史会话</span>
          <button className="history-refresh" onClick={onRefresh} title="刷新">
            {loadingSessions ? (
              <Loader2 className="icon spin" />
            ) : (
              <RefreshCw className="icon" />
            )}
          </button>
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
