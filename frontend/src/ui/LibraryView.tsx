import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  cloudRegionOptions,
  defaultCloudRegion,
  isSupportedCloudRegion,
  type CloudProvider,
  type CloudRegion,
} from "../adk/cloudProvider";
import { ArtifactLibrary } from "./ArtifactLibrary";
import {
  collectArtifactIngestCandidates,
  type ArtifactLibraryItem,
  type ArtifactSessionSource,
} from "./artifactLibraryModel";
import {
  deleteStoredArtifact,
  downloadStoredArtifact,
  syncStoredArtifacts,
  updateStoredArtifact,
} from "./artifactLibraryApi";
import { KnowledgeLibrary } from "./KnowledgeLibrary";
import {
  SkillCenterView,
  type SkillCenterWorkspaceLaunch,
} from "./SkillCenter";
import {
  ResourceFilterSelect,
  ResourcePageHeader,
  ResourcePageShell,
  ResourceTabs,
} from "./ResourceCollection";
import "./LibraryView.css";

export type LibraryTab = "skills" | "knowledge" | "artifacts";

const LIBRARY_TABS: ReadonlyArray<{ id: LibraryTab; label: string; panelId: string }> = [
  { id: "skills", label: "技能库", panelId: "library-skills-panel" },
  { id: "knowledge", label: "知识库", panelId: "library-knowledge-panel" },
  { id: "artifacts", label: "产物", panelId: "library-artifacts-panel" },
];

export interface LibraryViewProps {
  cloudProvider: CloudProvider;
  studioRegion?: string;
  activeTab: LibraryTab;
  onTabChange: (tab: LibraryTab) => void;
  onPageTitleChange?: (title: string) => void;
  skillInitialWorkspace?: SkillCenterWorkspaceLaunch | null;
  onSkillInitialWorkspaceConsumed?: () => void;
  artifactSources?: readonly ArtifactSessionSource[];
  artifactUserId?: string;
  onArtifactActivate?: () => void | Promise<void>;
  onArtifactSourceOpen?: (appName: string, sessionId: string) => void;
}

