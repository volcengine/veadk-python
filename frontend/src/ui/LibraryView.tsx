import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { CloudProvider } from "../adk/cloudProvider";
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
import "./AgentWorkspace.css";
import "./LibraryView.css";

export type LibraryTab = "skills" | "knowledge" | "artifacts";

const LIBRARY_TABS: ReadonlyArray<{ id: LibraryTab; label: string }> = [
  { id: "skills", label: "技能库" },
  { id: "knowledge", label: "知识库" },
  { id: "artifacts", label: "产物" },
];

export interface LibraryViewProps {
  cloudProvider: CloudProvider;
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
  const [skillPageTitle, setSkillPageTitle] = useState("技能库");
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

  const handleTabKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    tab: LibraryTab,
  ) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      return;
    }
    event.preventDefault();
    const currentIndex = LIBRARY_TABS.findIndex((item) => item.id === tab);
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? LIBRARY_TABS.length - 1
        : (currentIndex + (event.key === "ArrowRight" ? 1 : -1) + LIBRARY_TABS.length)
          % LIBRARY_TABS.length;
    const nextTab = LIBRARY_TABS[nextIndex];
    selectTab(nextTab.id);
    document.getElementById(`library-${nextTab.id}-tab`)?.focus();
  };

  return (
    <section className="library-view" aria-label="资源库">
      <header className="library-view__header">
        <h1>资源库</h1>
        <p>管理您的资源和产物</p>
      </header>
      <nav className="aw-agent-tabs library-tabs" aria-label="资源库分类" role="tablist">
        {LIBRARY_TABS.map((tab) => (
          <button
            type="button"
            key={tab.id}
            id={`library-${tab.id}-tab`}
            className={activeTab === tab.id ? "is-active" : ""}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`library-${tab.id}-panel`}
            tabIndex={activeTab === tab.id ? 0 : -1}
            onClick={() => selectTab(tab.id)}
            onKeyDown={(event) => handleTabKeyDown(event, tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

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
              active={activeTab === "skills"}
              activationRevision={activationRevisions.skills}
              onPageTitleChange={setSkillPageTitle}
              initialWorkspace={skillInitialWorkspace}
              onInitialWorkspaceConsumed={onSkillInitialWorkspaceConsumed}
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
              active={activeTab === "knowledge"}
              activationRevision={activationRevisions.knowledge}
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
            />
          </div>
        ) : null}
      </div>
    </section>
  );
}
