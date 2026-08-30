import { useMemo, type ReactNode, type SVGProps } from "react";
import { Accordion } from "@base-ui/react/accordion";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import {
  InternalKnowledge,
  Tools,
  ToolsSkills,
  Users,
} from "@openai/apps-sdk-ui/components/Icon";
import { Popover } from "@openai/apps-sdk-ui/components/Popover";
import {
  filterCollectedResourcesByCategory,
  parseCollectedResources,
  parseCreatedAgents,
  type CreatedAgentResourceView,
  type CreatedSubAgentView,
  type PythonToolView,
  type ResourceCategory,
  type ToolExecutionStatus,
} from "./createAgentToolCardData";
import {
  ResourceCard,
  ResourceCardDescription,
  ResourceCardHeader,
  ResourceIdentityMark,
} from "../ResourceCollection";
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
  { value: "tool", label: "工具" },
];

const AGENT_TYPE_LABELS: Record<string, string> = {
  llm: "LLM Agent",
  sequential: "顺序 Agent",
  parallel: "并行 Agent",
  loop: "循环 Agent",
  workflow: "Workflow",
};

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

function resourceTypeLabel(resource: CreatedAgentResourceView) {
  if (resource.kind === "tool") return "内置工具";
  if (resource.kind === "knowledge_base") return "知识库";
  if (resource.source.startsWith("skill_hub:")) return "Skill Hub";
  if (resource.source.startsWith("skill_space:")) return "AgentKit 技能中心";
  return "Skill";
}

