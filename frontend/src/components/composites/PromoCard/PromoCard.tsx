import consoleArtwork from "./assets/console-artwork.png";
import "./PromoCard.css";

export interface PromoCardProps {
  title?: string;
  description?: string;
  artworkSrc?: string;
  href?: string;
  className?: string;
}

/** Console promotion from Figma node 817:442129 */
export function PromoCard({
  title = "AgentKit Console",
  description = "Create and manage resources",
  artworkSrc = consoleArtwork,
  href,
  className,
}: PromoCardProps) {
  const classes = ["studio-promo-card", className].filter(Boolean).join(" ");
  const content = <>
    <img className="studio-promo-card__artwork" src={artworkSrc} alt="" aria-hidden="true" />
    <div className="studio-promo-card__content">
      <span className="studio-promo-card__title">{title}</span>
      <span className="studio-promo-card__description">{description}</span>
    </div>
  </>;

  return href
    ? <a className={classes} href={href}>{content}</a>
    : <article className={classes} aria-label={title}>{content}</article>;
}
