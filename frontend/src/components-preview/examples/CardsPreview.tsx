import { PromoCardPreview } from "./PromoCardPreview";
import { ResourceCardPreview } from "./ResourceCardPreview";
import { InfoCardPreview } from "./InfoCardPreview";
import { CardLayoutPreview } from "./CardLayoutPreview";

export function CardsPreview() {
  return <div style={{ display: "grid", gap: 40, minWidth: 0 }}>
    <ResourceCardPreview />
    <InfoCardPreview />
    <PromoCardPreview />
    <CardLayoutPreview />
  </div>;
}
