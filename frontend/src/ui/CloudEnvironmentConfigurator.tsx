import { useEffect, useId, useMemo, useState } from "react";
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
}

type EnvironmentOption = Option & { environment?: StudioEnvironment };

const DEFAULT_ENVIRONMENT_VALUE = "__default_environment__";
const DEFAULT_ENVIRONMENT_OPTION: EnvironmentOption = {
  value: DEFAULT_ENVIRONMENT_VALUE,
  label: "默认环境",
  description: "使用 AgentKit 默认运行环境",
};

const STATUS_LABELS = {
  preparing: "准备中",
  queued: "排队中",
  building: "构建中",
  scanning: "扫描中",
  available: "可用",
  failed: "构建失败",
} as const;

function environmentStatus(environment: StudioEnvironment) {
  return environment.latestVersion
    ? STATUS_LABELS[environment.latestVersion.status]
    : "未构建";
}

function statusColor(environment: StudioEnvironment): "secondary" | "success" | "warning" | "danger" {
  if (environment.latestVersion?.status === "available") return "success";
  if (environment.latestVersion?.status === "failed") return "danger";
  if (environment.latestVersion) return "warning";
  return "secondary";
}

export function CloudEnvironmentConfigurator({
  value,
  onChange,
  disabled = false,
}: CloudEnvironmentConfiguratorProps) {
  const selectId = useId();
  const [environments, setEnvironments] = useState<StudioEnvironment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void listEnvironments(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setEnvironments(items);
      })
      .catch((cause) => {
        if (!controller.signal.aborted && (cause as Error)?.name !== "AbortError") {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [reloadKey]);

  const options = useMemo<EnvironmentOption[]>(
    () => [
      DEFAULT_ENVIRONMENT_OPTION,
      ...environments.map((environment) => ({
        value: environment.id,
        label: environment.name,
        description: `${environmentOperatingSystemLabel(environment.operatingSystem)} · ${environmentLanguageLabel(environment.language)} · ${environmentStatus(environment)}`,
        disabled: environment.latestVersion?.status !== "available",
        environment,
      })),
    ],
    [environments],
  );
  const selectedEnvironment = environments.find(
    (environment) => environment.id === value.environmentId,
  );
  const selectedVersion = selectedEnvironment?.latestVersion?.versionId === value.environmentVersionId
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
        <TextShimmer duration={1.25}>正在加载环境...</TextShimmer>
      </div>
    );
  }

  if (error && environments.length === 0) {
    return (
      <div className="cloud-env-state cloud-env-state--error" role="alert">
        <div>
          <strong>环境加载失败</strong>
          <p>{error}</p>
        </div>
        <Button color="secondary" variant="soft" size="sm" onClick={() => setReloadKey((key) => key + 1)}>
          重试
        </Button>
      </div>
    );
  }

  return (
    <section className="cloud-env-config" aria-labelledby={`${selectId}-title`}>
      <label className="cloud-env-field" id={`${selectId}-title`} htmlFor={selectId}>
        <span>环境</span>
        <Select
          id={selectId}
          value={value.environmentId || DEFAULT_ENVIRONMENT_VALUE}
          options={options}
          size="lg"
          pill={false}
          disabled={disabled}
          placeholder="选择一个已构建的环境"
          searchPlaceholder="搜索环境"
          searchEmptyMessage="没有匹配的环境"
          onChange={selectEnvironment}
        />
        <small>仅可选择构建状态为“可用”的环境，部署时会固定到当前镜像版本。</small>
      </label>

      {selectedEnvironment ? (
        <div className="cloud-env-summary" aria-live="polite">
          <div className="cloud-env-summary__head">
            <div>
              <strong>{selectedEnvironment.name}</strong>
              {selectedEnvironment.description ? <p>{selectedEnvironment.description}</p> : null}
            </div>
            <Badge color={statusColor(selectedEnvironment)} variant="soft" size="sm">
              {environmentStatus(selectedEnvironment)}
            </Badge>
          </div>
          <dl className="cloud-env-details">
            <div>
              <dt>操作系统</dt>
              <dd>{environmentOperatingSystemLabel(selectedEnvironment.operatingSystem)}</dd>
            </div>
            <div>
              <dt>语言</dt>
              <dd>{environmentLanguageLabel(selectedEnvironment.language)}</dd>
            </div>
            <div>
              <dt>工具</dt>
              <dd>{selectedTools.length ? selectedTools.join("、") : "无额外工具"}</dd>
            </div>
            <div>
              <dt>技能</dt>
              <dd>{selectedEnvironment.selectedSkills?.length
                ? selectedEnvironment.selectedSkills.map((skill) => skill.name).join("、")
                : "无环境技能"}</dd>
            </div>
            <div>
              <dt>镜像版本</dt>
              <dd>{selectedVersion?.versionId || value.environmentVersionId || "不可用"}</dd>
            </div>
            <div>
              <dt>镜像</dt>
              <dd title={selectedVersion?.image || ""}>{selectedVersion?.image || "当前固定版本已不在列表中，请重新选择环境"}</dd>
            </div>
          </dl>
          {!selectedVersion ? (
            <p className="cloud-env-version-warning" role="alert">
              此环境的可用版本已变化，请重新选择后再发布。
            </p>
          ) : null}
        </div>
      ) : value.environmentId ? (
        <div className="cloud-env-version-warning" role="alert">
          已选择的环境不存在或无权访问，请重新选择。
        </div>
      ) : (
        <p className="cloud-env-guidance">
          {environments.length === 0
            ? "暂无自定义环境，将使用 AgentKit 默认运行环境。"
            : "当前使用 AgentKit 默认运行环境；选择自定义环境后，会基于对应镜像构建并加载环境技能。"}
        </p>
      )}
    </section>
  );
}
