import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Select, type Option } from "@openai/apps-sdk-ui/components/Select";

import { listEnvironments, type StudioEnvironment } from "../adk/client";
import type { CloudEnvironmentConfig } from "../create/types";
import {
  ENVIRONMENT_CATEGORIES,
  environmentLanguageLabel,
  environmentOperatingSystemLabel,
} from "./environmentModel";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import "./CloudEnvironmentConfigurator.css";

interface CloudEnvironmentConfiguratorProps {
  value: CloudEnvironmentConfig;
  onChange: (value: CloudEnvironmentConfig) => void;
  disabled?: boolean;
  controlSize?: "lg" | "xl";
  controlClassName?: string;
  optionClassName?: string;
}

type EnvironmentOption = Option & { environment?: StudioEnvironment };

const DEFAULT_ENVIRONMENT_VALUE = "__default_environment__";
function defaultEnvironmentOption(t: TFunction): EnvironmentOption {
  return {
    value: DEFAULT_ENVIRONMENT_VALUE,
    label: t("cloudEnvironment.defaultLabel"),
    description: t("cloudEnvironment.defaultDescription"),
  };
}

export function isPersistenceStorageUnavailableError(cause: unknown): boolean {
  const message = cause instanceof Error ? cause.message : String(cause);
  return (
    message.includes("HTTP 503") && message.includes("管理员未配置持久化存储")
  );
}

const STATUS_KEYS = {
  preparing: "cloudEnvironment.status.preparing",
  queued: "cloudEnvironment.status.queued",
  building: "cloudEnvironment.status.building",
  scanning: "cloudEnvironment.status.scanning",
  available: "cloudEnvironment.status.available",
  failed: "cloudEnvironment.status.failed",
} as const;

function environmentStatus(environment: StudioEnvironment, t: TFunction) {
  return environment.latestVersion
    ? t(STATUS_KEYS[environment.latestVersion.status])
    : t("cloudEnvironment.status.notBuilt");
}

function statusColor(
  environment: StudioEnvironment,
): "secondary" | "success" | "warning" | "danger" {
  if (environment.latestVersion?.status === "available") return "success";
  if (environment.latestVersion?.status === "failed") return "danger";
  if (environment.latestVersion) return "warning";
  return "secondary";
}

