import { type ReactNode, useId } from "react";
import { useTranslation } from "react-i18next";

import {
  defaultModelFallbackApiKeyEnv,
  isModelFallbackEndpoint,
  modelFallbackApiKeyEnv,
  modelFallbackName,
  nextModelFallbackApiKeyEnv,
  normalizeModelFallbacks,
} from "./modelFallbacks";
import { isValidModelApiBaseUrl } from "./modelApiBase";
import type { ModelFallbackDraft, ModelFallbackEndpointDraft } from "./types";
import "./ModelFallbackFields.css";

type ModelFallbackFieldsVariant = "traditional" | "workbench";

export interface SameProviderFallbackFieldRenderProps {
  index: number;
  value: string;
  onChange: (modelName: string) => void;
}

function endpointFromFallback(
  fallback: ModelFallbackDraft,
  agentName: string | undefined,
  index: number,
  values: readonly ModelFallbackDraft[],
): ModelFallbackEndpointDraft {
  if (isModelFallbackEndpoint(fallback)) return fallback;
  return {
    modelName: fallback.trim(),
    modelProvider: "",
    modelApiBase: "",
    modelApiKeyEnv: nextModelFallbackApiKeyEnv(agentName, index, values),
  };
}

export function ModelFallbackFields({
  variant,
  primaryModelName,
  agentName,
  value,
  secretValues,
  configuredSecretEnvKeys,
  embedded,
  onChange,
  onSecretChange,
  renderSameProviderField,
}: {
  variant: ModelFallbackFieldsVariant;
  primaryModelName?: string;
  agentName?: string;
  value?: ModelFallbackDraft[];
  secretValues?: Record<string, string>;
  configuredSecretEnvKeys?: readonly string[];
  embedded?: boolean;
  onChange: (fallbacks: ModelFallbackDraft[]) => void;
  onSecretChange?: (key: string, value: string) => void;
  renderSameProviderField?: (
    props: SameProviderFallbackFieldRenderProps,
  ) => ReactNode;
}) {
  const { t } = useTranslation("create");
  const id = useId();
  const values = value ?? [];
  const configuredSecretEnvKeySet = new Set(configuredSecretEnvKeys ?? []);
  const primary = (primaryModelName ?? "").trim();
  const fieldClassName =
    embedded
      ? "cw-model-picker-field"
      : variant === "workbench"
      ? "new-agent-workbench__field"
      : "cw-field";
  const labelClassName =
    embedded
      ? "cw-model-picker-label"
      : variant === "workbench"
      ? "new-agent-workbench__model-field-label"
      : "cw-label";
  const inputClassName =
    variant === "workbench"
      ? "model-fallback-fields__input model-fallback-fields__input--workbench"
      : "model-fallback-fields__input cw-input";
  const addButtonClassName =
    variant === "workbench"
      ? "model-fallback-fields__add new-agent-workbench__secondary-button"
      : "model-fallback-fields__add cw-btn cw-btn-soft";
  const removeButtonClassName =
    variant === "workbench"
      ? "model-fallback-fields__remove new-agent-workbench__secondary-button"
      : "model-fallback-fields__remove cw-btn cw-btn-ghost";

  const normalized = normalizeModelFallbacks(primary, values);
  const filledValueCount = values.filter((item) => {
    if (typeof item === "string") return Boolean(item.trim());
    return (
      isModelFallbackEndpoint(item) &&
      Boolean(
        item.modelName.trim() ||
          item.modelProvider?.trim() ||
          item.modelApiBase?.trim(),
      )
    );
  }).length;
  const hasIgnoredValues =
    filledValueCount > 0 && normalized.length !== filledValueCount;

  const replaceFallback = (
    index: number,
    fallback: ModelFallbackDraft,
    normalize = false,
  ) => {
    const next = [...values];
    next[index] = fallback;
    onChange(normalize ? normalizeModelFallbacks(primary, next) : next);
  };

  const removeFallback = (index: number) => {
    const fallback = values[index];
    if (isModelFallbackEndpoint(fallback) && fallback.modelApiKeyEnv) {
      onSecretChange?.(fallback.modelApiKeyEnv, "");
    }
    onChange(values.filter((_, itemIndex) => itemIndex !== index));
  };

  return (
    <div className={fieldClassName}>
      <span className={labelClassName}>{t(`${variant}.model.fallbacks`)}</span>
      <div className="model-fallback-fields">
        {values.length ? (
          <div className="model-fallback-fields__rows">
            {values.map((fallback, index) => {
              const endpoint = isModelFallbackEndpoint(fallback)
                ? fallback
                : null;
              const fallbackValue = modelFallbackName(fallback);
              const fallbackApiKeyEnv =
                endpoint
                  ? modelFallbackApiKeyEnv(agentName, index, values, endpoint)
                  : defaultModelFallbackApiKeyEnv(agentName, index);
              const secretValue = secretValues?.[fallbackApiKeyEnv] ?? "";
              const configuredSecret =
                configuredSecretEnvKeySet.has(fallbackApiKeyEnv);
              const modelInputId = `${id}-${index}-model`;
              const apiBaseInvalid =
                endpoint !== null &&
                !isValidModelApiBaseUrl(endpoint.modelApiBase);
              return (
                <div
                  className={`model-fallback-fields__item${
                    endpoint ? " is-endpoint" : ""
                  }`}
                  key={`fallback-row-${index}`}
                >
                  <div className="model-fallback-fields__toolbar">
                    <div
                      className="model-fallback-fields__type"
                      role="radiogroup"
                      aria-label={t(`${variant}.model.fallbackType`)}
                    >
                      <button
                        type="button"
                        role="radio"
                        className={!endpoint ? "is-on" : ""}
                        aria-checked={!endpoint}
                        onClick={() => {
                          if (endpoint) {
                            if (endpoint.modelApiKeyEnv) {
                              onSecretChange?.(endpoint.modelApiKeyEnv, "");
                            }
                            replaceFallback(index, endpoint.modelName);
                          }
                        }}
                      >
                        {t(`${variant}.model.fallbackSameProvider`)}
                      </button>
                      <button
                        type="button"
                        role="radio"
                        className={endpoint ? "is-on" : ""}
                        aria-checked={Boolean(endpoint)}
                        onClick={() => {
                          if (!endpoint) {
                            replaceFallback(
                              index,
                              endpointFromFallback(
                                fallback,
                                agentName,
                                index,
                                values,
                              ),
                            );
                          }
                        }}
                      >
                        {t(`${variant}.model.fallbackOtherProvider`)}
                      </button>
                    </div>
                    <button
                      type="button"
                      className={removeButtonClassName}
                      onClick={() => removeFallback(index)}
                    >
                      {t(`${variant}.model.removeFallback`)}
                    </button>
                  </div>
                  <div className="model-fallback-fields__model-name">
                    <span className="model-fallback-fields__field-label">
                      {t(`${variant}.model.name`)}
                    </span>
                    {!endpoint ? (
                      renderSameProviderField ? (
                        renderSameProviderField({
                          index,
                          value: fallbackValue,
                          onChange: (modelName) =>
                            replaceFallback(index, modelName, true),
                        })
                      ) : (
                        <input
                          id={modelInputId}
                          className={inputClassName}
                          value={fallbackValue}
                          placeholder={t(`${variant}.model.fallbackPlaceholder`)}
                          onChange={(event) =>
                            replaceFallback(index, event.currentTarget.value)
                          }
                        />
                      )
                    ) : (
                      <input
                        id={modelInputId}
                        className={inputClassName}
                        value={endpoint.modelName}
                        placeholder={t(`${variant}.model.fallbackPlaceholder`)}
                        onChange={(event) =>
                          replaceFallback(index, {
                            ...endpoint,
                            modelName: event.currentTarget.value,
                            modelApiKeyEnv: fallbackApiKeyEnv,
                          })
                        }
                      />
                    )}
                  </div>
                  {endpoint ? (
                    <div className="model-fallback-fields__endpoint-details">
                      <label className="model-fallback-fields__field">
                        <span className="model-fallback-fields__field-label">
                          {t(`${variant}.model.provider`)}
                        </span>
                        <input
                          className={inputClassName}
                          value={endpoint.modelProvider ?? ""}
                          placeholder="openai"
                          onChange={(event) =>
                            replaceFallback(index, {
                              ...endpoint,
                              modelProvider: event.currentTarget.value,
                              modelApiKeyEnv: fallbackApiKeyEnv,
                            })
                          }
                        />
                      </label>
                      <label className="model-fallback-fields__field">
                        <span className="model-fallback-fields__field-label">
                          API Base
                        </span>
                        <input
                          className={inputClassName}
                          type="url"
                          inputMode="url"
                          value={endpoint.modelApiBase ?? ""}
                          placeholder="https://api.example.com/v1"
                          aria-invalid={apiBaseInvalid}
                          onChange={(event) =>
                            replaceFallback(index, {
                              ...endpoint,
                              modelApiBase: event.currentTarget.value,
                              modelApiKeyEnv: fallbackApiKeyEnv,
                            })
                          }
                        />
                        {apiBaseInvalid ? (
                          <span className="model-fallback-fields__error">
                            {t(`${variant}.model.invalidApiBase`)}
                          </span>
                        ) : null}
                      </label>
                      <label className="model-fallback-fields__field">
                        <span className="model-fallback-fields__field-label">
                          API Key
                        </span>
                        <input
                          className={inputClassName}
                          type="password"
                          value={secretValue}
                          placeholder={
                            configuredSecret && !secretValue
                              ? "••••••"
                              : t(`${variant}.model.apiKeyPlaceholder`)
                          }
                          autoComplete="new-password"
                          onChange={(event) => {
                            replaceFallback(index, {
                              ...endpoint,
                              modelApiKeyEnv: fallbackApiKeyEnv,
                            });
                            onSecretChange?.(
                              fallbackApiKeyEnv,
                              event.currentTarget.value,
                            );
                          }}
                        />
                      </label>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : null}
        <div className="model-fallback-fields__actions">
          <button
            type="button"
            className={addButtonClassName}
            onClick={() => onChange([...values, ""])}
          >
            {t(`${variant}.model.addFallback`)}
          </button>
        </div>
        <p className="model-fallback-fields__help">
          {t(`${variant}.model.fallbackHelp`)}
        </p>
        {hasIgnoredValues ? (
          <p className="model-fallback-fields__issue">
            {t(`${variant}.model.fallbackIgnored`)}
          </p>
        ) : null}
      </div>
    </div>
  );
}
