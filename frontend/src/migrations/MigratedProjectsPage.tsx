import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { IntelligentDevelopmentReleaseRef } from "../blocks";
import { IntelligentProjectLibrary } from "../create/IntelligentProjectLibrary";
import type {
  IntelligentCreateBaseVersion,
  IntelligentDevelopmentCapabilities,
  IntelligentPreparationStage,
} from "../create/IntelligentCreate";
import { IntelligentOptimizationDialog } from "./IntelligentOptimizationDialog";

interface MigratedProjectsPageProps {
  capabilities: IntelligentDevelopmentCapabilities | null;
  capabilitiesLoading: boolean;
  preparationStage: IntelligentPreparationStage | null;
  optimizationError: string;
  initialProjectId?: string;
  onOptimize: (
    goal: string,
    modelId: string,
    base: IntelligentCreateBaseVersion,
  ) => Promise<void>;
  onCancelOptimization: () => void;
  onDownload: (delivery: IntelligentDevelopmentReleaseRef) => Promise<void>;
  onDeploy: (delivery: IntelligentDevelopmentReleaseRef) => void;
}

export function MigratedProjectsPage({
  capabilities,
  capabilitiesLoading,
  preparationStage,
  optimizationError,
  initialProjectId,
  onOptimize,
  onCancelOptimization,
  onDownload,
  onDeploy,
}: MigratedProjectsPageProps) {
  const { t } = useTranslation("migrations");
  const [optimizationBase, setOptimizationBase] =
    useState<IntelligentCreateBaseVersion>();

  return (
    <>
      <main className="migration-main migration-projects-page">
        <header className="migration-main__header">
          <div>
            <h2>{t("projects.title")}</h2>
            <p>{t("projects.description")}</p>
          </div>
        </header>
        <div className="migration-projects-page__content">
          <IntelligentProjectLibrary
            origin="migration"
            title={t("projects.libraryTitle")}
            description={t("projects.libraryDescription")}
            emptyTitle={t("projects.emptyTitle")}
            emptyDescription={t("projects.emptyDescription")}
            capabilities={capabilities}
            capabilitiesLoading={capabilitiesLoading}
            creating={preparationStage !== null}
            initialProjectId={initialProjectId}
            onSelectBaseVersion={setOptimizationBase}
            onClearBaseVersion={() => undefined}
            onDownload={onDownload}
            onDeploy={onDeploy}
          />
        </div>
      </main>
      {optimizationBase ? (
        <IntelligentOptimizationDialog
          baseVersion={optimizationBase}
          capabilities={capabilities}
          loading={capabilitiesLoading}
          preparationStage={preparationStage}
          error={optimizationError}
          onCancel={onCancelOptimization}
          onClose={() => setOptimizationBase(undefined)}
          onCreate={onOptimize}
        />
      ) : null}
    </>
  );
}
