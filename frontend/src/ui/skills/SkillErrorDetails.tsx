interface ErrorMetadata extends Error {
  status?: number;
  statusText?: string;
  code?: string;
  originalError?: {
    type?: string;
    message?: string;
    repr?: string;
  };
  rawResponse?: string;
}

export function normalizeSkillError(reason: unknown, fallback: string): Error {
  if (reason instanceof Error) return reason;
  if (typeof reason === "string" && reason.trim()) return new Error(reason.trim());
  return new Error(fallback);
}

export function SkillErrorDetails({ error }: { error: Error }) {
  const metadata = error as ErrorMetadata;
  const originalMessage = metadata.originalError?.message?.trim();
  const detailLines = [
    typeof metadata.status === "number"
      ? `HTTP ${metadata.status}${metadata.statusText ? ` ${metadata.statusText}` : ""}`
      : "",
    metadata.code ? `错误码：${metadata.code}` : "",
    metadata.originalError?.type ? `错误类型：${metadata.originalError.type}` : "",
    metadata.originalError?.repr && metadata.originalError.repr !== originalMessage
      ? `异常表示：${metadata.originalError.repr}`
      : "",
    metadata.rawResponse?.trim() ? `服务端原始响应：\n${metadata.rawResponse.trim()}` : "",
  ].filter(Boolean);

  return (
    <div className="skill-error-details">
      <div className="skill-error-details__summary">{error.message}</div>
      {originalMessage ? (
        <div className="skill-error-details__original">原始错误：{originalMessage}</div>
      ) : null}
      {detailLines.length > 0 ? (
        <details>
          <summary>详细信息</summary>
          <pre>{detailLines.join("\n")}</pre>
        </details>
      ) : null}
    </div>
  );
}
