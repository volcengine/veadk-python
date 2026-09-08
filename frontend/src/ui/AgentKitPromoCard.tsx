import { type MouseEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { X } from "@openai/apps-sdk-ui/components/Icon";
import type { CloudProvider } from "../adk/cloudProvider";
import { agentKitLinks } from "./agentKitLinks";
import "./AgentKitPromoCard.css";

export interface AgentKitPromoCardProps {
  cloudProvider: CloudProvider;
}

export function AgentKitPromoCard({ cloudProvider }: AgentKitPromoCardProps) {
  const { t } = useTranslation("ui");
  const [dismissed, setDismissed] = useState(false);
  const [hoverSuppressed, setHoverSuppressed] = useState(false);
  const links = agentKitLinks(cloudProvider);

  const handleActionClick = (event: MouseEvent<HTMLAnchorElement>) => {
    event.currentTarget.blur();
    setHoverSuppressed(true);
  };

  if (dismissed) return null;

  return (
    <section
      className={`agentkit-promo-card${hoverSuppressed ? " is-hover-suppressed" : ""}`}
      aria-label={t("agentKitPromo.ariaLabel")}
      onMouseLeave={() => setHoverSuppressed(false)}
    >
      <Button
        className="agentkit-promo-close"
        color="secondary"
        variant="ghost"
        size="3xs"
        uniform
        pill={false}
        aria-label={t("agentKitPromo.closeAriaLabel")}
        title={t("common.close")}
        onClick={() => setDismissed(true)}
      >
        <X aria-hidden="true" />
      </Button>

      <h2 className="agentkit-promo-title">{t("agentKitPromo.title")}</h2>
      <p className="agentkit-promo-description">
        {t("agentKitPromo.description")}
      </p>

      <div className="agentkit-promo-actions">
        <a
          className="agentkit-promo-action is-docs"
          href={links.docs}
          target="_blank"
          rel="noreferrer"
          aria-label={t("agentKitPromo.docsAriaLabel")}
          onClick={handleActionClick}
        >
          {t("agentKitPromo.docs")}
        </a>
        <a
          className="agentkit-promo-action is-console"
          href={links.console}
          target="_blank"
          rel="noreferrer"
          aria-label={t("agentKitPromo.consoleAriaLabel")}
          onClick={handleActionClick}
        >
          {t("agentKitPromo.console")}
        </a>
      </div>
    </section>
  );
}
