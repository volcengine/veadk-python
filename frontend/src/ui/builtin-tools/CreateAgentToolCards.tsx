import { useMemo, useState } from "react";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import { SegmentedControl } from "@openai/apps-sdk-ui/components/SegmentedControl";
import {
  parseCollectedResources,
  parseCreatedAgents,
  type ResourceCategory,
  type ToolExecutionStatus,
} from "./createAgentToolCardData";
import "./create-agent-tool-cards.css";

export interface CreateAgentToolCardProps {
  args?: unknown;
  response?: unknown;
  status: ToolExecutionStatus;
}

type ResourceFilter = "all" | ResourceCategory;

const RESOURCE_FILTERS: Array<{ value: ResourceFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "skill_hub", label: "Skill Hub" },
  { value: "skill_space", label: "私域 Skill" },
  { value: "knowledge_base", label: "知识库" },
];

const AGENT_TYPE_LABELS: Record<string, string> = {
  llm: "LLM Agent",
  sequential: "顺序 Agent",
  parallel: "并行 Agent",
  loop: "循环 Agent",
  workflow: "Workflow",
};

function statusBadge(status: ToolExecutionStatus | "ok" | "skipped") {
  if (status === "completed" || status === "ok") {
    return <Badge color="success" size="sm" variant="soft">已完成</Badge>;
  }
  if (status === "failed") {
    return <Badge color="danger" size="sm" variant="soft">失败</Badge>;
  }
  if (status === "skipped") {
    return <Badge color="warning" size="sm" variant="soft">已跳过</Badge>;
  }
  return <Badge color="secondary" size="sm" variant="soft">进行中</Badge>;
}

function sourceStatusBadge(status: "ok" | "skipped" | "error") {
  if (status === "ok") return statusBadge("ok");
  if (status === "skipped") return statusBadge("skipped");
  return statusBadge("failed");
}

function responseError(response: unknown): string {
  if (typeof response === "string") return response;
  if (!response || typeof response !== "object" || Array.isArray(response)) return "";
  const record = response as Record<string, unknown>;
  const nested = record.result;
  if (typeof record.error === "string") return record.error;
  if (typeof record.message === "string") return record.message;
  if (nested && typeof nested === "object" && !Array.isArray(nested)) {
    const nestedRecord = nested as Record<string, unknown>;
    if (typeof nestedRecord.error === "string") return nestedRecord.error;
    if (typeof nestedRecord.message === "string") return nestedRecord.message;
  }
  return "";
}

function LoadingRows({ label }: { label: string }) {
  return (
    <div className="create-agent-card__loading" role="status" aria-label={label}>
      {[0, 1, 2].map((index) => (
        <div className="create-agent-card__skeleton-row" key={index} aria-hidden="true">
          <span />
          <span />
        </div>
      ))}
    </div>
  );
}