function AgentResourceList({
  label,
  resources,
}: {
  label: string;
  resources: CreatedAgentResourceView[];
}) {
  if (resources.length === 0) return null;
  return (
    <section className="create-agent-card__popover-section">
      <h4>{label}</h4>
      <div className="create-agent-card__popover-list">
        {resources.map((resource) => (
          <div className="create-agent-card__popover-item" key={resource.ref}>
            <div className="create-agent-card__popover-item-heading">
              <strong>{resource.name}</strong>
              <Badge color="secondary" size="sm" variant="soft">
                {resourceTypeLabel(resource)}
              </Badge>
            </div>
            {resource.description ? <p>{resource.description}</p> : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function PythonToolList({ tools }: { tools: PythonToolView[] }) {
  if (tools.length === 0) return null;
  return (
    <section className="create-agent-card__popover-section">
      <h4>自写工具</h4>
      <Accordion.Root>
        {tools.map((tool, index) => (
          <Accordion.Item
            className="create-agent-card__python-tool"
            key={`${tool.name}:${index}`}
            value={`${tool.name}:${index}`}
          >
            <Accordion.Header className="create-agent-card__python-tool-header">
              <Accordion.Trigger className="create-agent-card__python-tool-trigger">
                <span>
                  <strong>{tool.name}</strong>
                  {tool.description ? <small>{tool.description}</small> : null}
                </span>
                <span className="create-agent-card__python-tool-meta">
                  <Badge color="secondary" size="sm" variant="soft">自写工具</Badge>
                  <AccordionChevron className="create-agent-card__python-tool-chevron" />
                </span>
              </Accordion.Trigger>
            </Accordion.Header>
            <Accordion.Panel className="create-agent-card__python-tool-panel">
              {tool.dependencies.length > 0 ? (
                <div className="create-agent-card__python-tool-dependencies">
                  依赖：{tool.dependencies.join(", ")}
                </div>
              ) : null}
              <pre tabIndex={0} aria-label={`${tool.name} 完整代码`}>
                <code>{tool.code}</code>
              </pre>
            </Accordion.Panel>
          </Accordion.Item>
        ))}
      </Accordion.Root>
    </section>
  );
}

function SubAgentList({ agents }: { agents: CreatedSubAgentView[] }) {
  if (agents.length === 0) return null;
  return (
    <section className="create-agent-card__popover-section">
      <h4>Sub Agent</h4>
      <div className="create-agent-card__popover-list">
        {agents.map((agent) => (
          <div className="create-agent-card__popover-item" key={agent.id}>
            <div className="create-agent-card__popover-item-heading">
              <strong>{agent.id}</strong>
              <Badge color="secondary" size="sm" variant="soft">
                {AGENT_TYPE_LABELS[agent.type] ?? agent.type}
              </Badge>
            </div>
            {agent.description ? <p>{agent.description}</p> : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function ResourceMetric({
  label,
  count,
  icon,
  children,
}: {
  label: string;
  count: number;
  icon: ReactNode;
  children: ReactNode;
}) {
  const metric = (
    <button
      className="create-agent-card__resource-metric"
      type="button"
      disabled={count === 0}
      aria-label={`${label} ${count} 项`}
    >
      {icon}
      <span>{count}</span>
    </button>
  );

  if (count === 0) {
    return metric;
  }

  return (
    <Popover showOnHover hoverOpenDelay={120}>
      <Popover.Trigger>{metric}</Popover.Trigger>
      <Popover.Content
        side="top"
        align="start"
        minWidth="auto"
        maxWidth={360}
        className="create-agent-card__resource-popover"
      >
        {children}
      </Popover.Content>
    </Popover>
  );
}

export function CollectResourcesCard({ response, status }: CreateAgentToolCardProps) {
  const data = useMemo(() => parseCollectedResources(response), [response]);
  const groups = useMemo(() => RESOURCE_CATEGORIES.map((item) => ({
    ...item,
    ...filterCollectedResourcesByCategory(data, item.value),
  })), [data]);
  const defaultCategory = groups.find(
    (group) => group.resources.length > 0,
  )?.value ?? "skill_hub";
  const failed = status === "failed";
  const error = failed ? responseError(response) : "";

  return (
    <section className="create-agent-tool-card" aria-label="召回资源信息">
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
                <div
                  className="create-agent-card__accordion-scroll"
                  role="region"
                  aria-label={`${group.label}资源列表`}
                  tabIndex={0}
                >
                  {group.resources.length > 0 ? (
                    <div className="create-agent-card__resource-list">
                      {group.resources.map((resource) => (
                        <div className="create-agent-card__resource" key={resource.ref}>
                          <div className="create-agent-card__resource-main">
                            <div className="create-agent-card__resource-title">
                              <span className="create-agent-card__resource-name">{resource.name}</span>
                              {resource.version ? (
                                <Badge
                                  className="create-agent-card__resource-version"
                                  color="secondary"
                                  size="sm"
                                  variant="soft"
                                >
                                  {resource.version}
                                </Badge>
                              ) : null}
                            </div>
                            {resource.description ? <p>{resource.description}</p> : null}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="create-agent-card__empty-category">
                      <p>本次检索未返回该类别的资源。</p>
                      {group.sources
                        .filter((source) => source.message)
                        .map((source) => (
                          <p
                            className="create-agent-card__raw-source-error"
                            key={source.source}
                          >
                            {source.message}
                          </p>
                        ))}
                    </div>
                  )}
                </div>
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
    <section className="create-agent-tool-card is-agent-results" aria-label="创建 Agent 结果">
      {topLevelError ? (
        <div className="create-agent-card__message is-error" role="alert">
          <span className="create-agent-card__message-title">Agent 创建未完成</span>
          <span>{topLevelError}</span>
        </div>
      ) : null}

      {data.agents.length > 0 ? (
        <div className="create-agent-card__agent-grid">
          {data.agents.map((agent) => {
            const agentStatus = status === "failed" ? "failed" : agent.status;
            const toolCount = agent.builtinTools.length + agent.pythonTools.length;
            return (
              <ResourceCard className="create-agent-card__agent-card" key={agent.name}>
                <ResourceCardHeader
                  leading={<ResourceIdentityMark seed={agent.name} />}
                  title={agent.name}
                  titleText={agent.name}
                  status={(
                    <Badge color="secondary" size="sm" variant="soft">
                      {AGENT_TYPE_LABELS[agent.rootType] ?? agent.rootType}
                    </Badge>
                  )}
                />
                {agent.description ? (
                  <ResourceCardDescription>{agent.description}</ResourceCardDescription>
                ) : null}
                {agent.error || (agentStatus === "failed" && topLevelError) ? (
                  <div className="create-agent-card__agent-result is-error" role="alert">
                    {agent.error || topLevelError}
                  </div>
                ) : null}
                <div className="create-agent-card__agent-resources" aria-label={`${agent.name} 具备的资源`}>
                  <ResourceMetric
                    label="Skill"
                    count={agent.skills.length}
                    icon={<ToolsSkills aria-hidden="true" />}
                  >
                    <AgentResourceList label="Skill" resources={agent.skills} />
                  </ResourceMetric>
                  <ResourceMetric
                    label="知识库"
                    count={agent.knowledgeBases.length}
                    icon={<InternalKnowledge aria-hidden="true" />}
                  >
                    <AgentResourceList label="知识库" resources={agent.knowledgeBases} />
                  </ResourceMetric>
                  <ResourceMetric
                    label="工具"
                    count={toolCount}
                    icon={<Tools aria-hidden="true" />}
                  >
                    <AgentResourceList label="内置工具" resources={agent.builtinTools} />
                    <PythonToolList tools={agent.pythonTools} />
                  </ResourceMetric>
                  <ResourceMetric
                    label="Sub Agent"
                    count={agent.subAgentCount}
                    icon={<Users aria-hidden="true" />}
                  >
                    <SubAgentList agents={agent.subAgents} />
                  </ResourceMetric>
                </div>
              </ResourceCard>
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
