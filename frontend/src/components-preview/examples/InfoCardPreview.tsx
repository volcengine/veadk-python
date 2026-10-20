import { InfoCard, InfoCardBody } from "../../components/composites/InfoCard";

export function InfoCardPreview() {
  return <section aria-labelledby="info-card-preview-title">
    <h2 data-preview-heading tabIndex={-1} id="info-card-preview-title" className="component-preview-title">Info Card</h2>
    <InfoCard title="TOTAL LEADS">
      <InfoCardBody value="12,480" description="+12% vs last quarter" />
    </InfoCard>
    </section>;
}
