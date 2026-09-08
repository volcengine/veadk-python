import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, CopyButton } from "@openai/apps-sdk-ui/components/Button";
import {
  ArrowRotateCcw,
  Check,
  Collapse,
  Copy,
  Expand,
} from "@openai/apps-sdk-ui/components/Icon";

export function DeploymentErrorMessage({
  message,
  className = "",
  onRetry,
  retryLabel,
  defaultExpanded = true,
}: {
  message: string;
  className?: string;
  onRetry?: () => Promise<void>;
  retryLabel?: string;
  defaultExpanded?: boolean;
}) {
  const { t } = useTranslation("ui");
  const resolvedRetryLabel = retryLabel ?? t("deploymentError.retryDeployment");
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [retrying, setRetrying] = useState(false);

  const retry = async () => {
    if (!onRetry || retrying) return;
    setRetrying(true);
    try {
      await onRetry();
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div
      className={`deploy-error-message${expanded ? " is-expanded" : ""}${
        className ? ` ${className}` : ""
      }`}
      role="alert"
    >
      <p className="deploy-error-message-text">{message}</p>
      <div className="deploy-error-message-actions">
        {onRetry && (
          <Button
            type="button"
            className="deploy-error-retry"
            color="danger"
            variant="soft"
            size="sm"
            pill={false}
            loading={retrying}
            onClick={() => void retry()}
          >
            {!retrying && <ArrowRotateCcw />}
            {retrying ? t("deploymentError.retrying") : resolvedRetryLabel}
          </Button>
        )}
        <Button
          type="button"
          color="secondary"
          variant="ghost"
          size="sm"
          uniform
          pill={false}
          title={expanded ? t("deploymentError.collapse") : t("deploymentError.expand")}
          aria-label={expanded ? t("deploymentError.collapse") : t("deploymentError.expand")}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? <Collapse /> : <Expand />}
        </Button>
        <CopyButton
          copyValue={message}
          color="secondary"
          variant="ghost"
          size="sm"
          uniform
          pill={false}
          title={t("deploymentError.copy")}
          aria-label={t("deploymentError.copy")}
        >
          {({ copied }) => copied ? <Check /> : <Copy />}
        </CopyButton>
      </div>
    </div>
  );
}
