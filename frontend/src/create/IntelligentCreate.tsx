import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  listModelOptions,
  type ModelOption,
} from "../adk/client";
import type { IntelligentDevelopmentReleaseRef } from "../blocks";
import { localeCompatibleBackendText } from "../i18n/locales";
import { isImeCompositionEvent } from "../ui/composerKeyboard";
import {
  NewChatCompactSelect,
  type NewChatCompactSelectOption,
} from "../ui/new-chat-modes/NewChatCompactSelect";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import { IntelligentProjectLibrary } from "./IntelligentProjectLibrary";
import "./IntelligentCreate.css";

function IntelligentCreateIcon() {
  return (
    <svg
      className="ic-create-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 5.5h14v13H5z" />
      <path d="m8 9 2 2-2 2M12.5 13H16" />
    </svg>
  );
}

export interface IntelligentDevelopmentCapabilities {
  enabled: boolean;
  reason: string;
  model?: {
    configured: boolean;
    id: string;
  };
  projectStorageEnabled?: boolean;
  projectStorageReason?: string;
}

export interface IntelligentCreateBaseVersion {
  projectId: string;
  versionId: string;
  projectName: string;
  versionLabel: string;
}

export type IntelligentPreparationStage = "preparing" | "starting";

const PREPARATION_MESSAGE_KEYS: Record<IntelligentPreparationStage, string> = {
  preparing: "intelligent.preparation.preparing",
  starting: "intelligent.preparation.starting",
};

function isSelectableModel(model: ModelOption): boolean {
  return model.available || model.lifecycleStatus === "Retiring";
}

interface IntelligentModelSelectProps {
  value: string;
  options: NewChatCompactSelectOption[];
  onChange: (value: string) => void;
  loading: boolean;
  error: string;
  disabled: boolean;
  onRetry: () => void;
}

function IntelligentModelSelect({
  value,
  options,
  onChange,
  loading,
  error,
  disabled,
  onRetry,
}: IntelligentModelSelectProps) {
  const { t } = useTranslation("create");
  return (
    <NewChatCompactSelect
      label={t("intelligent.model.label")}
      hideLabel
      value={value}
      options={options}
      onChange={onChange}
      placeholder={t("intelligent.model.placeholder")}
      searchable
      loading={loading}
      error={error}
      disabled={disabled}
      onRetry={onRetry}
    />
  );
}

export interface IntelligentCreateProps {
  capabilities: IntelligentDevelopmentCapabilities | null;
  loading: boolean;
  preparationStage: IntelligentPreparationStage | null;
  error: string;
  onBack: () => void;
  onCancel: () => void;
  onCreate: (
    goal: string,
    modelId: string,
    baseVersion?: IntelligentCreateBaseVersion,
  ) => Promise<void>;
  onDownload: (delivery: IntelligentDevelopmentReleaseRef) => Promise<void>;
  onDeploy: (delivery: IntelligentDevelopmentReleaseRef) => void;
  initialBaseVersion?: IntelligentCreateBaseVersion;
}

