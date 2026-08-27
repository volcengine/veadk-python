import type { IntelligentDevelopmentReleaseRef } from "../blocks";
import { IntelligentProjectLibrary } from "../create/IntelligentProjectLibrary";
import type {
  IntelligentCreateBaseVersion,
  IntelligentDevelopmentCapabilities,
} from "../create/IntelligentCreate";

interface MigratedProjectsPageProps {
  capabilities: IntelligentDevelopmentCapabilities | null;
  capabilitiesLoading: boolean;
  initialProjectId?: string;
  onOptimize: (base: IntelligentCreateBaseVersion) => void;
  onDownload: (delivery: IntelligentDevelopmentReleaseRef) => Promise<void>;
  onDeploy: (delivery: IntelligentDevelopmentReleaseRef) => void;
}

export function MigratedProjectsPage({
  capabilities,
  capabilitiesLoading,
  initialProjectId,
  onOptimize,
  onDownload,
  onDeploy,
}: MigratedProjectsPageProps) {
  return (
    <main className="migration-main migration-projects-page">
      <header className="migration-main__header">
        <div>
          <h2>已迁移项目</h2>
          <p>管理迁移后的源码版本，也可以选择任一版本继续优化。</p>
        </div>
      </header>
      <div className="migration-projects-page__content">
        <IntelligentProjectLibrary
          origin="migration"
          title="项目与版本"
          description="查看、下载、部署或对比源码版本，也可以基于任一版本继续优化。"
          emptyTitle="还没有已迁移的项目"
          emptyDescription="迁移完成后，源码会自动保存在这里。"
          capabilities={capabilities}
          capabilitiesLoading={capabilitiesLoading}
          creating={false}
          initialProjectId={initialProjectId}
          onSelectBaseVersion={onOptimize}
          onClearBaseVersion={() => undefined}
          onDownload={onDownload}
          onDeploy={onDeploy}
        />
      </div>
    </main>
  );
}
