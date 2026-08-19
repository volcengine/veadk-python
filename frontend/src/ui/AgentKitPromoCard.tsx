import type { CloudProvider } from "../adk/cloudProvider";
import { agentKitLinks } from "./agentKitLinks";
import "./AgentKitPromoCard.css";

export interface AgentKitPromoCardProps {
  cloudProvider: CloudProvider;
}

interface PromoLinkProps {
  href: string;
  label: string;
  tone: "console" | "docs";
}

function PromoLink({ href, label, tone }: PromoLinkProps) {
  return (
    <a
      className={`agentkit-promo-link is-${tone}`}
      href={href}
      target="_blank"
      rel="noreferrer"
      aria-label={`${label}，在新窗口打开`}
      title={label}
    >
      <span className="agentkit-promo-content">
        <span className="agentkit-promo-copy">{label}</span>
      </span>
      <svg
        className="agentkit-promo-external-icon"
        viewBox="0 0 20 20"
        aria-hidden="true"
      >
        <path d="M7.75 5.25h-2.5a1.5 1.5 0 0 0-1.5 1.5v8a1.5 1.5 0 0 0 1.5 1.5h8a1.5 1.5 0 0 0 1.5-1.5v-2.5" />
        <path d="M10.25 3.75h6v6M16 4 9 11" />
      </svg>
    </a>
  );
}

export function AgentKitPromoCard({ cloudProvider }: AgentKitPromoCardProps) {
  const links = agentKitLinks(cloudProvider);

  return (
    <div className="agentkit-promo-stack">
      <PromoLink
        href={links.console}
        label="前往 AgentKit 控制台"
        tone="console"
      />
      <PromoLink
        href={links.docs}
        label="查看 AgentKit 官方文档"
        tone="docs"
      />
    </div>
  );
}