export function CollectResourcesCard({ response, status }: CreateAgentToolCardProps) {
  const [filter, setFilter] = useState<ResourceFilter>("all");
  const data = useMemo(() => parseCollectedResources(response), [response]);
  const resources = filter === "all"
    ? data.resources
    : data.resources.filter((resource) => resource.category === filter);
  const failed = status === "failed";
  const error = failed ? responseError(response) : "";

  return (
    <section className="create-agent-tool-card" aria-label="召回资源信息">
      <div className="create-agent-card__summary">
        <div>
          <strong>{status === "running" ? "正在并行检索资源" : `召回 ${data.resources.length} 项资源`}</strong>
          <span>
            {data.capabilities.googleAdkVersion
              ? `Google ADK ${data.capabilities.googleAdkVersion}，最多嵌套 ${data.capabilities.maxOrchestrationDepth} 层`
              : "检索 Skill Hub、私域 Skill 与 AgentKit 知识库"}
          </span>
        </div>
        {statusBadge(status)}
      </div>

      <div className="create-agent-card__segment-scroll">
        <SegmentedControl
          className="create-agent-card__segments"
          value={filter}
          size="sm"
          gutterSize="sm"
          block
          pill={false}
          disabled={status === "running"}
          aria-label="资源类型"
          onChange={setFilter}
        >
          {RESOURCE_FILTERS.map((item) => (
            <SegmentedControl.Option key={item.value} value={item.value}>
              <span>{item.label}</span>
              <span className="create-agent-card__segment-count">{data.counts[item.value]}</span>
            </SegmentedControl.Option>
          ))}
        </SegmentedControl>
      </div>

      {status === "running" ? (
        <LoadingRows label="正在检索资源" />
      ) : failed ? (
        <div className="create-agent-card__message is-error" role="alert">
          <strong>资源检索未完成</strong>
          <span>{error || "请检查资源服务配置后重试。"}</span>
        </div>
      ) : resources.length > 0 ? (
        <div className="create-agent-card__resource-list">
          {resources.map((resource) => (
            <div className="create-agent-card__resource" key={resource.ref}>
              <div className="create-agent-card__resource-main">
                <div className="create-agent-card__resource-title">
                  <strong>{resource.name}</strong>
                  {resource.version ? <span>版本 {resource.version}</span> : null}
                </div>
                {resource.description ? <p>{resource.description}</p> : null}
                <span className="create-agent-card__resource-ref">{resource.ref}</span>
              </div>
              <Badge color="secondary" size="sm" variant="outline">
                {RESOURCE_FILTERS.find((item) => item.value === resource.category)?.label}
              </Badge>
            </div>
          ))}
        </div>
      ) : (
        <div className="create-agent-card__message">
          <strong>当前分类没有资源</strong>
          <span>切换其他分类查看本次检索结果。</span>
        </div>
      )}

      {status !== "running" && data.sources.length > 0 ? (
        <div className="create-agent-card__sources" aria-label="资源来源状态">
          {data.sources.map((source) => (
            <div className="create-agent-card__source" key={source.source}>
              <span className="create-agent-card__source-name">{source.label}</span>
              <span className="create-agent-card__source-meta">
                {source.status === "ok" ? `${source.count} 项` : source.message}
              </span>
              {sourceStatusBadge(source.status)}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export function CreateAgentsCard({ args, response, status }: CreateAgentToolCardProps) {
  const data = useMemo(() => parseCreatedAgents(args, response), [args, response]);
  const topLevelError = status === "failed" ? responseError(response) : "";

  return (
    <section className="create-agent-tool-card" aria-label="创建 Agent 结果">
      <div className="create-agent-card__summary">
        <div>
          <strong>
            {status === "running"
              ? `正在创建 ${data.agents.length} 个 Agent`
              : `${data.completedCount} 个成功，${data.failedCount} 个失败`}
          </strong>
          <span>各 Agent 按提交顺序展示，执行结果彼此独立</span>
        </div>
        {statusBadge(status)}
      </div>

      {topLevelError ? (
        <div className="create-agent-card__message is-error" role="alert">
          <strong>Agent 创建未完成</strong>
          <span>{topLevelError}</span>
        </div>
      ) : null}

      {data.agents.length > 0 ? (
        <div className="create-agent-card__agent-list">
          {data.agents.map((agent) => {
            const agentStatus = status === "failed" ? "failed" : agent.status;
            return (
              <div className="create-agent-card__agent" key={agent.name}>
                <div className="create-agent-card__agent-head">
                  <div>
                    <strong>{agent.name}</strong>
                    <span>{AGENT_TYPE_LABELS[agent.rootType] ?? agent.rootType}</span>
                  </div>
                  {statusBadge(agentStatus)}
                </div>
                {agent.task ? <p>{agent.task}</p> : null}
                <div className="create-agent-card__agent-metrics" aria-label={`${agent.name} 配置摘要`}>
                  <span>{agent.nodeCount} 个节点</span>
                  <span>{agent.resourceCount} 项资源</span>
                  <span>{agent.pythonToolCount} 个 Python 工具</span>
                </div>
                {agent.output ? (
                  <div className="create-agent-card__agent-result">{agent.output}</div>
                ) : null}
                {agent.error || (agentStatus === "failed" && topLevelError) ? (
                  <div className="create-agent-card__agent-result is-error" role="alert">
                    {agent.error || topLevelError}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : status === "running" ? (
        <LoadingRows label="正在创建 Agent" />
      ) : (
        <div className="create-agent-card__message">
          <strong>没有可展示的 Agent</strong>
          <span>工具返回中未包含 Agent 配置或执行结果。</span>
        </div>
      )}
    </section>
  );
}
