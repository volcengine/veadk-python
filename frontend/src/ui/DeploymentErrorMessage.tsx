import { useState } from "react";
import { Check, Copy, Loader2, Maximize2, Minimize2, RotateCcw } from "lucide-react";

export function DeploymentErrorMessage({
  message,
  className = "",
  onRetry,
}: {
  message: string;
  className?: string;
  onRetry?: () => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const copyMessage = async () => {
    try {
      await navigator.clipboard.writeText(message);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

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
    >
      <p className="deploy-error-message-text">{message}</p>
      <div className="deploy-error-message-actions">
        {onRetry && (
          <button
            type="button"
            className="deploy-error-retry"
            disabled={retrying}
            onClick={() => void retry()}
          >
            {retrying ? <Loader2 className="spin" /> : <RotateCcw />}
            {retrying ? "重试中…" : "重试部署"}
          </button>
        )}
        <button
          type="button"
          title={expanded ? "收起错误信息" : "展开完整错误信息"}
          aria-label={expanded ? "收起错误信息" : "展开完整错误信息"}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? <Minimize2 /> : <Maximize2 />}
        </button>
        <button
          type="button"
          title={copied ? "已复制" : "复制完整错误信息"}
          aria-label={copied ? "已复制" : "复制完整错误信息"}
          onClick={() => void copyMessage()}
        >
          {copied ? <Check /> : <Copy />}
        </button>
      </div>
    </div>
  );
}
