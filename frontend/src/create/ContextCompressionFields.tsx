import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Switch } from "@openai/apps-sdk-ui/components/Switch";
import { Input } from "@openai/apps-sdk-ui/components/Input";
import type { ContextCompressionDraft } from "./types";
import { capacityFields, normalizeContextCompression, ratioDefaults, ratioFields } from "./contextCompression";

/** Shared controls for the traditional wizard and the new workbench. */
export function ContextCompressionFields({
  value,
  onChange,
  disabled = false,
  variant,
}: {
  value?: ContextCompressionDraft;
  onChange: (value: ContextCompressionDraft) => void;
  disabled?: boolean;
  variant: "traditional" | "workbench";
}) {
  const { t } = useTranslation("create");
  const id = useId();
  const policy = value ?? { mode: "auto" };
  const traditional = variant === "traditional";
  const fieldClass = traditional ? "cw-field" : "new-agent-workbench__field";
  const helpClass = traditional ? "cw-dependency-hint" : "new-agent-workbench__model-field-label";
  let invalid = false;
  try { normalizeContextCompression(policy); } catch { invalid = true; }

  return (
    <div className={traditional ? "cw-form" : "new-agent-workbench__fields"}>
      <div className={fieldClass}>
        <label htmlFor={`${id}-mode`} className={traditional ? "cw-label" : undefined}>
          {t("contextCompression.title")}
        </label>
        <Switch
          id={`${id}-mode`}
          checked={policy.mode === "auto"}
          disabled={disabled}
          onCheckedChange={(checked) => onChange({ ...policy, mode: checked ? "auto" : "off" })}
          aria-describedby={`${id}-help`}
          aria-label={t("contextCompression.title")}
        />
        <span id={`${id}-help`} className={helpClass}>
          {t(policy.mode === "auto" ? "contextCompression.autoHint" : "contextCompression.offHint")}
        </span>
      </div>
      <details>
        <summary>{t("contextCompression.capacity")}</summary>
        <p className={helpClass}>{t("contextCompression.capacityHint")}</p>
        {capacityFields.map((field) => (
          <label className={fieldClass} key={field}>
            <span className={traditional ? "cw-label" : undefined}>{t(`contextCompression.${field}`)}</span>
            <Input
              type="number"
              min={1}
              max={Number.MAX_SAFE_INTEGER}
              step={1}
              value={policy[field] ?? ""}
              disabled={disabled}
              aria-invalid={policy[field] !== undefined && (!Number.isSafeInteger(policy[field]) || policy[field]! <= 0)}
              aria-describedby={invalid ? `${id}-error` : `${id}-help`}
              placeholder={t("contextCompression.automatic")}
              onChange={(event) => onChange({
                ...policy,
                [field]: event.currentTarget.value === "" ? undefined : Number(event.currentTarget.value),
              })}
            />
          </label>
        ))}
        <p className={helpClass}>{t("contextCompression.ratioHint")}</p>
        {ratioFields.map((field) => (
          <label className={fieldClass} key={field}>
            <span className={traditional ? "cw-label" : undefined}>{t(`contextCompression.${field}`)}</span>
            <Input
              type="number"
              min={1}
              max={100}
              step={1}
              value={policy[field] === undefined ? "" : Number((policy[field]! * 100).toFixed(6))}
              disabled={disabled}
              aria-invalid={invalid}
              aria-describedby={invalid ? `${id}-error` : undefined}
              placeholder={String(ratioDefaults[field] * 100)}
              onChange={(event) => onChange({
                ...policy,
                [field]: event.currentTarget.value === "" ? undefined : Number(event.currentTarget.value) / 100,
              })}
            />
          </label>
        ))}
      </details>
      {invalid ? <p id={`${id}-error`} role="alert" className={traditional ? "cw-error-text" : "new-agent-workbench__error"}>
        {t("contextCompression.invalid")}
      </p> : null}
    </div>
  );
}
