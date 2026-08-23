import { Checkbox } from "@openai/apps-sdk-ui/components/Checkbox";
import { Grid, XXs } from "@openai/apps-sdk-ui/components/Icon";
import { Input } from "@openai/apps-sdk-ui/components/Input";
import { Textarea } from "@openai/apps-sdk-ui/components/Textarea";
import { Switch } from "@openai/apps-sdk-ui/components/Switch";
import { useState } from "react";
import feishuLogo from "../assets/feishu-logo.svg";
import { GitHubLogo } from "./GitHubLogo";
import {
  AgentModelConfigFields,
  type AgentModelConfigValue,
} from "./AgentModelConfigFields";
import {
  AGENT_STORAGE_CAPABILITY_LABELS,
  AgentStorageConfigCard,
  AgentStorageConfigDialog,
  type AgentStorageCapabilities,
  type AgentStorageCapabilityKey,
} from "./AgentStorageConfigDialog";
import "./AgentConfigPanel.css";

type AgentConfigTab = "basic" | "capabilities";

const AGENT_TOOL_COLUMNS = [
  [
    { id: "left-parallel-web-search", label: "并行联网搜索" },
    { id: "left-web-reader", label: "网页读取" },
    { id: "left-image-generation", label: "图像生成" },
  ],
  [
    { id: "right-parallel-web-search", label: "并行联网搜索" },
    { id: "right-web-reader", label: "网页读取" },
    { id: "right-image-generation", label: "图像生成" },
  ],
] as const;

const MCP_OPTIONS = ["GitHub", "飞书", "Chrome", "自定义名称"] as const;
const SKILL_OPTIONS = [
  "senior-backend",
  "no-code-frontend-builder",
  "clean-pytest",
] as const;

export interface AgentConfigPanelProps {
  agentName: string;
  agentDescription: string;
  systemPrompt: string;
  modelConfig: AgentModelConfigValue;
  selectedMcps: string[];
  selectedSkills: string[];
  storageCapabilities: AgentStorageCapabilities;
  tone: "root" | "sub";
  onAgentNameChange: (value: string) => void;
  onAgentDescriptionChange: (value: string) => void;
  onSystemPromptChange: (value: string) => void;
  onModelConfigChange: (value: AgentModelConfigValue) => void;
  onSelectedMcpsChange: (value: string[]) => void;
  onSelectedSkillsChange: (value: string[]) => void;
  onStorageCapabilitiesChange: (value: AgentStorageCapabilities) => void;
  onClose: () => void;
}

function nextMissingOption(
  selected: readonly string[],
  options: readonly string[],
) {
  return options.find((option) => !selected.includes(option));
}

function McpChipIcon({ name }: { name: string }) {
  if (name === "GitHub") {
    return <GitHubLogo className="agent-config-panel__chip-icon" />;
  }
  if (name === "飞书") {
    return (
      <img className="agent-config-panel__chip-icon" src={feishuLogo} alt="" />
    );
  }
  if (name === "Chrome") {
    return (
      <span className="agent-config-panel__chrome-icon" aria-hidden="true" />
    );
  }
  return <Grid className="agent-config-panel__chip-icon" aria-hidden="true" />;
}

function CapabilityAddButton({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className="agent-config-panel__capability-add"
      aria-label={`添加${label}`}
      onClick={onClick}
    >
      <svg
        className="agent-config-panel__add-icon"
        viewBox="0 0 16 16"
        aria-hidden="true"
      >
        <path d="M7.5 13.3334V8.5H2.66667C2.39053 8.5 2.16667 8.27615 2.16667 8C2.16667 7.72386 2.39053 7.5 2.66667 7.5H7.5V2.66667C7.5 2.39053 7.72386 2.16667 8 2.16667C8.27615 2.16667 8.5 2.39053 8.5 2.66667V7.5H13.3334C13.6095 7.5 13.8334 7.72386 13.8334 8C13.8334 8.27615 13.6095 8.5 13.3334 8.5H8.5V13.3334C8.5 13.6095 8.27615 13.8334 8 13.8334C7.72386 13.8334 7.5 13.6095 7.5 13.3334Z" />
      </svg>
      <span>添加</span>
    </button>
  );
}

function RootAgentPanelIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M5.5 6V7.5M14.5 6V7.5M9 10.6001C9.8 10.6001 10.5 9.9001 10.5 9.1001V6M13.2002 13.2C11.4002 15 8.5002 15 6.7002 13.2M1 5.8V14.2C1 15.8802 1 16.7202 1.32698 17.362C1.6146 17.9265 2.07354 18.3854 2.63803 18.673C3.27976 19 4.11984 19 5.8 19H14.2C15.8802 19 16.7202 19 17.362 18.673C17.9265 18.3854 18.3854 17.9265 18.673 17.362C19 16.7202 19 15.8802 19 14.2V5.8C19 4.11984 19 3.27977 18.673 2.63803C18.3854 2.07354 17.9265 1.6146 17.362 1.32698C16.7202 1 15.8802 1 14.2 1H5.8C4.11984 1 3.27977 1 2.63803 1.32698C2.07354 1.6146 1.6146 2.07354 1.32698 2.63803C1 3.27976 1 4.11984 1 5.8Z" />
    </svg>
  );
}

function SubAgentPanelIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <path d="M10 12C10 13.1046 10.8954 14 12 14C13.1046 14 14 13.1046 14 12C14 10.8954 13.1046 10 12 10C10.8954 10 10 10.8954 10 12ZM10 12C8.4087 12 6.88257 11.3678 5.75736 10.2426C4.63214 9.11742 4 7.5913 4 6M4 6C5.10457 6 6 5.10457 6 4C6 2.89543 5.10457 2 4 2C2.89543 2 2 2.89543 2 4C2 5.10457 2.89543 6 4 6ZM4 6V14" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M5 5L15 15" />
      <path d="M15 5L5 15" />
    </svg>
  );
}

