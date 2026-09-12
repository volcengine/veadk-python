import { useState } from "react";
import { ComponentApi } from "../api/ComponentApi";
import { SidebarAgentIcon, SidebarGroupTitle, SidebarItem, SidebarItemWithIcon } from "../../components/composites/Sidebar";
import "./SidebarPreview.css";

function SidebarPreviewIcon({ name }: { name: "pin" | "check" | "more" | "archive" }) {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.33333" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {name === "pin" && <path d="M6 2h4l-.5 4L12 8v1H4V8l2.5-2L6 2ZM8 9v5" />}
    {name === "check" && <path d="m3 8 3 3 7-7" />}
    {name === "more" && <><circle cx="3" cy="8" r=".7" fill="currentColor" /><circle cx="8" cy="8" r=".7" fill="currentColor" /><circle cx="13" cy="8" r=".7" fill="currentColor" /></>}
    {name === "archive" && <><path d="M3 6v7h10V6M6 9h4" /><rect x="2" y="3" width="12" height="3" rx="1" /></>}
  </svg>;
}

export function SidebarPreview() {
  const [pinned, setPinned] = useState(false);
  const [notice, setNotice] = useState("");
  const pinAction = () => {
    setPinned(value => !value);
    setNotice(pinned ? "已取消置顶" : "已置顶");
  };

  return (
    <section aria-labelledby="sidebar-preview-title">
      <h2 id="sidebar-preview-title" className="component-preview-title">Sidebar</h2>
      <div className="sidebar-preview-examples">
        <section className="sidebar-preview-specimen" aria-labelledby="sidebar-preview-projects-title">
          <SidebarGroupTitle id="sidebar-preview-projects-title">Projects</SidebarGroupTitle>
          <SidebarItem>Search</SidebarItem>
          <SidebarItem icon={<SidebarAgentIcon />}>Agents</SidebarItem>
        </section>
        <section aria-labelledby="sidebar-preview-hover-title">
          <h3 className="sidebar-preview-state-title" id="sidebar-preview-hover-title">Hover</h3>
          <SidebarItem icon={<SidebarAgentIcon />} data-state="hover">Agents</SidebarItem>
        </section>
      </div>
      <section className="sidebar-preview-with-icon" aria-labelledby="sidebar-preview-with-icon-title">
        <h3 className="component-preview-title" id="sidebar-preview-with-icon-title">会话 Item with icon</h3>
        <div className="sidebar-preview-icon-specimen">
          <SidebarGroupTitle>Recent</SidebarGroupTitle>
          <SidebarItemWithIcon
            label="Agent tools"
            icon={<SidebarAgentIcon />}
            trailing={<button type="button" aria-label="Agent tools 更多操作" onClick={() => setNotice("已打开 Agent tools 更多操作")}><SidebarPreviewIcon name="more" /></button>}
            onClick={() => setNotice("已打开 Agent tools")}
          />
          <SidebarItemWithIcon
            label="Improve resource search and model selection across the workspace"
            trailing={<SidebarPreviewIcon name={pinned ? "pin" : "check"} />}
            hoverTrailing={<>
              <button type="button" aria-label={pinned ? "取消置顶" : "置顶"} aria-pressed={pinned} onClick={pinAction}><SidebarPreviewIcon name="pin" /></button>
              <button type="button" aria-label="Resource search 更多操作" onClick={() => setNotice("已打开 Resource search 更多操作")}><SidebarPreviewIcon name="more" /></button>
            </>}
            onClick={() => setNotice("已打开 Resource search")}
          />
          <SidebarItemWithIcon
            label="Review the agent configuration, runtime settings and deployment details"
            icon={<SidebarAgentIcon />}
            trailing={<><SidebarPreviewIcon name="pin" /><SidebarPreviewIcon name="check" /></>}
            hoverTrailing={<>
              <button type="button" aria-label="归档配置记录" onClick={() => setNotice("已归档配置记录")}><SidebarPreviewIcon name="archive" /></button>
              <button type="button" aria-label="Agent configuration 更多操作" onClick={() => setNotice("已打开 Agent configuration 更多操作")}><SidebarPreviewIcon name="more" /></button>
            </>}
            onClick={() => setNotice("已打开 Agent configuration")}
          />
          <SidebarItemWithIcon label="Archived conversation" disabled trailing={<SidebarPreviewIcon name="archive" />} />
        </div>
        <output className="sidebar-preview-action" aria-live="polite">{notice}</output>
      </section>
      <ComponentApi names={["SidebarGroupTitle", "SidebarItem", "SidebarItemWithIcon"]} />
    </section>
  );
}