export function CloudEnvironmentConfigurator({
  value,
  onChange,
  disabled = false,
  controlSize = "lg",
  controlClassName,
  optionClassName,
}: CloudEnvironmentConfiguratorProps) {
  const { t } = useTranslation("ui");
  const selectId = useId();
  const onChangeRef = useRef(onChange);
  const [environments, setEnvironments] = useState<StudioEnvironment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [usingDefaultFallback, setUsingDefaultFallback] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setUsingDefaultFallback(false);
    void listEnvironments(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setEnvironments(items);
      })
      .catch((cause) => {
        if (
          !controller.signal.aborted &&
          (cause as Error)?.name !== "AbortError"
        ) {
          if (isPersistenceStorageUnavailableError(cause)) {
            setEnvironments([]);
            setUsingDefaultFallback(true);
            onChangeRef.current({
              environmentId: "",
              environmentVersionId: "",
            });
          } else {
            setError(cause instanceof Error ? cause.message : String(cause));
          }
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [reloadKey]);

  const options = useMemo<EnvironmentOption[]>(
    () => [
      defaultEnvironmentOption(t),
      ...environments.map((environment) => ({
        value: environment.id,
        label: environment.name,
        description: `${environmentOperatingSystemLabel(environment.operatingSystem)} · ${environmentLanguageLabel(environment.language)} · ${environmentStatus(environment, t)}`,
        disabled: environment.latestVersion?.status !== "available",
        environment,
      })),
    ],
    [environments, t],
  );
  const selectedEnvironment = environments.find(
    (environment) => environment.id === value.environmentId,
  );
  const selectedVersion =
    selectedEnvironment?.latestVersion?.versionId === value.environmentVersionId
      ? selectedEnvironment.latestVersion
      : null;
  const selectedTools = selectedEnvironment
    ? ENVIRONMENT_CATEGORIES.flatMap((category) => category.options)
        .filter((option) => selectedEnvironment.optionIds.includes(option.id))
        .map((option) => option.label)
    : [];

  const selectEnvironment = (option: EnvironmentOption) => {
    if (option.value === DEFAULT_ENVIRONMENT_VALUE || !option.environment) {
      onChange({ environmentId: "", environmentVersionId: "" });
      return;
    }
    const versionId = option.environment.latestVersion?.versionId ?? "";
    onChange({ environmentId: option.value, environmentVersionId: versionId });
  };

  if (loading && environments.length === 0) {
    return (
      <div className="cloud-env-state" role="status">
        <TextShimmer duration={1.25}>{t("cloudEnvironment.loading")}</TextShimmer>
      </div>
    );
  }

  if (error && environments.length === 0) {
    return (
      <div className="cloud-env-state cloud-env-state--error" role="alert">
        <div>
          <strong>{t("cloudEnvironment.loadFailed")}</strong>
          <p>{error}</p>
        </div>
        <Button
          color="secondary"
          variant="soft"
          size="sm"
          onClick={() => setReloadKey((key) => key + 1)}
        >
          {t("common.retry")}
        </Button>
      </div>
    );
  }

  return (
    <section className="cloud-env-config" aria-labelledby={`${selectId}-title`}>
      <label
        className="cloud-env-field"
        id={`${selectId}-title`}
        htmlFor={selectId}
      >
        <span>{t("cloudEnvironment.label")}</span>
        <Select
          id={selectId}
          value={value.environmentId || DEFAULT_ENVIRONMENT_VALUE}
          options={options}
          size={controlSize}
          triggerClassName={controlClassName}
          optionClassName={optionClassName}
          pill={false}
          disabled={disabled}
          placeholder={t("cloudEnvironment.placeholder")}
          searchPlaceholder={t("cloudEnvironment.search")}
          searchEmptyMessage={t("cloudEnvironment.noMatches")}
          onChange={selectEnvironment}
        />
        <small>
          {t("cloudEnvironment.selectionHint")}
        </small>
      </label>

      {selectedEnvironment ? (
        <div className="cloud-env-summary" aria-live="polite">
          <div className="cloud-env-summary__head">
            <div>
              <strong>{selectedEnvironment.name}</strong>
              {selectedEnvironment.description ? (
                <p>{selectedEnvironment.description}</p>
              ) : null}
            </div>
            <Badge
              color={statusColor(selectedEnvironment)}
              variant="soft"
              size="sm"
            >
              {environmentStatus(selectedEnvironment, t)}
            </Badge>
          </div>
          <dl className="cloud-env-details">
            <div>
              <dt>{t("cloudEnvironment.operatingSystem")}</dt>
              <dd>
                {environmentOperatingSystemLabel(
                  selectedEnvironment.operatingSystem,
                )}
              </dd>
            </div>
            <div>
              <dt>{t("cloudEnvironment.language")}</dt>
              <dd>{environmentLanguageLabel(selectedEnvironment.language)}</dd>
            </div>
            <div>
              <dt>{t("cloudEnvironment.tools")}</dt>
              <dd>
                {selectedTools.length ? selectedTools.join(t("environmentCenter.listSeparator")) : t("cloudEnvironment.noExtraTools")}
              </dd>
            </div>
            <div>
              <dt>{t("cloudEnvironment.skills")}</dt>
              <dd>
                {selectedEnvironment.selectedSkills?.length
                  ? selectedEnvironment.selectedSkills
                      .map((skill) => skill.name)
                      .join(t("environmentCenter.listSeparator"))
                  : t("cloudEnvironment.noSkills")}
              </dd>
            </div>
            <div>
              <dt>{t("cloudEnvironment.imageVersion")}</dt>
              <dd>
                {selectedVersion?.versionId ||
                  value.environmentVersionId ||
                  t("cloudEnvironment.unavailable")}
              </dd>
            </div>
            <div>
              <dt>{t("cloudEnvironment.image")}</dt>
              <dd title={selectedVersion?.image || ""}>
                {selectedVersion?.image ||
                  t("cloudEnvironment.versionMissing")}
              </dd>
            </div>
          </dl>
          {!selectedVersion ? (
            <p className="cloud-env-version-warning" role="alert">
              {t("cloudEnvironment.versionChanged")}
            </p>
          ) : null}
        </div>
      ) : value.environmentId ? (
        <div className="cloud-env-version-warning" role="alert">
          {t("cloudEnvironment.selectionUnavailable")}
        </div>
      ) : (
        <p
          className={`cloud-env-guidance ${
            usingDefaultFallback ? "cloud-env-guidance--fallback" : ""
          }`}
        >
          {usingDefaultFallback
            ? t("cloudEnvironment.persistenceFallback")
            : environments.length === 0
              ? t("cloudEnvironment.emptyFallback")
              : t("cloudEnvironment.defaultGuidance")}
        </p>
      )}
    </section>
  );
}