export function LibraryView({
  cloudProvider,
  studioRegion = "",
  activeTab,
  onTabChange,
  onPageTitleChange,
  skillInitialWorkspace = null,
  onSkillInitialWorkspaceConsumed,
  artifactSources = [],
  artifactUserId = "",
  onArtifactActivate,
  onArtifactSourceOpen,
}: LibraryViewProps) {
  const configuredRegion = isSupportedCloudRegion(studioRegion)
    ? studioRegion
    : defaultCloudRegion(cloudProvider);
  const [region, setRegion] = useState<CloudRegion>(configuredRegion);
  const [skillPageTitle, setSkillPageTitle] = useState("技能库");
  const [knowledgeDetailActive, setKnowledgeDetailActive] = useState(false);
  const [mountedTabs, setMountedTabs] = useState<ReadonlySet<LibraryTab>>(
    () => new Set<LibraryTab>(["skills", activeTab]),
  );
  const [activationRevisions, setActivationRevisions] = useState<
    Record<LibraryTab, number>
  >({ skills: 0, knowledge: 0, artifacts: 0 });
  const artifactActivateRef = useRef(onArtifactActivate);
  const [artifactItems, setArtifactItems] = useState<ArtifactLibraryItem[]>([]);
  const [artifactLoading, setArtifactLoading] = useState(false);
  const [artifactError, setArtifactError] = useState("");
  const artifactCandidateSnapshot = useMemo(() => {
    const candidates = collectArtifactIngestCandidates(artifactSources);
    return { key: JSON.stringify(candidates), candidates };
  }, [artifactSources]);
  const artifactCandidateCache = useRef(artifactCandidateSnapshot);
  if (artifactCandidateCache.current.key !== artifactCandidateSnapshot.key) {
    artifactCandidateCache.current = artifactCandidateSnapshot;
  }
  const artifactCandidates = artifactCandidateCache.current.candidates;
  const regionOptions = useMemo(() => cloudRegionOptions(cloudProvider), [cloudProvider]);

  useEffect(() => {
    setRegion(configuredRegion);
  }, [configuredRegion]);

  useEffect(() => {
    artifactActivateRef.current = onArtifactActivate;
  }, [onArtifactActivate]);

  useEffect(() => {
    setMountedTabs((current) => {
      if (current.has(activeTab)) return current;
      const next = new Set(current);
      next.add(activeTab);
      return next;
    });
  }, [activeTab]);

  useEffect(() => {
    const activeTitle = activeTab === "skills"
      ? skillPageTitle
      : LIBRARY_TABS.find((tab) => tab.id === activeTab)?.label || "资源库";
    onPageTitleChange?.(activeTitle);
  }, [activeTab, onPageTitleChange, skillPageTitle]);

  useEffect(() => {
    if (activeTab === "artifacts") {
      void artifactActivateRef.current?.();
    }
  }, [activeTab, activationRevisions.artifacts]);

  const loadArtifacts = useCallback(async () => {
    setArtifactLoading(true);
    setArtifactError("");
    try {
      setArtifactItems(await syncStoredArtifacts(artifactCandidates));
    } catch (reason) {
      setArtifactError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setArtifactLoading(false);
    }
  }, [artifactCandidates]);

  useEffect(() => {
    if (activeTab === "artifacts") void loadArtifacts();
  }, [activeTab, activationRevisions.artifacts, loadArtifacts]);

  const selectTab = (tab: LibraryTab) => {
    setMountedTabs((current) => {
      if (current.has(tab)) return current;
      const next = new Set(current);
      next.add(tab);
      return next;
    });
    setActivationRevisions((current) => ({
      ...current,
      [tab]: current[tab] + 1,
    }));
    onTabChange(tab);
  };

  const toolbarLeading = (
    <ResourceTabs
      idPrefix="library"
      ariaLabel="资源库分类"
      value={activeTab}
      items={LIBRARY_TABS}
      onChange={selectTab}
    />
  );
  const regionFilter = (id: string) => (
    <ResourceFilterSelect
      id={id}
      ariaLabel="区域"
      value={region}
      options={regionOptions}
      onChange={setRegion}
    />
  );
  const detailActive = activeTab === "skills"
    ? skillPageTitle !== "技能库"
    : activeTab === "knowledge" && knowledgeDetailActive;

  return (
    <ResourcePageShell className={`library-view${detailActive ? " is-detail" : ""}`} aria-label="资源库">
      {!detailActive ? (
        <ResourcePageHeader
          className="library-view__header"
          title="资源库"
        />
      ) : null}
      <div className="library-panels">
        {mountedTabs.has("skills") ? (
          <div
            id="library-skills-panel"
            className="library-panel"
            role="tabpanel"
            aria-labelledby="library-skills-tab"
            hidden={activeTab !== "skills"}
          >
            <SkillCenterView
              cloudProvider={cloudProvider}
              region={region}
              active={activeTab === "skills"}
              activationRevision={activationRevisions.skills}
              onPageTitleChange={setSkillPageTitle}
              initialWorkspace={skillInitialWorkspace}
              onInitialWorkspaceConsumed={onSkillInitialWorkspaceConsumed}
              toolbarLeading={toolbarLeading}
              toolbarFilters={regionFilter("library-skills-region-filter")}
            />
          </div>
        ) : null}
        {mountedTabs.has("knowledge") ? (
          <div
            id="library-knowledge-panel"
            className="library-panel"
            role="tabpanel"
            aria-labelledby="library-knowledge-tab"
            hidden={activeTab !== "knowledge"}
          >
            <KnowledgeLibrary
              cloudProvider={cloudProvider}
              region={region}
              active={activeTab === "knowledge"}
              activationRevision={activationRevisions.knowledge}
              onDetailChange={setKnowledgeDetailActive}
              toolbarLeading={toolbarLeading}
              toolbarFilters={regionFilter("library-knowledge-region-filter")}
            />
          </div>
        ) : null}
        {mountedTabs.has("artifacts") ? (
          <div
            id="library-artifacts-panel"
            className="library-panel"
            role="tabpanel"
            aria-labelledby="library-artifacts-tab"
            hidden={activeTab !== "artifacts"}
          >
            <ArtifactLibrary
              items={artifactItems}
              region={region}
              userId={artifactUserId}
              active={activeTab === "artifacts"}
              activationRevision={activationRevisions.artifacts}
              loading={artifactLoading}
              error={artifactError}
              onRetry={() => void loadArtifacts()}
              onEdit={updateStoredArtifact}
              onDelete={deleteStoredArtifact}
              onDownload={downloadStoredArtifact}
              onOpenSource={onArtifactSourceOpen
                ? (artifact) => onArtifactSourceOpen(artifact.appName, artifact.sessionId)
                : undefined}
              toolbarLeading={toolbarLeading}
              toolbarFilters={regionFilter("library-artifacts-region-filter")}
            />
          </div>
        ) : null}
      </div>
    </ResourcePageShell>
  );
}
