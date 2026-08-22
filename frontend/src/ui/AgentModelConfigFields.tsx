import { Input } from "@openai/apps-sdk-ui/components/Input";
import { Select, type Option } from "@openai/apps-sdk-ui/components/Select";
import type { ReactNode } from "react";

export type AgentModelCategory = "custom" | "volcano-ark";

export interface AgentModelConfigValue {
  category: AgentModelCategory;
  customProvider: string;
  customModelName: string;
  customBaseUrl: string;
  customApiKey: string;
  volcanoApiKey: string;
  volcanoModelName: string;
}

const MODEL_CATEGORY_OPTIONS: Option<AgentModelCategory>[] = [
  { value: "custom", label: "自定义" },
  { value: "volcano-ark", label: "火山方舟" },
];

export function activeAgentModelName(value: AgentModelConfigValue): string {
  return value.category === "custom"
    ? value.customModelName
    : value.volcanoModelName;
}

interface AgentModelConfigFieldsProps {
  idPrefix: string;
  value: AgentModelConfigValue;
  onChange: (value: AgentModelConfigValue) => void;
  fieldClassName: string;
  controlClassName: string;
  selectClassName: string;
  renderLabel?: (label: string) => ReactNode;
}

export function AgentModelConfigFields({
  idPrefix,
  value,
  onChange,
  fieldClassName,
  controlClassName,
  selectClassName,
  renderLabel = (label) => label,
}: AgentModelConfigFieldsProps) {
  const fieldId = (suffix: string) =>
    `${idPrefix}-${suffix === "category" ? "model-category" : suffix}`;

  return (
    <>
      <div className={fieldClassName}>
        <label htmlFor={fieldId("category")}>{renderLabel("模型类别")}</label>
        <Select
          id={fieldId("category")}
          options={MODEL_CATEGORY_OPTIONS}
          value={value.category}
          onChange={(option) => onChange({ ...value, category: option.value })}
          triggerClassName={selectClassName}
          size="md"
          pill={false}
          block
          align="start"
        />
      </div>

      {value.category === "custom" ? (
        <>
          <div className={fieldClassName}>
            <label htmlFor={fieldId("custom-provider")}>
              {renderLabel("模型提供商")}
            </label>
            <Input
              id={fieldId("custom-provider")}
              className={controlClassName}
              value={value.customProvider}
              onChange={(event) =>
                onChange({ ...value, customProvider: event.target.value })
              }
              autoComplete="off"
            />
          </div>
          <div className={fieldClassName}>
            <label htmlFor={fieldId("custom-model-name")}>
              {renderLabel("模型名称")}
            </label>
            <Input
              id={fieldId("custom-model-name")}
              className={controlClassName}
              value={value.customModelName}
              onChange={(event) =>
                onChange({ ...value, customModelName: event.target.value })
              }
              autoComplete="off"
            />
          </div>
          <div className={fieldClassName}>
            <label htmlFor={fieldId("custom-base-url")}>
              {renderLabel("Base URL")}
            </label>
            <Input
              id={fieldId("custom-base-url")}
              className={controlClassName}
              value={value.customBaseUrl}
              onChange={(event) =>
                onChange({ ...value, customBaseUrl: event.target.value })
              }
              autoComplete="off"
            />
          </div>
          <div className={fieldClassName}>
            <label htmlFor={fieldId("custom-api-key")}>
              {renderLabel("API Key")}
            </label>
            <Input
              id={fieldId("custom-api-key")}
              className={controlClassName}
              type="password"
              value={value.customApiKey}
              onChange={(event) =>
                onChange({ ...value, customApiKey: event.target.value })
              }
              autoComplete="new-password"
            />
          </div>
        </>
      ) : (
        <>
          <div className={fieldClassName}>
            <label htmlFor={fieldId("volcano-api-key")}>
              {renderLabel("API Key")}
            </label>
            <Input
              id={fieldId("volcano-api-key")}
              className={controlClassName}
              type="password"
              value={value.volcanoApiKey}
              onChange={(event) =>
                onChange({ ...value, volcanoApiKey: event.target.value })
              }
              autoComplete="new-password"
            />
          </div>
          <div className={fieldClassName}>
            <label htmlFor={fieldId("volcano-model-name")}>
              {renderLabel("模型名称")}
            </label>
            <Input
              id={fieldId("volcano-model-name")}
              className={controlClassName}
              value={value.volcanoModelName}
              onChange={(event) =>
                onChange({ ...value, volcanoModelName: event.target.value })
              }
              autoComplete="off"
            />
          </div>
        </>
      )}
    </>
  );
}
