import { ComponentApi } from "../api/ComponentApi";
import { useId } from "react";
import { PromoCard } from "../../components/composites/PromoCard";
import "./PromoCardPreview.css";

export function PromoCardPreview() {
  const id = useId();
  return (
    <section aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="component-preview-title">Promo card</h2>
      <div className="promo-card-preview-example">
        <PromoCard />
      </div>
    <ComponentApi names={["PromoCard"]} />
    </section>
  );
}
