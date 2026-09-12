import { useState } from "react";
import { LoadMoreArea } from "../../components/composites/LoadMoreArea";
import { ResourceCard } from "../../components/composites/ResourceCard";
import { ComponentApi } from "../api/ComponentApi";
import "./LoadMoreAreaPreview.css";

const examples = [
  ["Meeting Assistant", "Gather context and prepare a concise briefing before each meeting."],
  ["Research Assistant", "Find relevant sources and organize research into a clear summary."],
  ["Code Reviewer", "Review changes and highlight issues that need attention."],
  ["Document Assistant", "Organize documents and locate the information you need."],
  ["Data Analyst", "Explore datasets and summarize useful insights."],
  ["Workflow Assistant", "Coordinate recurring tasks and track their progress."],
];

export function LoadMoreAreaPreview() {
  const [count, setCount] = useState(6);
  async function loadMore(signal: AbortSignal) {
    await new Promise<void>((resolve, reject) => {
      if (signal.aborted) { reject(signal.reason); return; }
      const abort = () => { clearTimeout(timer); reject(signal.reason); };
      const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, 900);
      signal.addEventListener("abort", abort, { once: true });
    });
    if (!signal.aborted) setCount(current => Math.min(current + 6, 24));
  }
  return <section aria-labelledby="load-more-preview-title">
    <h2 id="load-more-preview-title" className="component-preview-title">下拉加载</h2>
    <LoadMoreArea hasMore={count < 24} onLoadMore={loadMore} aria-label="资源卡片列表" contentClassName="load-more-preview-grid">
      {Array.from({ length: count }, (_, index) => {
        const [title, description] = examples[index % examples.length];
        return <ResourceCard key={index} title={index < 6 ? title : `${title} ${Math.floor(index / 6) + 1}`} description={description} author="Studio" updatedLabel="Updated 09-11" />;
      })}
    </LoadMoreArea>
    <ComponentApi names={["LoadMoreArea"]} />
  </section>;
}
