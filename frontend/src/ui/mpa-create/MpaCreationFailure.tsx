import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { MpaCreationTask } from "../../adk/mpaCreation";
import { Button } from "../../components/primitives/Button";
import "./MpaCreationFailure.css";

const prefix = "myAgents.mpaCreate.failureDetails";
const categories = new Set([
  "timeout",
  "connection",
  "throttled",
  "unavailable",
  "permission",
  "invalid_request",
  "not_found",
  "provider_error",
  "ownership",
  "metadata_pending",
  "metadata_missing",
  "resource_failed",
  "configuration_changed",
  "deployment_error",
  "unknown",
  "child_exit",
  "interrupted",
  "protocol_error",
]);
const legacyReasons: Record<string, string> = {
  iamPermissionDenied: "permission",
  iamTemporaryFailure: "unavailable",
  iamVerificationFailed: "iamVerification",
  iamTrustConflict: "iamTrustConflict",
  iamPolicyConflict: "iamPolicyConflict",
  iamOwnershipConflict: "ownership",
  iamConfigurationConflict: "configuration_changed",
  tosBucketUnavailable: "tosBucketUnavailable",
  runtimeNameCheckFailed: "nameCheckUnavailable",
  openvikingPermissionDenied: "permission",
  openvikingQuotaExceeded: "quota",
  openvikingModelEndpointsInvalid: "modelEndpoints",
  openvikingModelConfigurationRejected: "modelConfiguration",
  openvikingConfigurationConflict: "configuration_changed",
  openvikingCreateUnknown: "creationUnconfirmed",
  openvikingNotReady: "metadata_pending",
  openvikingResourceFailed: "resource_failed",
  openvikingResourceMissing: "not_found",
  openvikingUnavailable: "unavailable",
  openvikingInvalidResponse: "protocol_error",
  configurationChanged: "configuration_changed",
  timeout: "timeout",
  interrupted: "interrupted",
};
function reasonFor(
  task: MpaCreationTask,
  category: string,
  code: string,
): string {
  if (/^(ExceededQuota|QuotaExceeded|LimitExceeded)([._]|$)/.test(code))
    return "quota";
  if (/^(AccessDenied|Forbidden|Unauthorized)([._]|$)/.test(code))
    return "permission";
  if (
    /^(ResourceAlreadyExists|AlreadyExists|DuplicateName)([._]|$)/.test(code) ||
    task.error === "runtimeNameTaken"
  )
    return "nameConflict";
  if (code === "PostgreSQL.28P01") return "databaseAuthentication";
  if (code === "PostgreSQL.42501") return "databasePermission";
  if (task.error === "configurationChanged") return "configuration_changed";
  if (task.error && legacyReasons[task.error]) return legacyReasons[task.error];
  return categories.has(category) ? category : "unknown";
}

export function MpaCreationFailure({ task }: { task: MpaCreationTask }) {
  const { t } = useTranslation("ui");
  const [copyStatus, setCopyStatus] = useState("");
  if (task.state !== "failed") return null;
  const candidate = task.latestDiagnostic;
  const diagnostic =
    candidate?.stage === task.stage && candidate.outcome === "failed"
      ? candidate
      : undefined;
  const rawCode = diagnostic?.errorCode ?? "";
  const code =
    /^[A-Z][A-Za-z0-9]*(?:[._][A-Za-z0-9]+)*$/.test(rawCode) &&
    rawCode.length <= 128
      ? rawCode
      : "";
  const rawRequestId = diagnostic?.requestId ?? "";
  const requestId = /^[0-9A-Fa-f-]{16,128}$/.test(rawRequestId)
    ? rawRequestId
    : "";
  const operation =
    diagnostic?.operation && /^[A-Za-z_]{1,80}$/.test(diagnostic.operation)
      ? diagnostic.operation
      : "";
  const exceptionTypes = new Set([
    "Exception", "ApiError", "AuthError", "NetworkError", "HTTPError",
    "HTTPStatusError", "RequestException", "TimeoutError", "Timeout",
    "ConnectTimeout", "ReadTimeout", "ConnectionError", "ConnectError",
    "ReadError", "SSLError", "JSONDecodeError", "ValidationError",
    "ValueError", "TypeError", "KeyError", "RuntimeError", "OSError",
  ]);
  const rawType = diagnostic?.exceptionType ?? "";
  const parts = rawType.split(" -> ");
  const exceptionType = rawType.length <= 256 && parts.length <= 8 &&
    parts.every((part) => exceptionTypes.has(part)) ? rawType : "";
  const rawStatus = diagnostic?.httpStatus;
  const httpStatus = typeof rawStatus === "number" && Number.isInteger(rawStatus) &&
    rawStatus >= 100 && rawStatus <= 599 ? String(rawStatus) : "";
  const rawResponseType = diagnostic?.responseType ?? "";
  const responseType = ["application/json", "text/html", "text/plain", "other"].includes(rawResponseType)
    ? rawResponseType : "";
  const reason = t(
    `${prefix}.reasons.${reasonFor(task, diagnostic?.category ?? "unknown", code)}`,
  );
  const fields = [
    [t(`${prefix}.stage`), t(`myAgents.mpaCreate.stages.${task.stage}`)],
    ...(operation ? [[t(`${prefix}.operation`), operation]] : []),
    ...(code ? [[t(`${prefix}.errorCode`), code]] : []),
    ...(exceptionType ? [[t(`${prefix}.exceptionType`), exceptionType]] : []),
    ...(httpStatus ? [[t(`${prefix}.httpStatus`), httpStatus]] : []),
    ...(responseType ? [[t(`${prefix}.responseType`), responseType]] : []),
    ...(requestId ? [["Request ID", requestId]] : []),
  ];
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(
        [reason, ...fields.map(([label, value]) => `${label}: ${value}`)].join(
          "\n",
        ),
      );
      setCopyStatus("copied");
    } catch {
      setCopyStatus("copyFailed");
    }
  };
  return (
    <div className="mpa-creation-failure" role="alert">
      <p>{reason}</p>
      <details>
        <summary>{t(`${prefix}.details`)}</summary>
        <dl>
          {fields.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        <Button variant="outline" size="compact" onClick={() => void copy()}>
          {t(`${prefix}.copy`)}
        </Button>
        {copyStatus && (
          <span role="status">{t(`${prefix}.${copyStatus}`)}</span>
        )}
      </details>
    </div>
  );
}
