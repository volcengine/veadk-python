import { useDeferredValue, useMemo, useState, type SVGProps } from "react";

import {
  AUTOMATION_CATEGORIES,
  AUTOMATIONS,
  type AutomationId,
} from "../automations/registry";
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

export function Applications({ onOpen }: ApplicationsProps) {
  const [activeCategory, setActiveCategory] = useState("development");
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const visibleApplications = useMemo(() => {
    const normalized = deferredQuery.trim().toLocaleLowerCase();
    return AUTOMATIONS.filter(
      (application) => application.category === activeCategory,
    ).filter((application) =>
      !normalized || `${application.name} ${application.description}`.toLocaleLowerCase().includes(normalized),
    );
  }, [activeCategory, deferredQuery]);
  const activeCategoryLabel = AUTOMATION_CATEGORIES.find(
    (category) => category.id === activeCategory,
  )?.label;

  return (
    <div className="applications-page">
      <header className="applications-header">
        <div>
          <h1>自动化</h1>
          <p>连接研发工具，为智能体扩展自动化工作流</p>
        </div>
        <label className="applications-search">
          <SearchIcon />
          <input
            type="search"
            aria-label="搜索自动化"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索自动化"
          />
        </label>
      </header>

      <nav className="applications-categories" aria-label="自动化分类">
        {AUTOMATION_CATEGORIES.map((category) => (
          <button
            type="button"
            key={category.id}
            className={activeCategory === category.id ? "is-active" : ""}
            aria-pressed={activeCategory === category.id}
            onClick={() => setActiveCategory(category.id)}
          >
            {category.label}
          </button>
        ))}
      </nav>

      <section className="applications-results" aria-label={`${activeCategoryLabel}自动化列表`}>
        {visibleApplications.length ? (
          <div className="applications-grid">
            {visibleApplications.map((application) => (
              <button
                type="button"
                className="application-card"
                key={application.id}
                onClick={() => onOpen(application.id)}
                aria-label={`打开${application.name}`}
              >
                {application.icon === "feishu" ? (
                  <img
                    className="application-card-icon application-card-brand-icon"
                    src={feishuLogo}
                    alt=""
                    aria-hidden="true"
                  />
                ) : (
                  <GitHubLogo className="application-card-icon" />
                )}
                <div className="application-card-copy">
                  <div className="application-card-title">
                    <h2>{application.name}</h2>
                    {application.badge ? (
                      <span className="application-card-badge">{application.badge}</span>
                    ) : null}
                  </div>
                  <p>{application.description}</p>
                </div>
              </button>
            ))}
          </div>
        ) : (
          <div className="applications-empty" role="status">
            <SearchIcon />
            <h2>没有匹配的自动化</h2>
            <p>请尝试搜索其他名称</p>
          </div>
        )}
      </section>
    </div>
  );
}
