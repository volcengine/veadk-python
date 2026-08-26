import { useEffect, useMemo, useState } from "react";
import {
  listModelOptions,
  type ModelOption,
} from "../adk/client";
import { isImeCompositionEvent } from "../ui/composerKeyboard";
import {
  NewChatCompactSelect,
  type NewChatCompactSelectOption,
} from "../ui/new-chat-modes/NewChatCompactSelect";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
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
}

export type IntelligentPreparationStage = "preparing" | "starting";

const PREPARATION_MESSAGES: Record<IntelligentPreparationStage, string> = {
  preparing: "正在创建任务环境…",
  starting: "环境已就绪，正在启动 Codex…",
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
  return (
    <NewChatCompactSelect
      label="模型"
      hideLabel
      value={value}
      options={options}
      onChange={onChange}
      placeholder="选择模型"
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
  onCreate: (goal: string, modelId: string) => Promise<void>;
}

export function IntelligentCreate({
  capabilities,
  loading,
  preparationStage,
  error,
  onBack,
  onCancel,
  onCreate,
}: IntelligentCreateProps) {
  const [goal, setGoal] = useState("");
  const [models, setModels] = useState<ModelOption[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState("");
  const [modelsReloadKey, setModelsReloadKey] = useState(0);
  const defaultModelId = capabilities?.model?.id.trim() ?? "";
  const [selectedModelId, setSelectedModelId] = useState("");
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
        model.lifecycleStatus === "Retiring" ? "即将下线" : "",
      ]
        .filter(Boolean)
        .join(" · "),
    }));
    if (
      displayModelId &&
      !options.some((option) => option.value === displayModelId)
    ) {
      options.unshift({
        value: displayModelId,
        label: displayModelId,
        description: "当前配置",
      });
    }
    return options;
  }, [displayModelId, selectableModels]);
  const unavailableReason = loading
    ? "正在检查智能开发能力…"
    : capabilities?.enabled
      ? ""
      : capabilities?.reason || (error ? "" : "当前无法使用智能模式，请返回后重试。");
  const submitDisabled =
    loading ||
    creating ||
    unavailable ||
    !goal.trim();

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
            cause instanceof Error ? cause.message : "加载模型列表失败",
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setModelsLoading(false);
      });
    return () => controller.abort();
  }, [modelsReloadKey]);

  useEffect(() => {
    if (
      !selectedModelId ||
      selectedModelId === defaultModelId ||
      (selectedModelId &&
        selectableModels.some((model) => model.id === selectedModelId))
    ) {
      return;
    }
    setSelectedModelId("");
  }, [defaultModelId, selectableModels, selectedModelId]);

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
    await onCreate(value, modelOverride);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !isImeCompositionEvent(event.nativeEvent)
    ) {
      event.preventDefault();
      void submit();
    }
  }

  return (
    <section className="ic-root" aria-labelledby="intelligent-create-title">
      <header className="ic-header">
        <button type="button" className="ic-back" onClick={onBack}>
          返回
        </button>
        <div>
          <h1 id="intelligent-create-title">智能模式</h1>
          <p>描述目标后，沙箱中的 Codex 会判断你的意图，完成构建、调试和临时云端验证。</p>
        </div>
      </header>

      <div className="ic-main">
        <section className="ic-panel ic-goal-panel" aria-busy={creating}>
          <div className="ic-goal-heading">
            <span className="ic-create-icon-wrap"><IntelligentCreateIcon /></span>
            <div>
              <h2>从目标开始</h2>
            </div>
          </div>
          <p className="ic-goal-hint">只需说明 Agent 要解决的问题；如有影响结果的关键信息，会在开始前向你确认。</p>
          <label className="ic-goal-label" htmlFor="intelligent-goal">目标描述</label>
          <div className="ic-composer">
            <textarea
              id="intelligent-goal"
              className="ic-goal-input"
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
              onKeyDown={onKeyDown}
              placeholder="例如：创建一个能读取销售数据、生成周报并校验输出格式的 Agent"
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
                    取消
                  </button>
                ) : null}
                <button
                  type="button"
                  className="ic-primary"
                  onClick={() => void submit()}
                  disabled={submitDisabled}
                  aria-busy={creating}
                >
                  {creating ? "准备中…" : "开始构建"}
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
                <strong>目标已收到，马上开始实现</strong>
                <TextShimmer as="p" duration={2.4} spread={18}>
                  {PREPARATION_MESSAGES[preparationStage]}
                </TextShimmer>
                <p className="ic-preparation-next">
                  接下来会先梳理目标和实现方式，再编写、运行和验证 Agent。
                </p>
              </div>
            </div>
          ) : null}
          {unavailableReason ? (
            <p className={loading ? "ic-state" : "ic-error"} role={loading ? "status" : "alert"}>
              {unavailableReason}
            </p>
          ) : null}
          {error ? <p className="ic-error" role="alert">{error}</p> : null}
        </section>
      </div>
    </section>
  );
}
