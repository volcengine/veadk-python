import { PromoCard } from "../../components/composites/PromoCard";
import "./PromoCardPreview.css";

export function PromoCardPreview() {
  const id = "preview-promo-card";
  return (
    <section aria-labelledby={`${id}-title`}>
      <h2 data-preview-heading tabIndex={-1} id={`${id}-title`} className="component-preview-title">Promo Card</h2>
      <div className="promo-card-preview-example">
        <PromoCard />
      </div>
    </section>
  );
}
