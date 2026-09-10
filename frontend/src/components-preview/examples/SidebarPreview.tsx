import { SidebarAgentIcon, SidebarGroupTitle, SidebarItem } from "../../components/composites/Sidebar";
import "./SidebarPreview.css";

export function SidebarPreview() {
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
    </section>
  );
}