export function IntelligentGoalPanel({
  capabilities,
  loading,
  preparationStage,
  error,
  onCancel,
  onCreate,
  baseVersion,
  onClearBaseVersion,
}: Pick<
  IntelligentCreateProps,
  "capabilities" | "loading" | "preparationStage" | "error" | "onCancel" | "onCreate"
> & {
  baseVersion?: IntelligentCreateBaseVersion;
  onClearBaseVersion?: () => void;
}) {
  const { t, i18n } = useTranslation("create");
  const [goal, setGoal] = useState("");
  const [models, setModels] = useState<ModelOption[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState("");
  const [modelsReloadKey, setModelsReloadKey] = useState(0);
  const [selectedModelId, setSelectedModelId] = useState("");
  const goalInputRef = useRef<HTMLTextAreaElement>(null);
  const defaultModelId = capabilities?.model?.id.trim() ?? "";
  const displayModelId = selectedModelId || defaultModelId;
  const creating = preparationStage !== null;
  const unavailable = capabilities?.enabled !== true;
  const selectableModels = useMemo(
    () => models.filter(isSelectableModel),
    [models],
  );
  const modelSelectOptions = useMemo(() => {
    const options = selectableModels.map((model) => ({
      value: model.id,
      label: model.displayName,
      description: [
        model.id,
        model.vendorName,
        model.lifecycleStatus === "Retiring" ? t("intelligent.model.retiring") : "",
      ]
        .filter(Boolean)
        .join(" · "),
    }));
    if (
      displayModelId
      && !options.some((option) => option.value === displayModelId)
    ) {
      options.unshift({
        value: displayModelId,
        label: displayModelId,
        description: t("intelligent.model.currentConfiguration"),
      });
    }
    return options;
  }, [displayModelId, selectableModels, t]);
  const unavailableReason = loading
    ? t("intelligent.availability.checking")
    : capabilities?.enabled
      ? ""
      : localeCompatibleBackendText(
          capabilities?.reason,
          i18n.resolvedLanguage || i18n.language,
        ) || (error ? "" : t("intelligent.availability.unavailable"));
  const submitDisabled = loading || creating || unavailable || !goal.trim();

  useEffect(() => {
    const controller = new AbortController();
    setModelsLoading(true);
    setModelsError("");
    void listModelOptions({
      signal: controller.signal,
      refresh: modelsReloadKey > 0,
    })
      .then((response) => {
        if (controller.signal.aborted) return;
        setModels(response.models);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setModelsError(
            cause instanceof Error ? cause.message : t("intelligent.model.loadError"),
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setModelsLoading(false);
      });
    return () => controller.abort();
  }, [modelsReloadKey, t]);

  useEffect(() => {
    if (
      !selectedModelId
      || selectedModelId === defaultModelId
      || selectableModels.some((model) => model.id === selectedModelId)
    ) {
      return;
    }
    setSelectedModelId("");
  }, [defaultModelId, selectableModels, selectedModelId]);

  useEffect(() => {
    setGoal("");
    window.requestAnimationFrame(() => goalInputRef.current?.focus());
  }, [baseVersion?.versionId]);

  function changeModel(modelId: string) {
    const value = modelId.trim();
    setSelectedModelId(value && value !== defaultModelId ? value : "");
  }

  async function submit() {
    const value = goal.trim();
    if (!value || submitDisabled) return;
    const modelOverride =
      selectedModelId && selectedModelId !== defaultModelId
        ? selectedModelId
        : "";
    await onCreate(value, modelOverride, baseVersion);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === "Enter"
      && !event.shiftKey
      && !isImeCompositionEvent(event.nativeEvent)
    ) {
      event.preventDefault();
      void submit();
    }
  }

  return (
    <section className="ic-panel ic-goal-panel" aria-busy={creating}>
      <div className="ic-goal-heading">
        <span className="ic-create-icon-wrap"><IntelligentCreateIcon /></span>
        <div>
          <h2>{baseVersion ? t("intelligent.goal.continueTitle") : t("intelligent.goal.title")}</h2>
        </div>
      </div>
      <p className="ic-goal-hint">
        {baseVersion
          ? t("intelligent.goal.continueHint")
          : t("intelligent.goal.hint")}
      </p>
      {baseVersion ? (
        <div className="ic-selected-base">
          <span>{t("intelligent.goal.basedOn")}</span>
          <strong title={`${baseVersion.projectName} · ${baseVersion.versionLabel}`}>
            {baseVersion.projectName} · {baseVersion.versionLabel}
          </strong>
          {onClearBaseVersion ? (
            <button type="button" onClick={onClearBaseVersion}>
              {t("intelligent.goal.clearSelection")}
            </button>
          ) : null}
        </div>
      ) : null}
      <label className="ic-goal-label" htmlFor="intelligent-goal">
        {baseVersion ? t("intelligent.goal.optimizationLabel") : t("intelligent.goal.label")}
      </label>
      <div className="ic-composer">
        <textarea
          ref={goalInputRef}
          id="intelligent-goal"
          className="ic-goal-input"
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={baseVersion
            ? t("intelligent.goal.optimizationPlaceholder")
            : t("intelligent.goal.placeholder")}
          rows={6}
          disabled={loading || creating || unavailable}
          autoFocus
        />
        <div className="ic-actions">
          <div className="ic-composer-tools">
            <div className="ic-model-select">
              <IntelligentModelSelect
                value={displayModelId}
                options={modelSelectOptions}
                onChange={changeModel}
                loading={modelsLoading}
                error={modelsError}
                disabled={loading || creating || unavailable}
                onRetry={() => setModelsReloadKey((current) => current + 1)}
              />
            </div>
          </div>
          <div className="ic-action-buttons">
            {creating ? (
              <button type="button" className="ic-secondary" onClick={onCancel}>
                {t("common.cancel")}
              </button>
            ) : null}
            <button
              type="button"
              className="ic-primary"
              onClick={() => void submit()}
              disabled={submitDisabled}
              aria-busy={creating}
            >
              {creating ? t("intelligent.actions.preparing") : baseVersion ? t("intelligent.actions.optimize") : t("intelligent.actions.build")}
            </button>
          </div>
        </div>
      </div>
      {preparationStage ? (
        <div
          className="ic-preparation"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          <div>
            <strong>{t("intelligent.preparation.accepted")}</strong>
            <TextShimmer as="p" duration={2.4} spread={18}>
              {t(PREPARATION_MESSAGE_KEYS[preparationStage])}
            </TextShimmer>
            <p className="ic-preparation-next">
              {t("intelligent.preparation.next")}
            </p>
          </div>
        </div>
      ) : null}
      {unavailableReason ? (
        <p
          className={loading ? "ic-state" : "ic-error"}
          role={loading ? "status" : "alert"}
        >
          {unavailableReason}
        </p>
      ) : null}
      {error ? <p className="ic-error" role="alert">{error}</p> : null}
    </section>
  );
}

export function IntelligentCreate({
  capabilities,
  loading,
  preparationStage,
  error,
  onBack,
  onCancel,
  onCreate,
  onDownload,
  onDeploy,
  initialBaseVersion,
}: IntelligentCreateProps) {
  const { t } = useTranslation("create");
  const [baseVersion, setBaseVersion] = useState<IntelligentCreateBaseVersion | undefined>(
    initialBaseVersion,
  );

  return (
    <section className="ic-root" aria-labelledby="intelligent-create-title">
      <header className="ic-header">
        <button type="button" className="ic-back" onClick={onBack}>{t("common.back")}</button>
        <div>
          <h1 id="intelligent-create-title">{t("intelligent.title")}</h1>
          <p>{t("intelligent.subtitle")}</p>
        </div>
      </header>

      <div className="ic-main">
        <div className="ic-content">
          <IntelligentGoalPanel
            capabilities={capabilities}
            loading={loading}
            preparationStage={preparationStage}
            error={error}
            onCancel={onCancel}
            onCreate={onCreate}
            baseVersion={baseVersion}
            onClearBaseVersion={() => setBaseVersion(undefined)}
          />

          <IntelligentProjectLibrary
            capabilities={capabilities}
            capabilitiesLoading={loading}
            creating={preparationStage !== null}
            selectedBaseVersionId={baseVersion?.versionId}
            onSelectBaseVersion={setBaseVersion}
            onClearBaseVersion={() => setBaseVersion(undefined)}
            onDownload={onDownload}
            onDeploy={onDeploy}
          />
        </div>
      </div>
    </section>
  );
}
