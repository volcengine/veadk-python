import { ArrowUpRight } from "@openai/apps-sdk-ui/components/Icon";
import { TextLink } from "@openai/apps-sdk-ui/components/TextLink";
import { useTranslation } from "react-i18next";
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
    titleKey: "developerResources.sections.documentation.title",
    descriptionKey: "developerResources.sections.documentation.description",
  },
  {
    id: "best-practices",
    titleKey: "developerResources.sections.bestPractices.title",
    descriptionKey: "developerResources.sections.bestPractices.description",
  },
  {
    id: "showcases",
    titleKey: "developerResources.sections.showcases.title",
    descriptionKey: "developerResources.sections.showcases.description",
  },
] as const;

const VEADK_DOCUMENTATION_URL = "https://volcengine.github.io/veadk-python/";
const AGENTKIT_CLI_DOCUMENTATION_URL =
  "https://volcengine.github.io/agentkit-sdk-python/content/2.agentkit-cli/1.overview.html";

const BEST_PRACTICE_ARTICLES = [
  {
    id: "veadk-development",
    titleKey: "developerResources.articles.veadkDevelopment.title",
    descriptionKey: "developerResources.articles.veadkDevelopment.description",
    meta: "AgentKit · VeADK",
    image: articleAgentWorkflow,
    href: "https://docs.volcengine.com/docs/86681/2155817?lang=zh",
  },
  {
    id: "agentkit-cli-development",
    titleKey: "developerResources.articles.cliDevelopment.title",
    descriptionKey: "developerResources.articles.cliDevelopment.description",
    meta: "AgentKit · CLI",
    image: articleToolDebugging,
    href: "https://docs.volcengine.com/docs/86681/1844871?lang=zh",
  },
] as const;

const SHOWCASES = [
  {
    id: "research-assistant",
    titleKey: "developerResources.showcases.researchAssistant.title",
    descriptionKey: "developerResources.showcases.researchAssistant.description",
    image: showcaseResearchAssistant,
    href: "https://github.com/volcengine/veadk-python/tree/main/examples/06_multi_agent",
  },
  {
    id: "multimodal-analysis",
    titleKey: "developerResources.showcases.multimodalAnalysis.title",
    descriptionKey: "developerResources.showcases.multimodalAnalysis.description",
    image: showcaseMultimodal,
    href: "https://github.com/volcengine/veadk-python/tree/main/examples/multimodal_agent",
  },
  {
    id: "customer-service",
    titleKey: "developerResources.showcases.customerService.title",
    descriptionKey: "developerResources.showcases.customerService.description",
    image: showcaseCustomerService,
    href: "https://github.com/volcengine/veadk-python/tree/main/examples/basic-app",
  },
  {
    id: "web-search",
    titleKey: "developerResources.showcases.webSearch.title",
    descriptionKey: "developerResources.showcases.webSearch.description",
    image: showcaseWebSearch,
    href: "https://github.com/volcengine/veadk-python/tree/main/examples/04_web_search",
  },
  {
    id: "a2ui-app",
    titleKey: "developerResources.showcases.a2uiApp.title",
    descriptionKey: "developerResources.showcases.a2uiApp.description",
    image: showcaseA2ui,
    href: "https://github.com/volcengine/veadk-python/tree/main/examples/a2ui_agent",
  },
] as const;

export function DeveloperResources({
  cloudProvider,
}: {
  cloudProvider: CloudProvider;
}) {
  const { t } = useTranslation("workspaceTools");
  const links = agentKitLinks(cloudProvider);

  return (
    <ResourcePageShell
      className="developer-resources"
      aria-label={t("developerResources.title")}
    >
      <ResourcePageHeader title={t("developerResources.title")} />

      <div className="developer-resources__content">
        {RESOURCE_SECTIONS.map((section) => (
          <section
            className="developer-resources__section"
            key={section.id}
            aria-labelledby={`developer-resources-${section.id}`}
          >
            <header className="developer-resources__section-header">
              <h2 id={`developer-resources-${section.id}`}>
                {t(section.titleKey)}
              </h2>
              <p>{t(section.descriptionKey)}</p>
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
                    {t("developerResources.links.veadkDocs")}
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
                    {t("developerResources.links.cliDocs")}
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
                    {t("developerResources.links.platformDocs")}
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
                    {t("developerResources.links.console")}
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
                      alt={t("developerResources.articles.coverAlt", {
                        title: t(article.titleKey),
                      })}
                      loading="lazy"
                    />
                    <span className="developer-resources__article-copy">
                      <strong>{t(article.titleKey)}</strong>
                      <span>{t(article.descriptionKey)}</span>
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
                        alt={t("developerResources.showcases.previewAlt", {
                          title: t(showcase.titleKey),
                        })}
                        loading="lazy"
                      />
                    </span>
                    <strong>{t(showcase.titleKey)}</strong>
                    <span>{t(showcase.descriptionKey)}</span>
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
