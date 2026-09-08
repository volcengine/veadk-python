import { useDeferredValue, useMemo, useState, type SVGProps } from "react";
import { useTranslation } from "react-i18next";

import {
  AUTOMATION_CATEGORIES,
  AUTOMATIONS,
  type AutomationId,
} from "../automations/registry";
import { isCodingAgentsAutomationAvailable } from "../automations/codingAgents";
import feishuLogo from "../assets/feishu-logo.svg";
import { GitHubLogo } from "./GitHubLogo";
import "./Applications.css";

interface ApplicationsProps {
  onOpen: (automation: AutomationId) => void;
}

export type ApplicationId = AutomationId;

function SearchIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <circle cx="10.8" cy="10.8" r="6.2" stroke="currentColor" strokeWidth="1.7" />
      <path d="m15.4 15.4 4 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function CodingAgentsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 36 36" fill="none" aria-hidden="true" {...props}>
      <rect x="3.5" y="5" width="18" height="18" rx="5" fill="currentColor" opacity="0.1" />
      <rect x="3.5" y="5" width="18" height="18" rx="5" stroke="currentColor" strokeWidth="1.6" />
      <path d="m9.2 11.2-2.8 2.7 2.8 2.7M12.1 17.4h4.3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="26.5" cy="12" r="3" fill="hsl(var(--background))" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="27" cy="26.5" r="3" fill="hsl(var(--background))" stroke="currentColor" strokeWidth="1.6" />
      <path d="M21.5 12h2M19.3 21l5.6 3.8M27 15v8.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function WebsiteIntegrationIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 36 36" fill="none" aria-hidden="true" {...props}>
      <rect x="3.5" y="5" width="22" height="18" rx="4" stroke="currentColor" strokeWidth="1.6" />
      <path d="M4.5 10h20M9 7.5h.1M12 7.5h.1" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M18 18.5c0-3 2.5-5.5 5.5-5.5h3c3 0 5.5 2.5 5.5 5.5v5c0 3-2.5 5.5-5.5 5.5H25l-4 3v-3.6a5.5 5.5 0 0 1-3-4.9v-5Z" fill="hsl(var(--background))" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M22 19.5h6M22 23h4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function Applications({ onOpen }: ApplicationsProps) {
  const { t } = useTranslation("automations");
  const [activeCategory, setActiveCategory] = useState("development");
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const visibleApplications = useMemo(() => {
    const normalized = deferredQuery.trim().toLocaleLowerCase();
    return AUTOMATIONS.filter(
      (application) => application.category === activeCategory,
    ).filter((application) =>
      !normalized || `${t(`cards.${application.id}.name`)} ${t(`cards.${application.id}.description`)}`.toLocaleLowerCase().includes(normalized),
    );
  }, [activeCategory, deferredQuery, t]);
  const activeCategoryLabel = AUTOMATION_CATEGORIES.find(
    (category) => category.id === activeCategory,
  )?.id;
  const codingAgentsAvailable = isCodingAgentsAutomationAvailable(window.location.hostname);

  return (
    <div className="applications-page">
      <header className="applications-header">
        <div>
          <h1>{t("title")}</h1>
          <p>{t("description")}</p>
        </div>
        <label className="applications-search">
          <SearchIcon />
          <input
            type="search"
            aria-label={t("search")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("search")}
          />
        </label>
      </header>

      <nav className="applications-categories" aria-label={t("categoriesLabel")}>
        {AUTOMATION_CATEGORIES.map((category) => (
          <button
            type="button"
            key={category.id}
            className={activeCategory === category.id ? "is-active" : ""}
            aria-pressed={activeCategory === category.id}
            onClick={() => setActiveCategory(category.id)}
          >
            {t(`categories.${category.id}`)}
          </button>
        ))}
      </nav>

      <section className="applications-results" aria-label={t("resultsLabel", { category: t(`categories.${activeCategoryLabel}`) })}>
        {visibleApplications.length ? (
          <div className="applications-grid">
            {visibleApplications.map((application) => {
              const disabled = application.id === "coding-agents" && !codingAgentsAvailable;
              const tooltipId = disabled ? "coding-agents-local-only-tooltip" : undefined;

              return (
                <div
                  className={`application-card-wrap${disabled ? " is-disabled" : ""}`}
                  key={application.id}
                  tabIndex={disabled ? 0 : undefined}
                  aria-describedby={tooltipId}
                >
                  <button
                    type="button"
                    className="application-card"
                    onClick={() => onOpen(application.id)}
                    aria-label={t("open", { name: t(`cards.${application.id}.name`) })}
                    disabled={disabled}
                  >
                    {application.icon === "feishu" ? (
                      <img
                        className="application-card-icon application-card-brand-icon"
                        src={feishuLogo}
                        alt=""
                        aria-hidden="true"
                      />
                    ) : application.icon === "coding-agents" ? (
                      <CodingAgentsIcon className="application-card-icon" />
                    ) : application.icon === "website-integration" ? (
                      <WebsiteIntegrationIcon className="application-card-icon" />
                    ) : (
                      <GitHubLogo className="application-card-icon" />
                    )}
                    <div className="application-card-copy">
                      <div className="application-card-title">
                        <h2>{t(`cards.${application.id}.name`)}</h2>
                        {application.badge ? (
                          <span className={`application-card-badge is-${application.badgeTone || "default"}`}>{t(`cards.${application.id}.badge`, { defaultValue: application.badge })}</span>
                        ) : null}
                      </div>
                      <p>{t(`cards.${application.id}.description`)}</p>
                    </div>
                  </button>
                  {disabled ? (
                    <span id={tooltipId} className="application-card-tooltip" role="tooltip">
                      {t("localOnly")}
                    </span>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="applications-empty" role="status">
            <SearchIcon />
            <h2>{t("emptyTitle")}</h2>
            <p>{t("emptyDescription")}</p>
          </div>
        )}
      </section>
    </div>
  );
}
