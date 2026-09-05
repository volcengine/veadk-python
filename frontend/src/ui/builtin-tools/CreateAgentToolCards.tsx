import { useMemo, type ReactNode, type SVGProps } from "react";
import { Accordion } from "@base-ui/react/accordion";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import {
  Tools,
  ToolsSkills,
  Users,
} from "@openai/apps-sdk-ui/components/Icon";
import { Popover } from "@openai/apps-sdk-ui/components/Popover";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import {
  filterCollectedResourcesByCategory,
  parseCollectedResources,
  parseCreatedAgents,
  toolResponseError,
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
import { ResourceLibraryIcon } from "../icons/SidebarIcons";
import "./create-agent-tool-cards.css";

export interface CreateAgentToolCardProps {
  args?: unknown;
  response?: unknown;
  status: ToolExecutionStatus;
}

const RESOURCE_CATEGORIES: ResourceCategory[] = [
  "skill_hub",
  "skill_space",
  "knowledge_base",
  "tool",
];

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

function resourceTypeLabel(resource: CreatedAgentResourceView, t: TFunction) {
  if (resource.kind === "tool") return t("blocks.createAgents.builtinTool");
  if (resource.kind === "knowledge_base") return t("blocks.createAgents.knowledgeBase");
  if (resource.source.startsWith("skill_hub:")) return "Skill Hub";
  if (resource.source.startsWith("skill_space:")) return t("blocks.createAgents.skillCenter");
  return "Skill";
}

function AgentResourceList({
  label,
  resources,
}: {
  label: string;
  resources: CreatedAgentResourceView[];
}) {
  const { t } = useTranslation("conversation");
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
                {resourceTypeLabel(resource, t)}
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
  const { t } = useTranslation("conversation");
  if (tools.length === 0) return null;
  return (
    <section className="create-agent-card__popover-section">
      <h4>{t("blocks.createAgents.selfAuthoredTools")}</h4>
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
                  <Badge color="secondary" size="sm" variant="soft">{t("blocks.createAgents.selfAuthoredTools")}</Badge>
                  <AccordionChevron className="create-agent-card__python-tool-chevron" />
                </span>
              </Accordion.Trigger>
            </Accordion.Header>
            <Accordion.Panel className="create-agent-card__python-tool-panel">
              {tool.dependencies.length > 0 ? (
                <div className="create-agent-card__python-tool-dependencies">
                  {t("blocks.createAgents.dependencies", { items: tool.dependencies.join(", ") })}
                </div>
              ) : null}
              <pre tabIndex={0} aria-label={t("blocks.createAgents.fullCode", { name: tool.name })}>
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
  const { t } = useTranslation("conversation");
  if (agents.length === 0) return null;
  return (
    <section className="create-agent-card__popover-section">
      <h4>{t("blocks.createAgents.subAgents")}</h4>
      <div className="create-agent-card__popover-list">
        {agents.map((agent) => (
          <div className="create-agent-card__popover-item" key={agent.id}>
            <div className="create-agent-card__popover-item-heading">
              <strong>{agent.id}</strong>
              <Badge color="secondary" size="sm" variant="soft">
                {t(`blocks.createAgents.agentTypes.${agent.type}`, { defaultValue: agent.type })}
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
  const { t } = useTranslation("conversation");
  const metric = (
    <button
      className="create-agent-card__resource-metric"
      type="button"
      disabled={count === 0}
      aria-label={t("blocks.createAgents.itemCount", { label, count })}
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
  const { t } = useTranslation("conversation");
  const fallbackLabels = useMemo(() => ({
    tool: t("blocks.createAgents.sourceLabels.tool"),
    knowledge: t("blocks.createAgents.sourceLabels.knowledge"),
    skillCenter: t("blocks.createAgents.sourceLabels.skillCenter"),
    unknownSource: t("blocks.createAgents.sourceLabels.unknown"),
    unnamedResource: t("blocks.createAgents.unnamedResource"),
    unnamedAgent: t("blocks.createAgents.unnamedAgent"),
  }), [t]);
  const data = useMemo(
    () => parseCollectedResources(response, fallbackLabels),
    [fallbackLabels, response],
  );
  const groups = useMemo(() => RESOURCE_CATEGORIES.map((value) => {
    const group = filterCollectedResourcesByCategory(data, value);
    return {
      value,
      label: t(`blocks.createAgents.categories.${value}`),
      ...group,
      searchKeywords: [...new Set(
        group.sources.flatMap((source) => source.searchKeywords),
      )],
    };
  }), [data, t]);
  const failed = status === "failed";
  const error = failed ? toolResponseError(response) : "";

  return (
    <section className="create-agent-tool-card" aria-label={t("blocks.createAgents.collectionAria")}>
      {status === "running" ? (
        <LoadingRows label={t("blocks.createAgents.retrieving")} />
      ) : failed ? (
        <div className="create-agent-card__message is-error" role="alert">
          <span className="create-agent-card__message-title">{t("blocks.createAgents.retrievalFailed")}</span>
          <span>{error || t("blocks.createAgents.checkConfig")}</span>
        </div>
      ) : (
        <Accordion.Root
          key={data.collectionId || "collected-resources"}
          className="create-agent-card__accordion"
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
                      {group.sources.length === 0
                        ? group.value === "skill_hub" ? t("blocks.createAgents.notSearched") : t("blocks.createAgents.notConfigured")
                        : group.resources.length}
                    </Badge>
                    <AccordionChevron className="create-agent-card__accordion-chevron" />
                  </span>
                </Accordion.Trigger>
              </Accordion.Header>
              <Accordion.Panel className="create-agent-card__accordion-content">
                <div
                  className="create-agent-card__accordion-scroll"
                  role="region"
                  aria-label={t("blocks.createAgents.resourceList", { label: group.label })}
                  tabIndex={0}
                >
                  {group.value === "skill_hub" && group.searchKeywords.length > 0 ? (
                    <div className="create-agent-card__search-keywords">
                      <span>{t("blocks.createAgents.searchKeywords")}</span>
                      <span>{group.searchKeywords.join("、")}</span>
                    </div>
                  ) : null}
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
                      <p>
                        {group.sources.length === 0
                          ? group.value === "skill_hub"
                            ? t("blocks.createAgents.skillHubSkipped")
                            : t("blocks.createAgents.sourceSkipped", { label: group.label })
                          : t("blocks.createAgents.noResources")}
                      </p>
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
  const { t } = useTranslation("conversation");
  const fallbackLabels = useMemo(() => ({
    tool: t("blocks.createAgents.sourceLabels.tool"),
    knowledge: t("blocks.createAgents.sourceLabels.knowledge"),
    skillCenter: t("blocks.createAgents.sourceLabels.skillCenter"),
    unknownSource: t("blocks.createAgents.sourceLabels.unknown"),
    unnamedResource: t("blocks.createAgents.unnamedResource"),
    unnamedAgent: t("blocks.createAgents.unnamedAgent"),
  }), [t]);
  const data = useMemo(
    () => parseCreatedAgents(args, response, fallbackLabels),
    [args, fallbackLabels, response],
  );
  const topLevelError = status === "failed" ? toolResponseError(response) : "";

  return (
    <section className="create-agent-tool-card is-agent-results" aria-label={t("blocks.createAgents.resultAria")}>
      {topLevelError ? (
        <div className="create-agent-card__message is-error" role="alert">
          <span className="create-agent-card__message-title">{t("blocks.createAgents.creationFailed")}</span>
          <span>{topLevelError}</span>
        </div>
      ) : null}

      {data.agents.length > 0 ? (
        <div className="create-agent-card__agent-grid">
          {data.agents.map((agent) => {
            const agentStatus = status === "failed" ? "failed" : agent.status;
            const agentError = agent.error || (agentStatus === "failed" && topLevelError);
            const toolCount = agent.builtinTools.length + agent.pythonTools.length;
            return (
              <ResourceCard
                className={`create-agent-card__agent-card${agentError ? " is-error" : ""}`}
                key={agent.name}
              >
                <ResourceCardHeader
                  leading={<ResourceIdentityMark seed={agent.name} />}
                  title={agent.name}
                  titleText={agent.name}
                  status={(
                    <Badge color="secondary" size="sm" variant="soft">
                      {t(`blocks.createAgents.agentTypes.${agent.rootType}`, { defaultValue: agent.rootType })}
                    </Badge>
                  )}
                />
                {agent.description ? (
                  <ResourceCardDescription>{agent.description}</ResourceCardDescription>
                ) : null}
                {agentError ? (
                  <div className="create-agent-card__agent-result is-error" role="alert">
                    {agentError}
                  </div>
                ) : null}
                <div className="create-agent-card__agent-resources" aria-label={t("blocks.createAgents.agentResources", { name: agent.name })}>
                  <ResourceMetric
                    label={t("blocks.createAgents.skill")}
                    count={agent.skills.length}
                    icon={<ToolsSkills aria-hidden="true" />}
                  >
                    <AgentResourceList label={t("blocks.createAgents.skill")} resources={agent.skills} />
                  </ResourceMetric>
                  <ResourceMetric
                    label={t("blocks.createAgents.knowledgeBase")}
                    count={agent.knowledgeBases.length}
                    icon={<ResourceLibraryIcon aria-hidden="true" />}
                  >
                    <AgentResourceList label={t("blocks.createAgents.knowledgeBase")} resources={agent.knowledgeBases} />
                  </ResourceMetric>
                  <ResourceMetric
                    label={t("blocks.createAgents.toolsLabel")}
                    count={toolCount}
                    icon={<Tools aria-hidden="true" />}
                  >
                    <AgentResourceList label={t("blocks.createAgents.builtinTool")} resources={agent.builtinTools} />
                    <PythonToolList tools={agent.pythonTools} />
                  </ResourceMetric>
                  <ResourceMetric
                    label={t("blocks.createAgents.subAgents")}
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
        <LoadingRows label={t("blocks.createAgents.creating")} />
      ) : (
        <div className="create-agent-card__message">
          <span className="create-agent-card__message-title">{t("blocks.createAgents.noAgents")}</span>
          <span>{t("blocks.createAgents.noAgentResult")}</span>
        </div>
      )}
    </section>
  );
}
