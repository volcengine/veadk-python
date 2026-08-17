import { useState } from "react";
import { isImeCompositionEvent } from "../ui/composerKeyboard";
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
}

export type IntelligentPreparationStage = "preparing" | "starting";

const PREPARATION_MESSAGES: Record<IntelligentPreparationStage, string> = {
  preparing: "正在准备完成这项任务所需的工具…",
  starting: "工具已准备好，正在开始处理你的目标…",
};

export interface IntelligentCreateProps {
  capabilities: IntelligentDevelopmentCapabilities | null;
  loading: boolean;
  preparationStage: IntelligentPreparationStage | null;
  error: string;
  onBack: () => void;
  onCancel: () => void;
  onCreate: (goal: string) => Promise<void>;
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
  const creating = preparationStage !== null;
  const unavailable = capabilities?.enabled !== true;
  const unavailableReason = loading
    ? "正在检查智能开发能力…"
    : capabilities?.enabled
      ? ""
      : capabilities?.reason || (error ? "" : "当前无法使用智能模式，请返回后重试。");
  const submitDisabled = loading || creating || unavailable || !goal.trim();

  async function submit() {
    const value = goal.trim();
    if (!value || submitDisabled) return;
    await onCreate(value);
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
          <p>描述目标后，AI 会自动判断意图、构建、调试并完成临时云端验证。</p>
        </div>
      </header>

      <div className="ic-main">
        <section className="ic-panel ic-goal-panel" aria-busy={creating}>
          <div className="ic-goal-heading">
            <span className="ic-create-icon-wrap"><IntelligentCreateIcon /></span>
            <div>
              <h2>从目标开始</h2>
              <p>只需说明 Agent 要解决的问题；会改变结果的关键信息，AI 才会追问。</p>
            </div>
          </div>
          <label className="ic-goal-label" htmlFor="intelligent-goal">目标描述</label>
          <textarea
            id="intelligent-goal"
            className="ic-goal-input"
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="例如：创建一个能读取销售数据、生成周报并验证输出格式的 VeADK Agent"
            rows={6}
            disabled={loading || creating || unavailable}
            autoFocus
          />
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
          <div className="ic-actions">
            <span>
              {creating
                ? "目标会保留在当前页面，取消后可以继续修改"
                : "开发环境保留最多 8 小时，可在同一 Thread 持续优化"}
            </span>
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
        </section>
      </div>
    </section>
  );
}
