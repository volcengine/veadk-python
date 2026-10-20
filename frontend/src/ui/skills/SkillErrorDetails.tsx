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
  const { t } = useTranslation("skills");
  const metadata = error as ErrorMetadata;
  const originalMessage = metadata.originalError?.message?.trim();
  const detailLines = [
    typeof metadata.status === "number"
      ? `HTTP ${metadata.status}${metadata.statusText ? ` ${metadata.statusText}` : ""}`
      : "",
    metadata.code ? t("errorDetails.code", { code: metadata.code }) : "",
    metadata.originalError?.type ? t("errorDetails.type", { type: metadata.originalError.type }) : "",
    metadata.originalError?.repr && metadata.originalError.repr !== originalMessage
      ? t("errorDetails.representation", { value: metadata.originalError.repr })
      : "",
    metadata.rawResponse?.trim() ? t("errorDetails.rawResponse", { value: metadata.rawResponse.trim() }) : "",
  ].filter(Boolean);

  return (
    <div className="skill-error-details">
      <div className="skill-error-details__summary">{error.message}</div>
      {originalMessage ? (
        <div className="skill-error-details__original">{t("errorDetails.original", { message: originalMessage })}</div>
      ) : null}
      {detailLines.length > 0 ? (
        <details>
          <summary>{t("errorDetails.details")}</summary>
          <pre>{detailLines.join("\n")}</pre>
        </details>
      ) : null}
    </div>
  );
}
import { useTranslation } from "react-i18next";
