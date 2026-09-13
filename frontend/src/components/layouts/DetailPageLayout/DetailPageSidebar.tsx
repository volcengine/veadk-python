import { SidebarAgentIcon, SidebarGroupTitle, SidebarItem } from "../../composites/Sidebar";
import { PromoCard } from "../../composites/PromoCard";
import brand from "./assets/brand.svg";
import collapse from "./assets/collapse.svg";
import newTask from "./assets/new-task.svg";
import resources from "./assets/resources.svg";
import files from "./assets/files.svg";
import folder from "./assets/folder.svg";
import progress from "./assets/progress.svg";
import profile from "./assets/profile.png";
import bell from "./assets/bell.svg";

export function DetailPageSidebar() {
  const icon = (src: string) => <img src={src} alt="" />;
  return <div className="studio-detail-sidebar">
    <div className="studio-detail-sidebar__brand"><span><img src={brand} alt="" />AK Studio</span><button type="button" aria-label="Collapse sidebar"><img src={collapse} alt="" /></button></div>
    <nav className="studio-detail-sidebar__navigation" aria-label="Studio navigation">
      <div className="studio-detail-sidebar__items">
        <SidebarItem icon={icon(newTask)} className="studio-detail-sidebar__new-task">New task</SidebarItem>
        <SidebarItem>Search</SidebarItem>
        <SidebarItem icon={<SidebarAgentIcon />} data-state="hover" aria-current="page">Agents</SidebarItem>
        <SidebarItem icon={icon(resources)} className="studio-detail-sidebar__tracked">Resources</SidebarItem>
        <SidebarItem icon={icon(files)} className="studio-detail-sidebar__tracked">My files</SidebarItem>
      </div>
      <section><SidebarGroupTitle>Pinned</SidebarGroupTitle><SidebarItem icon={icon(folder)} className="studio-detail-sidebar__tracked">Studio design</SidebarItem></section>
      <section><SidebarGroupTitle>Projects</SidebarGroupTitle><div className="studio-detail-sidebar__items">
        <SidebarItem icon={icon(folder)} className="studio-detail-sidebar__tracked">ArkClaw</SidebarItem>
        <SidebarItem icon={icon(folder)} className="studio-detail-sidebar__tracked">AgentKit</SidebarItem>
        <div className="studio-detail-sidebar__task"><span>Optimize page layout</span><img src={progress} alt="In progress" /></div>
        <div className="studio-detail-sidebar__task"><span>Add Runtime info</span></div>
        <SidebarItem icon={icon(folder)} className="studio-detail-sidebar__tracked">Default project</SidebarItem>
      </div></section>
    </nav>
    <div className="studio-detail-sidebar__promo"><PromoCard /></div>
    <footer className="studio-detail-sidebar__footer"><div className="studio-detail-sidebar__user"><span><img src={profile} alt="" /></span>Chloe</div><div className="studio-detail-sidebar__account-actions"><button type="button" aria-label="Notifications"><img src={bell} alt="" /></button><button type="button" className="studio-detail-sidebar__update">Update</button></div></footer>
  </div>;
}
