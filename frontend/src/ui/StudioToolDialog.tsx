import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { StudioBffTool } from "../adk/client";
import { BUILTIN_TOOLS } from "../create/veadkCatalog";
import { ToolCapabilityIcon } from "./CapabilityIcons";

const STUDIO_TOOL_LABELS: Record<string, string> = {
  coding: "智能编程",
  get_city_weather: "城市天气查询",
  get_location_weather: "位置天气查询",
  web_fetch: "网页内容获取",
};

export function studioToolLabel(name: string): string {
  const catalogTool = BUILTIN_TOOLS.find(
    (tool) => tool.id === name || tool.toolNames.includes(name),
  );
  return STUDIO_TOOL_LABELS[name] ?? catalogTool?.label ?? name;
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m7 7 10 10M17 7 7 17" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="10.8" cy="10.8" r="5.8" stroke="currentColor" strokeWidth="1.7" />
      <path d="m15.2 15.2 4 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function StudioToolDialog({
  agentName,
  tools,
  selectedIds,
  loading,
  disabled,
  unavailableReason,
  onChange,
  onClose,
}: {
  agentName: string;
  tools: StudioBffTool[];
  selectedIds: readonly string[];
  loading: boolean;
  disabled: boolean;
  unavailableReason?: string;
  onChange: (selectedIds: string[]) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const selected = useMemo(() => new Set(selectedIds), [selectedIds]);
  const titleId = useRef(`studio-tool-${Math.random().toString(36).slice(2)}`);
  const filteredTools = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return tools;
    return tools.filter((tool) =>
      `${tool.name} ${tool.id} ${tool.description}`.toLowerCase().includes(normalized),
    );
  }, [query, tools]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  const toggle = (toolId: string) => {
    const next = new Set(selected);
    if (next.has(toolId)) next.delete(toolId);
    else next.add(toolId);
    onChange([...next]);
  };

  return createPortal(
    <div className="studio-tool-dialog-layer">
      <button
        type="button"
        className="studio-tool-dialog-scrim"
        aria-label="关闭弹窗"
        onClick={onClose}
      />
      <section
        className="studio-tool-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId.current}
      >
        <header className="studio-tool-dialog-head">
          <span className="studio-tool-dialog-mark"><ToolCapabilityIcon /></span>
          <div>
            <h2 id={titleId.current}>添加 Studio 工具</h2>
            <p>由 Studio BFF 为 {agentName} 的当前会话执行，Runtime 无需预装</p>
          </div>
          <button
            type="button"
            className="studio-tool-dialog-close"
            aria-label="关闭添加 Studio 工具"
            onClick={onClose}
          >
            <CloseIcon />
          </button>
        </header>
        <div className="studio-tool-dialog-body">
          <label className="studio-tool-search">
            <SearchIcon />
            <input
              value={query}
              aria-label="搜索 Studio 工具"
              placeholder="搜索中文名称或工具标识"
              autoFocus
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <div className="studio-tool-picker" role="list" aria-label="可用 Studio 工具">
            {loading ? (
              <div className="studio-tool-empty">正在读取 Studio 工具…</div>
            ) : unavailableReason ? (
              <div className="studio-tool-empty">{unavailableReason}</div>
            ) : filteredTools.length === 0 ? (
              <div className="studio-tool-empty">没有匹配的 Studio 工具</div>
            ) : (
              filteredTools.map((tool) => {
                const active = selected.has(tool.id);
                return (
                  <article key={tool.id} className="studio-tool-option" role="listitem">
                    <span className="studio-tool-option-icon"><ToolCapabilityIcon /></span>
                    <span className="studio-tool-option-copy">
                      <strong>{tool.name || studioToolLabel(tool.id)}</strong>
                      <code>{tool.id}</code>
                      <span>{tool.description}</span>
                    </span>
                    <button
                      type="button"
                      disabled={disabled}
                      aria-pressed={active}
                      onClick={() => toggle(tool.id)}
                    >
                      {active ? "移除" : "添加"}
                    </button>
                  </article>
                );
              })
            )}
          </div>
        </div>
      </section>
    </div>,
    document.body,
  );
}
