import { type MouseEvent, useState } from "react";
import { Button, ButtonLink } from "@openai/apps-sdk-ui/components/Button";
import { ArrowRight, X } from "@openai/apps-sdk-ui/components/Icon";
import type { CloudProvider } from "../adk/cloudProvider";
import { agentKitLinks } from "./agentKitLinks";
import "./AgentKitPromoCard.css";

export interface AgentKitPromoCardProps {
  cloudProvider: CloudProvider;
}

export function AgentKitPromoCard({ cloudProvider }: AgentKitPromoCardProps) {
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
      aria-label="AgentKit 快速入口"
      onMouseLeave={() => setHoverSuppressed(false)}
    >
      <Button
        className="agentkit-promo-close"
        color="secondary"
        variant="ghost"
        size="3xs"
        uniform
        pill={false}
        aria-label="关闭 AgentKit 欢迎卡片"
        title="关闭"
        onClick={() => setDismissed(true)}
      >
        <X aria-hidden="true" />
      </Button>

      <h2 className="agentkit-promo-title">欢迎使用 AgentKit</h2>
      <p className="agentkit-promo-description">
        通过 AgentKit 平台快速构建与托管您的企业级智能体
      </p>

      <div className="agentkit-promo-actions">
        <ButtonLink
          className="agentkit-promo-action is-docs"
          href={links.docs}
          external
          color="secondary"
          variant="soft"
          size="xs"
          pill={false}
          aria-label="打开 AgentKit 文档，在新窗口打开"
          onClick={handleActionClick}
        >
          文档
        </ButtonLink>
        <ButtonLink
          className="agentkit-promo-action is-console"
          href={links.console}
          external
          color="primary"
          variant="solid"
          size="xs"
          pill={false}
          aria-label="打开 AgentKit 控制台，在新窗口打开"
          onClick={handleActionClick}
        >
          控制台
          <ArrowRight
            className="agentkit-promo-arrow-icon"
            aria-hidden="true"
          />
        </ButtonLink>
      </div>
    </section>
  );
}
