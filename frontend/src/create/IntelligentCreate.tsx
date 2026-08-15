import { useState } from "react";
import { isImeCompositionEvent } from "../ui/composerKeyboard";
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

export interface IntelligentCreateProps {
  capabilities: IntelligentDevelopmentCapabilities | null;
  loading: boolean;
  creating: boolean;
  error: string;
  onBack: () => void;
  onCreate: (goal: string) => Promise<void>;
}

export function IntelligentCreate({
  capabilities,
  loading,
  creating,
  error,
  onBack,
  onCreate,
}: IntelligentCreateProps) {
  const [goal, setGoal] = useState("");
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
          <p>描述目标后进入开发会话，持续沟通、调试并交付可部署的 VeADK Agent。</p>
        </div>
      </header>

      <main className="ic-main">
        <section className="ic-panel ic-goal-panel">
          <div className="ic-goal-heading">
            <span className="ic-create-icon-wrap"><IntelligentCreateIcon /></span>
            <div>
              <h2>从目标开始</h2>
              <p>说明 Agent 要解决的问题、业务约束和验收标准；创建后仍可在会话中补充。</p>
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
          {unavailableReason ? (
            <p className={loading ? "ic-state" : "ic-error"} role={loading ? "status" : "alert"}>
              {unavailableReason}
            </p>
          ) : null}
          {error ? <p className="ic-error" role="alert">{error}</p> : null}
          <div className="ic-actions">
            <span>Enter 创建 · Shift+Enter 换行</span>
            <button type="button" className="ic-primary" onClick={() => void submit()} disabled={submitDisabled}>
              {creating ? "正在准备开发环境…" : "进入开发会话"}
            </button>
          </div>
        </section>
      </main>
    </section>
  );
}
