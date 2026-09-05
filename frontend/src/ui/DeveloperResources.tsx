import { ArrowUpRight } from "@openai/apps-sdk-ui/components/Icon";
import { TextLink } from "@openai/apps-sdk-ui/components/TextLink";
import type { CloudProvider } from "../adk/cloudProvider";
import articleAgentWorkflow from "../assets/developer-resources/article-agent-workflow.webp";
import articleToolDebugging from "../assets/developer-resources/article-tool-debugging.webp";
import showcaseA2ui from "../assets/developer-resources/showcase-a2ui.webp";
import showcaseCustomerService from "../assets/developer-resources/showcase-customer-service.webp";
import showcaseMultimodal from "../assets/developer-resources/showcase-multimodal.webp";
import showcaseResearchAssistant from "../assets/developer-resources/showcase-research-assistant.webp";
import showcaseWebSearch from "../assets/developer-resources/showcase-web-search.webp";
import { agentKitLinks } from "./agentKitLinks";
import {
  ResourcePageHeader,
  ResourcePageShell,
} from "./ResourceCollection";
import "./DeveloperResources.css";

const RESOURCE_SECTIONS = [
  {
    id: "documentation",
    title: "相关链接",
    description: "查看开发文档与 AgentKit 常用入口",
  },
  {
    id: "best-practices",
    title: "最佳实践",
    description: "参考开发、调试与部署经验",
  },
  {
    id: "showcases",
    title: "Showcases",
    description: "探索 AgentKit 应用案例",
  },
] as const;

const VEADK_DOCUMENTATION_URL = "https://volcengine.github.io/veadk-python/";
const AGENTKIT_CLI_DOCUMENTATION_URL =
  "https://volcengine.github.io/agentkit-sdk-python/content/2.agentkit-cli/1.overview.html";

const BEST_PRACTICE_ARTICLES = [
  {
    id: "veadk-development",
    title: "使用 VeADK 开发并部署智能体",
    description: "使用 VeADK 构建 Agent，并部署至 AgentKit 智能体运行时。",
    meta: "AgentKit · VeADK",
    image: articleAgentWorkflow,
    href: "https://docs.volcengine.com/docs/86681/2155817?lang=zh",
  },
  {
    id: "agentkit-cli-development",
    title: "使用 AgentKit CLI 开发并部署智能体",
    description: "通过 AgentKit CLI 创建项目、调试 Agent，并完成部署。",
    meta: "AgentKit · CLI",
    image: articleToolDebugging,
    href: "https://docs.volcengine.com/docs/86681/1844871?lang=zh",
  },
] as const;

const SHOWCASES = [
  {
    id: "research-assistant",
    title: "多智能体研究助手",
    description: "由多个专业 Agent 协同完成资料检索、分析和结论整理。",
    image: showcaseResearchAssistant,
    href: "https://github.com/volcengine/veadk-python/tree/main/examples/06_multi_agent",
  },
  {
    id: "multimodal-analysis",
    title: "多模态内容分析",
    description: "在统一会话中理解图片、文档和视频内容。",
    image: showcaseMultimodal,
    href: "https://github.com/volcengine/veadk-python/tree/main/examples/multimodal_agent",
  },
  {
    id: "customer-service",
    title: "智能客服工作台",
    description: "结合知识检索与工具调用处理复杂的客户服务任务。",
    image: showcaseCustomerService,
    href: "https://github.com/volcengine/veadk-python/tree/main/examples/basic-app",
  },
  {
    id: "web-search",
    title: "联网搜索 Agent",
    description: "检索实时网页内容，并将信息整理为可追溯的回答。",
    image: showcaseWebSearch,
    href: "https://github.com/volcengine/veadk-python/tree/main/examples/04_web_search",
  },
  {
    id: "a2ui-app",
    title: "A2UI 交互应用",
    description: "让 Agent 根据任务过程生成可交互的前端界面。",
    image: showcaseA2ui,
    href: "https://github.com/volcengine/veadk-python/tree/main/examples/a2ui_agent",
  },
] as const;

export function DeveloperResources({
  cloudProvider,
}: {
  cloudProvider: CloudProvider;
}) {
  const links = agentKitLinks(cloudProvider);

  return (
    <ResourcePageShell
      className="developer-resources"
      aria-label="开发者资源"
    >
      <ResourcePageHeader title="开发者资源" />

      <div className="developer-resources__content">
        {RESOURCE_SECTIONS.map((section) => (
          <section
            className="developer-resources__section"
            key={section.id}
            aria-labelledby={`developer-resources-${section.id}`}
          >
            <header className="developer-resources__section-header">
              <h2 id={`developer-resources-${section.id}`}>
                {section.title}
              </h2>
              <p>{section.description}</p>
            </header>
            {section.id === "documentation" ? (
              <ul className="developer-resources__links">
                <li>
                  <TextLink
                    className="developer-resources__link"
                    primary
                    underline
                    href={VEADK_DOCUMENTATION_URL}
                    target="_blank"
                    rel="noreferrer"
                  >
                    VeADK 文档
                    <ArrowUpRight aria-hidden="true" />
                  </TextLink>
                </li>
                <li>
                  <TextLink
                    className="developer-resources__link"
                    primary
                    underline
                    href={AGENTKIT_CLI_DOCUMENTATION_URL}
                    target="_blank"
                    rel="noreferrer"
                  >
                    AgentKit CLI 文档
                    <ArrowUpRight aria-hidden="true" />
                  </TextLink>
                </li>
                <li>
                  <TextLink
                    className="developer-resources__link"
                    primary
                    underline
                    href={links.docs}
                    target="_blank"
                    rel="noreferrer"
                  >
                    AgentKit 平台文档
                    <ArrowUpRight aria-hidden="true" />
                  </TextLink>
                </li>
                <li>
                  <TextLink
                    className="developer-resources__link"
                    primary
                    underline
                    href={links.console}
                    target="_blank"
                    rel="noreferrer"
                  >
                    AgentKit 控制台
                    <ArrowUpRight aria-hidden="true" />
                  </TextLink>
                </li>
              </ul>
            ) : section.id === "best-practices" ? (
              <div className="developer-resources__articles">
                {BEST_PRACTICE_ARTICLES.map((article) => (
                  <a
                    className="developer-resources__article"
                    href={article.href}
                    key={article.id}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <img
                      src={article.image}
                      alt={`${article.title}文章封面`}
                      loading="lazy"
                    />
                    <span className="developer-resources__article-copy">
                      <strong>{article.title}</strong>
                      <span>{article.description}</span>
                      <small>{article.meta}</small>
                    </span>
                  </a>
                ))}
              </div>
            ) : section.id === "showcases" ? (
              <div className="developer-resources__showcases">
                {SHOWCASES.map((showcase) => (
                  <a
                    className="developer-resources__showcase"
                    href={showcase.href}
                    key={showcase.id}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <span className="developer-resources__showcase-media">
                      <img
                        src={showcase.image}
                        alt={`${showcase.title}界面预览`}
                        loading="lazy"
                      />
                    </span>
                    <strong>{showcase.title}</strong>
                    <span>{showcase.description}</span>
                  </a>
                ))}
              </div>
            ) : null}
          </section>
        ))}
      </div>
    </ResourcePageShell>
  );
}
