import { useDeferredValue, useMemo, useState, type SVGProps } from "react";

import { GitHubLogo } from "./GitHubLogo";
import "./Applications.css";

interface ApplicationsProps {
  onOpenGitHub: () => void;
}

const CATEGORIES = [{ id: "development", label: "研发" }] as const;
const APPLICATIONS = [
  {
    id: "github",
    name: "AgentKit Runtime 持续交付",
    description: "为您的仓库添加持续交付到 AgentKit Runtime 的自动化工作流。",
  },
] as const;

function SearchIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <circle cx="10.8" cy="10.8" r="6.2" stroke="currentColor" strokeWidth="1.7" />
      <path d="m15.4 15.4 4 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function Applications({ onOpenGitHub }: ApplicationsProps) {
  const [activeCategory, setActiveCategory] = useState("development");
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const visibleApplications = useMemo(() => {
    const normalized = deferredQuery.trim().toLocaleLowerCase();
    return APPLICATIONS.filter((application) =>
      !normalized || `${application.name} ${application.description}`.toLocaleLowerCase().includes(normalized)
    );
  }, [deferredQuery]);

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
        {CATEGORIES.map((category) => (
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

      <section className="applications-results" aria-label="研发自动化列表">
        {visibleApplications.length ? (
          <div className="applications-grid">
            {visibleApplications.map((application) => (
              <button
                type="button"
                className="application-card"
                key={application.id}
                onClick={onOpenGitHub}
                aria-label={`打开${application.name}`}
              >
                <GitHubLogo className="application-card-icon" />
                <div className="application-card-copy">
                  <h2>{application.name}</h2>
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
