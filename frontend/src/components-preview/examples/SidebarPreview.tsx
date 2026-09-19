import { useState } from "react";

import { Sidebar, SidebarAgentIcon, SidebarGroupTitle, SidebarItem, SidebarItemWithIcon } from "../../components/composites/Sidebar";
import { Button } from "../../components/primitives/Button";
import { Menu } from "../../components/primitives/Menu";
import { EmptyState } from "../../components/primitives/EmptyState";
import { ToastProvider } from "../../components/primitives/Toast";
import { Drawer } from "../../components/composites/Drawer";
import { useSidebarPreviewState } from "./sidebarPreviewState";
import "./SidebarPreview.css";

function CompleteSidebarExample() {
  const [collapsed, setCollapsed] = useState(false);
  const { sidebar, provider, setProvider, state, setState, reset, notifications, setNotifications } = useSidebarPreviewState();

  return <section className="sidebar-preview-complete" aria-label="完整 Sidebar">
    <div className="sidebar-preview-controls">
      <Menu label={provider === "volcengine" ? "火山引擎" : "BytePlus"} items={[{ type: "radio-group", id: "provider", value: provider, onValueChange: setProvider,
        items: [{ id: "volcengine", label: "火山引擎" }, { id: "byteplus", label: "BytePlus" }] }]} />
      <Menu label="会话状态" items={[{ type: "radio-group", id: "state", value: state, onValueChange: setState,
        items: [{ id: "ready", label: "正常" }, { id: "loading", label: "加载中" }, { id: "empty", label: "空状态" }, { id: "error", label: "加载失败" }] }]} />
      <Button variant="link" onClick={() => { reset(); setCollapsed(false); }}>重置示例</Button>
    </div>
    <div className="sidebar-preview-frame">
      <Sidebar {...sidebar} collapsed={collapsed} onCollapsedChange={setCollapsed} />
    </div>
    <Drawer open={notifications} onOpenChange={setNotifications} title="通知"><EmptyState title="暂无新通知" description="新的通知会显示在这里" /></Drawer>
  </section>;
}

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
      <h2 data-preview-heading tabIndex={-1} id="sidebar-preview-title" className="component-preview-title">Complete Sidebar</h2>
      <ToastProvider><CompleteSidebarExample /></ToastProvider>
      <div className="sidebar-preview-examples">
        <section className="sidebar-preview-specimen" aria-labelledby="sidebar-preview-projects-title">
          <h2 data-preview-heading tabIndex={-1} id="sidebar-preview-default-title">Sidebar Item</h2>
          <SidebarGroupTitle id="sidebar-preview-projects-title">Projects</SidebarGroupTitle>
          <SidebarItem>Search</SidebarItem>
          <SidebarItem icon={<SidebarAgentIcon />}>Agents</SidebarItem>
        </section>
        <section aria-labelledby="sidebar-preview-hover-title">
          <h2 data-preview-heading tabIndex={-1} className="sidebar-preview-state-title" id="sidebar-preview-hover-title">Hover</h2>
          <SidebarItem icon={<SidebarAgentIcon />} data-state="hover">Agents</SidebarItem>
        </section>
        <section aria-labelledby="sidebar-preview-selected-title">
          <h2 data-preview-heading tabIndex={-1} className="sidebar-preview-state-title" id="sidebar-preview-selected-title">Selected</h2>
          <SidebarItem icon={<SidebarAgentIcon />} selected>Agents</SidebarItem>
        </section>
      </div>
      <section className="sidebar-preview-with-icon" aria-labelledby="sidebar-preview-with-icon-title">
        <h2 data-preview-heading tabIndex={-1} className="component-preview-title" id="sidebar-preview-with-icon-title">会话 Item with icon</h2>
        <div className="sidebar-preview-icon-specimen">
          <SidebarGroupTitle>Recent</SidebarGroupTitle>
          <SidebarItemWithIcon
            label="Agent tools"
            icon={<SidebarAgentIcon />}
            trailing={<Button variant="ghost" iconOnly hoverEffect="icon" aria-label="Agent tools 更多操作" onClick={() => setNotice("已打开 Agent tools 更多操作")} startIcon={<SidebarPreviewIcon name="more" />} />}
            onClick={() => setNotice("已打开 Agent tools")}
          />
          <SidebarItemWithIcon
            label="Improve resource search and model selection across the workspace"
            trailing={<SidebarPreviewIcon name={pinned ? "pin" : "check"} />}
            hoverTrailing={<>
              <Button variant="ghost" iconOnly hoverEffect="icon" aria-label={pinned ? "取消置顶" : "置顶"} aria-pressed={pinned} onClick={pinAction} startIcon={<SidebarPreviewIcon name="pin" />} />
              <Button variant="ghost" iconOnly hoverEffect="icon" aria-label="Resource search 更多操作" onClick={() => setNotice("已打开 Resource search 更多操作")} startIcon={<SidebarPreviewIcon name="more" />} />
            </>}
            onClick={() => setNotice("已打开 Resource search")}
          />
          <SidebarItemWithIcon
            label="Review the agent configuration, runtime settings and deployment details"
            icon={<SidebarAgentIcon />}
            trailing={<><SidebarPreviewIcon name="pin" /><SidebarPreviewIcon name="check" /></>}
            hoverTrailing={<>
              <Button variant="ghost" iconOnly hoverEffect="icon" aria-label="归档配置记录" onClick={() => setNotice("已归档配置记录")} startIcon={<SidebarPreviewIcon name="archive" />} />
              <Button variant="ghost" iconOnly hoverEffect="icon" aria-label="Agent configuration 更多操作" onClick={() => setNotice("已打开 Agent configuration 更多操作")} startIcon={<SidebarPreviewIcon name="more" />} />
            </>}
            onClick={() => setNotice("已打开 Agent configuration")}
          />
          <SidebarItemWithIcon label="Archived conversation" disabled trailing={<SidebarPreviewIcon name="archive" />} />
          <SidebarItemWithIcon label="Generating response" loading
            hoverTrailing={<Button variant="ghost" iconOnly hoverEffect="icon" aria-label="Generating response 更多操作" onClick={() => setNotice("已打开 Generating response 更多操作")} startIcon={<SidebarPreviewIcon name="more" />} />} />
        </div>
        <output className="sidebar-preview-action" aria-live="polite">{notice}</output>
      </section>
    </section>
  );
}
