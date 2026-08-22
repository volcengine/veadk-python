import { useState } from "react";
import { Button, CopyButton } from "@openai/apps-sdk-ui/components/Button";
import {
  ArrowRotateCcw,
  Collapse,
  Expand,
} from "@openai/apps-sdk-ui/components/Icon";

export function DeploymentErrorMessage({
  message,
  className = "",
  onRetry,
  retryLabel = "重试部署",
  defaultExpanded = true,
}: {
  message: string;
  className?: string;
  onRetry?: () => Promise<void>;
  retryLabel?: string;
  defaultExpanded?: boolean;
}) {
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
            {retrying ? "重试中…" : retryLabel}
          </Button>
        )}
        <Button
          type="button"
          color="secondary"
          variant="ghost"
          size="sm"
          uniform
          pill={false}
          title={expanded ? "收起错误信息" : "展开完整错误信息"}
          aria-label={expanded ? "收起错误信息" : "展开完整错误信息"}
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
          title="复制完整错误信息"
          aria-label="复制完整错误信息"
        />
      </div>
    </div>
  );
}
