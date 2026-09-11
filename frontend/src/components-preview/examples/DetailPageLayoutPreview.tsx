import { ComponentApi } from "../api/ComponentApi";
import { DetailPageLayout, DetailPageSidebar } from "../../components/layouts/DetailPageLayout";
import { Header } from "../../components/composites/Header";
import { InfoCard, InfoCardBody } from "../../components/composites/InfoCard";
import { UnderlineTabs } from "../../components/primitives/UnderlineTabs";
import back from "../../components/layouts/DetailPageLayout/assets/back.svg";
import chart from "../../components/layouts/DetailPageLayout/assets/chart.svg";
import gridLine from "../../components/layouts/DetailPageLayout/assets/grid-line.svg";
import baseline from "../../components/layouts/DetailPageLayout/assets/baseline.svg";
import "./DetailPageLayoutPreview.css";

function DetailPerformanceChart() {
  return <article className="detail-page-preview__performance-card" aria-label="Average Deal Size">
    <div className="detail-page-preview__chart-heading"><h3>Average Deal Size</h3><div><strong>2,800</strong><span>+15%</span></div></div>
    <div className="detail-page-preview__chart" role="img" aria-label="Average deal size trend from September 3 to September 9">
      <div className="detail-page-preview__grid">{["3,500", "3,000", "2,500", "2,000", "0"].map((value, index) => <div key={value}><span>{value}</span><img src={index === 4 ? baseline : gridLine} alt="" /></div>)}</div>
      <img className="detail-page-preview__line" src={chart} alt="" />
      <div className="detail-page-preview__dates">{["9/3", "9/5", "9/7", "9/9"].map((date) => <span key={date}>{date}</span>)}</div>
    </div>
  </article>;
}

export function DetailPageLayoutPreview() {
  return <section aria-labelledby="detail-page-layout-preview-title">
    <h2 className="component-preview-title" id="detail-page-layout-preview-title">Detail page layout</h2>
    <DetailPageLayout
      sidebar={<DetailPageSidebar />}
      back={<button className="detail-page-preview__back" type="button"><span><img src={back} alt="" /></span>Back</button>}
      header={<Header title="DocuMind" description="Parses multi-format docs, extracts key points and to-dos, and skips page-by-page reading." />}
      tabs={<UnderlineTabs aria-label="Agent details" items={[{ value: "overview", label: "OverView" }, { value: "configuration", label: "Configuration" }, { value: "integration", label: "Integration" }, { value: "evaluation", label: "Evaluation" }, { value: "versions", label: "Versions" }]} />}
    >
      <div className="detail-page-preview__overview">
        <section aria-labelledby="detail-key-metrics-title"><h2 className="detail-page-preview__section-title" id="detail-key-metrics-title">KEY METRICS</h2><div className="detail-page-preview__metrics">{[0,1,2,3].map((index) => <InfoCard key={index} title="TOTAL LEADS"><InfoCardBody value="12,480" description="+12% vs last quarter" /></InfoCard>)}</div></section>
        <section aria-labelledby="detail-performance-title"><h2 className="detail-page-preview__section-title" id="detail-performance-title">PERFORMANCE OVERVIEW</h2><div className="detail-page-preview__performance"><DetailPerformanceChart /><article className="detail-page-preview__performance-card"><div className="detail-page-preview__chart-heading"><h3>Title</h3></div></article></div></section>
      </div>
    </DetailPageLayout>
  <ComponentApi names={["DetailPageLayout", "DetailPageSidebar"]} />
    </section>;
}
