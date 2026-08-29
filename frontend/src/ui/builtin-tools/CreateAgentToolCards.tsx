import { useMemo, type SVGProps } from "react";
import { Accordion } from "@base-ui/react/accordion";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import {
  filterCollectedResourcesByCategory,
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

const RESOURCE_CATEGORIES: Array<{ value: ResourceCategory; label: string }> = [
  { value: "skill_hub", label: "Skill Hub" },
  { value: "skill_space", label: "AgentKit 技能中心" },
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

function AccordionChevron(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="m4 6 4 4 4-4" />
    </svg>
  );
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
  const data = useMemo(() => parseCollectedResources(response), [response]);
  const groups = useMemo(() => RESOURCE_CATEGORIES.map((item) => ({
    ...item,
    ...filterCollectedResourcesByCategory(data, item.value),
  })), [data]);
  const defaultCategory = groups.find(
    (group) => group.resources.length > 0 || group.sources.length > 0,
  )?.value ?? "skill_hub";
  const failed = status === "failed";
  const error = failed ? responseError(response) : "";

  return (
    <section className="create-agent-tool-card" aria-label="召回资源信息">
      <div className="create-agent-card__summary">
        <span className="create-agent-card__summary-title">
          {status === "running" ? "正在并行检索资源" : `召回 ${data.resources.length} 项资源`}
        </span>
        {statusBadge(status)}
      </div>

      {status === "running" ? (
        <LoadingRows label="正在检索资源" />
      ) : failed ? (
        <div className="create-agent-card__message is-error" role="alert">
          <span className="create-agent-card__message-title">资源检索未完成</span>
          <span>{error || "请检查资源服务配置后重试。"}</span>
        </div>
      ) : (
        <Accordion.Root
          key={data.collectionId || "collected-resources"}
          className="create-agent-card__accordion"
          defaultValue={[defaultCategory]}
        >
          {groups.map((group) => (
            <Accordion.Item
              className="create-agent-card__accordion-item"
              key={group.value}
              value={group.value}
            >
              <Accordion.Header className="create-agent-card__accordion-header">
                <Accordion.Trigger className="create-agent-card__accordion-trigger">
                  <span>{group.label}</span>
                  <span className="create-agent-card__accordion-meta">
                    <Badge color="secondary" size="sm" variant="soft">
                      {group.resources.length}
                    </Badge>
                    <AccordionChevron className="create-agent-card__accordion-chevron" />
                  </span>
                </Accordion.Trigger>
              </Accordion.Header>
              <Accordion.Panel className="create-agent-card__accordion-content">
                {group.resources.length > 0 ? (
                  <div className="create-agent-card__resource-list">
                    {group.resources.map((resource) => (
                      <div className="create-agent-card__resource" key={resource.ref}>
                        <div className="create-agent-card__resource-main">
                          <div className="create-agent-card__resource-title">
                            <span className="create-agent-card__resource-name">{resource.name}</span>
                            {resource.version ? <span>版本 {resource.version}</span> : null}
                          </div>
                          {resource.description ? <p>{resource.description}</p> : null}
                          <span className="create-agent-card__resource-ref">{resource.ref}</span>
                        </div>
                        <Badge color="secondary" size="sm" variant="outline">
                          {group.label}
                        </Badge>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="create-agent-card__message">
                    <span className="create-agent-card__message-title">当前类别没有资源</span>
                    <span>本次检索未返回该类别的资源。</span>
                  </div>
                )}
                {group.sources.length > 0 ? (
                  <div className="create-agent-card__sources" aria-label={`${group.label}来源状态`}>
                    {group.sources.map((source) => (
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
              </Accordion.Panel>
            </Accordion.Item>
          ))}
        </Accordion.Root>
      )}
    </section>
  );
}

export function CreateAgentsCard({ args, response, status }: CreateAgentToolCardProps) {
  const data = useMemo(() => parseCreatedAgents(args, response), [args, response]);
  const topLevelError = status === "failed" ? responseError(response) : "";

  return (
    <section className="create-agent-tool-card" aria-label="创建 Agent 结果">
      <div className="create-agent-card__summary">
        <span className="create-agent-card__summary-title">
          {status === "running"
            ? `正在创建 ${data.agents.length} 个 Agent`
            : `${data.completedCount} 个成功，${data.failedCount} 个失败`}
        </span>
        {statusBadge(status)}
      </div>

      {topLevelError ? (
        <div className="create-agent-card__message is-error" role="alert">
          <span className="create-agent-card__message-title">Agent 创建未完成</span>
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
                    <span className="create-agent-card__agent-name">{agent.name}</span>
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
          <span className="create-agent-card__message-title">没有可展示的 Agent</span>
          <span>工具返回中未包含 Agent 配置或执行结果。</span>
        </div>
      )}
    </section>
  );
}
