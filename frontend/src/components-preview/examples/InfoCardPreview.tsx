import { ComponentApi } from "../api/ComponentApi";
import { InfoCard, InfoCardBody } from "../../components/composites/InfoCard";

export function InfoCardPreview() {
  return <section aria-labelledby="info-card-preview-title">
    <h2 id="info-card-preview-title" className="component-preview-title">Info card</h2>
    <InfoCard title="TOTAL LEADS">
      <InfoCardBody value="12,480" description="+12% vs last quarter" />
    </InfoCard>
  <ComponentApi names={["InfoCard", "InfoCardTitle", "InfoCardBody"]} />
    </section>;
}