export function AgentConfigPanel({
  agentName,
  agentDescription,
  systemPrompt,
  modelConfig,
  selectedMcps,
  selectedSkills,
  storageCapabilities,
  tone,
  onAgentNameChange,
  onAgentDescriptionChange,
  onSystemPromptChange,
  onModelConfigChange,
  onSelectedMcpsChange,
  onSelectedSkillsChange,
  onStorageCapabilitiesChange,
  onClose,
}: AgentConfigPanelProps) {
  const [activeTab, setActiveTab] = useState<AgentConfigTab>("basic");
  const [activeStorageCapability, setActiveStorageCapability] =
    useState<AgentStorageCapabilityKey | null>(null);
  const [selectedTools, setSelectedTools] = useState<Set<string>>(
    () => new Set(),
  );
  const AgentIcon = tone === "root" ? RootAgentPanelIcon : SubAgentPanelIcon;

  return (
    <aside className="agent-config-panel" aria-label={`${agentName} 配置面板`}>
      <header className="agent-config-panel__header">
        <div className="agent-config-panel__identity">
          <span
            className={`agent-config-panel__icon agent-config-panel__icon--${tone}`}
          >
            <AgentIcon />
          </span>
          <h2>{agentName}</h2>
        </div>

        <button
          type="button"
          className="agent-config-panel__close"
          aria-label="关闭配置面板"
          onClick={onClose}
        >
          <CloseIcon />
        </button>
      </header>

      <div className="agent-config-panel__content">
        <div
          className="agent-config-panel__tabs"
          role="tablist"
          aria-label="智能体配置"
        >
          <button
            type="button"
            id="agent-config-basic-tab"
            role="tab"
            aria-controls="agent-config-basic-panel"
            aria-selected={activeTab === "basic"}
            className={`agent-config-panel__tab${activeTab === "basic" ? " is-active" : ""}`}
            onClick={() => setActiveTab("basic")}
          >
            基本信息
          </button>
          <button
            type="button"
            id="agent-config-capabilities-tab"
            role="tab"
            aria-controls="agent-config-capabilities-panel"
            aria-selected={activeTab === "capabilities"}
            className={`agent-config-panel__tab${activeTab === "capabilities" ? " is-active" : ""}`}
            onClick={() => setActiveTab("capabilities")}
          >
            能力扩展
          </button>
        </div>

        {activeTab === "basic" ? (
          <div
            id="agent-config-basic-panel"
            className="agent-config-panel__tab-content"
            role="tabpanel"
            aria-labelledby="agent-config-basic-tab"
          >
            <div className="agent-config-panel__fields">
              <div className="agent-config-panel__field">
                <label htmlFor="agent-config-name">名称</label>
                <Input
                  id="agent-config-name"
                  className="agent-config-panel__control"
                  value={agentName}
                  onChange={(event) => onAgentNameChange(event.target.value)}
                  autoComplete="off"
                />
              </div>

              <section
                className="agent-config-panel__config-group"
                aria-labelledby="agent-config-definition-heading"
              >
                <h3 id="agent-config-definition-heading">定义</h3>

                <div className="agent-config-panel__config-fields">
                  <div className="agent-config-panel__description-field">
                    <label htmlFor="agent-config-description">描述</label>
                    <Textarea
                      id="agent-config-description"
                      className="agent-config-panel__control"
                      value={agentDescription}
                      onChange={(event) =>
                        onAgentDescriptionChange(event.target.value)
                      }
                      autoComplete="off"
                    />
                  </div>

                  <div className="agent-config-panel__stacked-field">
                    <label htmlFor="agent-config-system-prompt">
                      系统提示词
                    </label>
                    <Textarea
                      id="agent-config-system-prompt"
                      className="agent-config-panel__control"
                      value={systemPrompt}
                      onChange={(event) =>
                        onSystemPromptChange(event.target.value)
                      }
                      autoComplete="off"
                    />
                  </div>
                </div>
              </section>

              <section
                className="agent-config-panel__config-group"
                aria-labelledby="agent-config-model-heading"
              >
                <h3 id="agent-config-model-heading">模型配置</h3>

                <div className="agent-config-panel__config-fields">
                  <AgentModelConfigFields
                    idPrefix="agent-config"
                    value={modelConfig}
                    onChange={onModelConfigChange}
                    fieldClassName="agent-config-panel__field"
                    controlClassName="agent-config-panel__control"
                    selectClassName="agent-config-panel__select-control"
                  />
                </div>
              </section>
            </div>
          </div>
        ) : (
          <div
            id="agent-config-capabilities-panel"
            className="agent-config-panel__tab-content"
            role="tabpanel"
            aria-labelledby="agent-config-capabilities-tab"
          >
            <div className="agent-config-panel__capability-stack">
              <div className="agent-config-panel__tools-field">
                <span className="agent-config-panel__field-label">工具</span>

                <div className="agent-config-panel__tool-grid">
                  {AGENT_TOOL_COLUMNS.map((column, columnIndex) => (
                    <div
                      key={`tool-column-${columnIndex + 1}`}
                      className="agent-config-panel__tool-column"
                    >
                      {column.map((tool) => (
                        <Checkbox
                          key={tool.id}
                          id={`agent-config-tool-${tool.id}`}
                          className="agent-config-panel__tool-checkbox"
                          checked={selectedTools.has(tool.id)}
                          onCheckedChange={(checked) => {
                            setSelectedTools((current) => {
                              const next = new Set(current);
                              if (checked) {
                                next.add(tool.id);
                              } else {
                                next.delete(tool.id);
                              }
                              return next;
                            });
                          }}
                          label={tool.label}
                        />
                      ))}
                    </div>
                  ))}
                </div>
              </div>

              <div className="agent-config-panel__capability-field">
                <span className="agent-config-panel__field-label">MCP</span>
                <div className="agent-config-panel__capability-list">
                  {selectedMcps.map((mcp) => (
                    <span
                      key={mcp}
                      className="agent-config-panel__capability-chip agent-config-panel__capability-chip--mcp"
                    >
                      <McpChipIcon name={mcp} />
                      <span>{mcp}</span>
                      <button
                        type="button"
                        className="agent-config-panel__chip-remove"
                        aria-label={`移除 MCP ${mcp}`}
                        onClick={() =>
                          onSelectedMcpsChange(
                            selectedMcps.filter((item) => item !== mcp),
                          )
                        }
                      >
                        <XXs aria-hidden="true" />
                      </button>
                    </span>
                  ))}
                  <CapabilityAddButton
                    label=" MCP"
                    onClick={() => {
                      const next =
                        nextMissingOption(selectedMcps, MCP_OPTIONS) ??
                        `MCP ${selectedMcps.length + 1}`;
                      onSelectedMcpsChange([...selectedMcps, next]);
                    }}
                  />
                </div>
              </div>

              <div className="agent-config-panel__capability-field">
                <span className="agent-config-panel__field-label">技能</span>
                <div className="agent-config-panel__capability-list agent-config-panel__capability-list--skills">
                  {selectedSkills.map((skill) => (
                    <button
                      key={skill}
                      type="button"
                      className="agent-config-panel__capability-chip agent-config-panel__capability-chip--skill"
                      aria-label={`移除技能 ${skill}`}
                      title="点击移除"
                      onClick={() =>
                        onSelectedSkillsChange(
                          selectedSkills.filter((item) => item !== skill),
                        )
                      }
                    >
                      {skill}
                    </button>
                  ))}
                  <CapabilityAddButton
                    label="技能"
                    onClick={() => {
                      const next =
                        nextMissingOption(selectedSkills, SKILL_OPTIONS) ??
                        `custom-skill-${selectedSkills.length + 1}`;
                      onSelectedSkillsChange([...selectedSkills, next]);
                    }}
                  />
                </div>
              </div>

              {(
                Object.keys(
                  AGENT_STORAGE_CAPABILITY_LABELS,
                ) as AgentStorageCapabilityKey[]
              ).map((capabilityKey) => {
                const capability = storageCapabilities[capabilityKey];
                const labels = AGENT_STORAGE_CAPABILITY_LABELS[capabilityKey];
                const switchId = `agent-config-${capabilityKey}`;

                return (
                  <div
                    key={capabilityKey}
                    className="agent-config-panel__storage-field"
                  >
                    <div className="agent-config-panel__storage-toggle-row">
                      <label
                        className="agent-config-panel__field-label"
                        htmlFor={switchId}
                      >
                        {labels.label}
                      </label>
                      <Switch
                        id={switchId}
                        checked={capability.enabled}
                        onCheckedChange={(checked) => {
                          if (checked) {
                            setActiveStorageCapability(capabilityKey);
                            return;
                          }
                          onStorageCapabilitiesChange({
                            ...storageCapabilities,
                            [capabilityKey]: {
                              ...capability,
                              enabled: false,
                            },
                          });
                        }}
                      />
                    </div>

                    {capability.enabled ? (
                      <AgentStorageConfigCard
                        capability={capabilityKey}
                        config={capability}
                        label={labels.label}
                        onEdit={() => setActiveStorageCapability(capabilityKey)}
                      />
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {activeStorageCapability ? (
        <AgentStorageConfigDialog
          key={activeStorageCapability}
          capability={activeStorageCapability}
          title={
            AGENT_STORAGE_CAPABILITY_LABELS[activeStorageCapability].dialogTitle
          }
          value={storageCapabilities[activeStorageCapability]}
          onCancel={() => setActiveStorageCapability(null)}
          onConfirm={(value) => {
            onStorageCapabilitiesChange({
              ...storageCapabilities,
              [activeStorageCapability]: value,
            });
            setActiveStorageCapability(null);
          }}
        />
      ) : null}
    </aside>
  );
}
