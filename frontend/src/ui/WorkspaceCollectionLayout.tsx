import { useTranslation } from "react-i18next";
import type { ReactNode } from "react";
import { ResourcePageShell, ResourcePageHeader, ResourceToolbar, ResourceTabs } from "./ResourceCollection";
import "./WorkspaceCenter.css";

export function WorkspaceCollectionLayout({ section, onWorkspace, onEnvironment, onProjects, actions, children, className = "" }: {
  section: "workspaces" | "environments" | "projects";
  onWorkspace?: () => void; onEnvironment?: () => void; onProjects?: () => void;
  actions: ReactNode; children: ReactNode; className?: string;
}) {
  const { t } = useTranslation("ui");
  const title = section === "workspaces" ? t("workspace.title") : section === "environments" ? t("common.environment") : t("workspace.codeProjects");
  return <ResourcePageShell className={`workspace-center ${className}`} aria-label={title}>
    <ResourcePageHeader title={title} />
    <ResourceToolbar>
      {(onWorkspace || onEnvironment) && <ResourceTabs
        items={[{ id: "workspaces", label: t("workspace.title") }, { id: "environments", label: t("common.environment") }, ...(onProjects ? [{ id: "projects", label: t("workspace.codeProjects") }] : [])]}
        value={section} onChange={value => {
          if (value === "workspaces") onWorkspace?.();
          if (value === "environments") onEnvironment?.();
          if (value === "projects") onProjects?.();
        }} ariaLabel={t("workspace.resourceType")} idPrefix="workspace-center" />}
      <div className="resource-toolbar__actions">{actions}</div>
    </ResourceToolbar>
    {children}
  </ResourcePageShell>;
}
