import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { listAgentReviews, type AgentReviewApplication } from "../adk/agentReviews";
import { cloudRegionOptions, defaultCloudRegion, type CloudProvider } from "../adk/cloudProvider";
import { ResourceDataTable, ResourceFilterSelect, ResourceLoadingState, type ResourceDataTableColumn } from "../ui/ResourceCollection";
import { AgentReviewDialog, ReviewPersonLabel } from "./AgentReviewDialog";
import "./agentReviews.css";

export function AgentReviewCenter({ cloudProvider, onPendingCountChange, onChanged }: {
  cloudProvider: CloudProvider;
  onPendingCountChange: (count: number) => void;
  onChanged?: () => void;
}) {
  const { t, i18n } = useTranslation("agentReviews");
  const [region, setRegion] = useState(defaultCloudRegion(cloudProvider));
  const [items, setItems] = useState<AgentReviewApplication[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState<AgentReviewApplication | null>(null);
  useEffect(() => { setRegion(defaultCloudRegion(cloudProvider)); }, [cloudProvider]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    void listAgentReviews(region, controller.signal).then((result) => {
      if (controller.signal.aborted) return;
      setItems(result.items);
      onPendingCountChange(result.items.filter((item) => item.status === "pending").length);
    }).catch((value: unknown) => { if (!controller.signal.aborted) setError(value instanceof Error ? value.message : String(value)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [region, revision, onPendingCountChange]);
  const visible = useMemo(() => items.filter((item) => (status === "all" || item.status === status) && `${item.agent.name} ${item.submitter.name}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())), [items, query, status]);
  const columns: ResourceDataTableColumn<AgentReviewApplication>[] = [
    { key: "name", header: t("agent"), className: "review-column-name", render: (item) => <button type="button" className="agent-review-name" onClick={() => setSelected(item)}>{item.agent.name}</button> },
    { key: "submitter", header: t("submitter"), render: (item) => <ReviewPersonLabel person={item.submitter} /> },
    { key: "version", header: t("version"), render: (item) => item.agent.version ?? "—" },
    { key: "submittedAt", header: t("submittedAt"), render: (item) => <time dateTime={item.submittedAt}>{new Date(item.submittedAt).toLocaleString(i18n.language)}</time> },
    { key: "status", header: t("statusTitle"), render: (item) => <div>{t(`status.${item.status}`)}{item.reviewer ? <ReviewPersonLabel person={item.reviewer} /> : null}</div> },
    { key: "actions", header: t("actions"), render: (item) => <button type="button" onClick={() => setSelected(item)}>{t(item.status === "pending" ? "review" : "details")}</button> },
  ];
  return <div className="agent-review-center" aria-label={t("title")}>
    {error ? <div className="agent-review-error" role="alert"><p>{error}</p><button type="button" onClick={() => setRevision((value) => value + 1)}>{t("refresh")}</button></div> : null}
    <ResourceDataTable rows={visible} rowKey={(item) => `${item.region}:${item.id}`} columns={columns}
      searchValue={query} onSearchChange={setQuery} searchPlaceholder={t("search")} searchLabel={t("search")}
      toolbarActions={<>
        <ResourceFilterSelect id="agent-review-region" ariaLabel={t("region")} value={region} options={cloudRegionOptions(cloudProvider)} onChange={(value) => { setRegion(value); setItems([]); setSelected(null); }} />
        <ResourceFilterSelect id="agent-review-status" ariaLabel={t("statusTitle")} value={status} options={["all", "pending", "approved", "returned", "withdrawn"].map((value) => ({ value, label: t(value === "all" ? "all" : `status.${value}`) }))} onChange={setStatus} />
        <button type="button" disabled={loading} onClick={() => setRevision((value) => value + 1)}>{t("refresh")}</button>
      </>}
      emptyLabel={loading ? <ResourceLoadingState /> : error ? null : <p className="agent-review-empty">{t(query || status !== "all" ? "noMatches" : "empty")}</p>} />
    {selected ? <AgentReviewDialog key={`${selected.region}:${selected.id}`} runtimeId={selected.runtimeId} region={selected.region} name={selected.agent.name} canPublish onClose={() => setSelected(null)} onChanged={() => { onChanged?.(); setRevision((value) => value + 1); }} /> : null}
  </div>;
}
