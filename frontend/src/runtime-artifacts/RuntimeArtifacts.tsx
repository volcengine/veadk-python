import { useEffect, useMemo, useState } from "react";
import type { RuntimeArtifactScope } from "../adk/runtimeArtifacts";
import { Drawer } from "../components/composites/Drawer";
import { FileExplorer } from "../components/composites/FileExplorer";
import { Button } from "../components/primitives/Button";
import { EmptyState } from "../components/primitives/EmptyState";
import { ErrorState } from "../components/primitives/ErrorState";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import { artifactEntries } from "./artifactPreview";
import { useRuntimeArtifacts } from "./useRuntimeArtifacts";
import { RuntimeArtifactPreview } from "./RuntimeArtifactPreview";
import { ArtifactRefreshIcon, RuntimeArtifactsIcon } from "./RuntimeArtifactsIcons";
import "./RuntimeArtifacts.css";

export function RuntimeArtifacts({ scope, busy }: { scope: RuntimeArtifactScope; busy: boolean }) {
  const [open, setOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<string[]>([]);
  const { listing, loading, error, previewRevision, loadPreview, refresh } = useRuntimeArtifacts(scope, open, busy);
  const entries = useMemo(() => artifactEntries(listing?.items ?? []), [listing?.items]);

  useEffect(() => {
    if (!listing) return;
    setSelectedId(previous => listing.items.some(item => item.path === previous) ? previous : null);
    setExpandedIds(previous => [...new Set([...previous, ...listing.items.flatMap(item => {
      const parts = item.path.split("/");
      return parts.slice(0, -1).map((_part, index) => `folder:${parts.slice(0, index + 1).join("/")}`);
    })])]);
  }, [listing]);

  return <Drawer
    open={open}
    onOpenChange={setOpen}
    title="会话产物"
    description="浏览当前会话生成的文件"
    closeLabel="关闭会话产物"
    width="min(1120px, calc(100vw - 32px))"
    surface="solid"
    trigger={<Button variant="primary" startIcon={<RuntimeArtifactsIcon />}>会话产物</Button>}
  >
    {open && <div className="runtime-artifacts">
      <div className="runtime-artifacts__toolbar">
        <span role="status">{loading && listing ? <TextShimmer>正在刷新文件</TextShimmer> : listing?.available ? `${listing.items.length} 个文件${listing.nextCursor ? "，还有更多" : ""}` : ""}</span>
        <Button variant="ghost" loading={loading} startIcon={<ArtifactRefreshIcon />} onClick={() => void refresh(undefined, true)}>刷新</Button>
      </div>
      {busy && <p className="runtime-artifacts__notice" role="status">Agent 正在生成，完成后自动刷新</p>}
      {loading && !listing && <div className="runtime-artifacts__empty" role="status"><TextShimmer>正在加载会话产物</TextShimmer></div>}
      {error && <div className="runtime-artifacts__failure" role="alert"><ErrorState title="产物读取失败" description={error} /><Button variant="outline" onClick={() => void refresh(undefined, true)}>重试</Button></div>}
      {!error && listing && !listing.available ? <div className="runtime-artifacts__empty"><EmptyState title="产物存储暂不可用" description={listing.reason || "请稍后重试，或检查 Studio 的产物存储配置"} /></div>
        : listing?.available && listing.items.length === 0 ? <div className="runtime-artifacts__empty"><EmptyState title="这个会话还没有产物" description="让 Agent 使用“保存会话产物”工具生成文件，完成后会显示在这里" /></div>
          : listing?.available && listing.items.length > 0 ? <>
            <FileExplorer entries={entries} selectedId={selectedId} onSelect={setSelectedId} expandedIds={expandedIds} onExpandedChange={setExpandedIds} treeLabel="会话产物目录" height="calc(100dvh - 220px)" narrowLayout="stack" renderPreview={file => {
              const artifact = listing.items.find(item => item.path === file?.id);
              return <RuntimeArtifactPreview key={`${artifact?.path ?? "empty"}:${artifact?.updatedAt ?? ""}:${artifact?.sizeBytes ?? ""}:${previewRevision}`} scope={scope} file={artifact} loadPreview={loadPreview} />;
            }} />
            {listing.nextCursor && <div className="runtime-artifacts__more"><Button variant="ghost" loading={loading} onClick={() => void refresh(listing.nextCursor ?? undefined)}>加载更多文件</Button></div>}
          </> : null}
    </div>}
  </Drawer>;
}
