import { Textarea } from "@openai/apps-sdk-ui/components/Textarea";
import {
  AgentModelConfigFields,
  type AgentModelConfigValue,
} from "./AgentModelConfigFields";
import "./AgentDebugConfigPanel.css";

export interface AgentDebugConfigValue {
  agentName: string;
  description: string;
  modelConfig: AgentModelConfigValue;
  systemPrompt: string;
}

interface AgentDebugConfigPanelProps {
  idPrefix: string;
  value: AgentDebugConfigValue;
  showChangeBadges: boolean;
  onChange: (value: AgentDebugConfigValue) => void;
  onConfirm: () => void;
  onCancel: () => void;
}

function RequiredLabel({
  children,
  changed = false,
}: {
  children: string;
  changed?: boolean;
}) {
  return (
    <span className="agent-debug-config__label-row">
      <span>{children}</span>
      <span className="agent-debug-config__required" aria-hidden="true">*</span>
      {changed && <span className="agent-debug-config__change">Change</span>}
    </span>
  );
}

export function AgentDebugConfigPanel({
  idPrefix,
  value,
  showChangeBadges,
  onChange,
  onConfirm,
  onCancel,
}: AgentDebugConfigPanelProps) {
  return (
    <div className="agent-debug-config" aria-label={`${value.agentName} 调试配置`}>
      <header className="agent-debug-config__identity">
        <h2>{value.agentName}</h2>
      </header>

      <div className="agent-debug-config__content">
        <div className="agent-debug-config__fields">
          <label className="agent-debug-config__field" htmlFor={`${idPrefix}-description`}>
            <RequiredLabel>描述</RequiredLabel>
            <Textarea
              id={`${idPrefix}-description`}
              className="agent-debug-config__control agent-debug-config__description"
              value={value.description}
              onChange={(event) => onChange({ ...value, description: event.target.value })}
              autoComplete="off"
            />
          </label>

          <div className="agent-debug-config__field">
            <RequiredLabel changed={showChangeBadges}>模型</RequiredLabel>
            <div className="agent-debug-config__model-fields">
              <AgentModelConfigFields
                idPrefix={idPrefix}
                value={value.modelConfig}
                onChange={(modelConfig) => onChange({ ...value, modelConfig })}
                fieldClassName="agent-debug-config__model-field"
                controlClassName="agent-debug-config__control"
                selectClassName="agent-debug-config__select-control"
              />
            </div>
          </div>

          <label className="agent-debug-config__field" htmlFor={`${idPrefix}-system-prompt`}>
            <RequiredLabel changed={showChangeBadges}>系统提示词</RequiredLabel>
            <Textarea
              id={`${idPrefix}-system-prompt`}
              className="agent-debug-config__control agent-debug-config__system-prompt"
              rows={11}
              value={value.systemPrompt}
              onChange={(event) => onChange({ ...value, systemPrompt: event.target.value })}
              autoComplete="off"
            />
          </label>
        </div>
      </div>

      <footer className="agent-debug-config__actions">
        <button type="button" className="agent-debug-config__confirm" onClick={onConfirm}>
          确定
        </button>
        <button type="button" className="agent-debug-config__cancel" onClick={onCancel}>
          取消
        </button>
      </footer>
    </div>
  );
}
