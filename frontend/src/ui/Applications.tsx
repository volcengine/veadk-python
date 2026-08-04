import { useDeferredValue, useMemo, useState, type SVGProps } from "react";

import "./Applications.css";

interface ApplicationsProps {
  onOpenGitHub: () => void;
}

const CATEGORIES = [{ id: "development", label: "研发" }] as const;
const APPLICATIONS = [
  {
    id: "github",
    name: "GitHub 集成",
    description: "连接代码仓库，通过 Pull Request 配置 AgentKit Runtime 持续发布。",
    category: "研发",
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

function RepositoryFlowIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <circle cx="7" cy="5" r="2" />
      <circle cx="17" cy="8" r="2" />
      <circle cx="7" cy="19" r="2" />
      <path d="M7 7v10M9 8h4a4 4 0 0 1 4 4v-2" />
    </svg>
  );
}

function ArrowIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path d="m6 3.5 4.5 4.5L6 12.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
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
          <h1>应用</h1>
          <p>连接研发工具，为智能体扩展自动化工作流</p>
        </div>
        <label className="applications-search">
          <SearchIcon />
          <input
            type="search"
            aria-label="搜索应用"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索应用"
          />
        </label>
      </header>

      <nav className="applications-categories" aria-label="应用分类">
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

      <section className="applications-results" aria-label="研发应用列表">
        {visibleApplications.length ? (
          <div className="applications-grid">
            {visibleApplications.map((application) => (
              <article className="application-card" key={application.id}>
                <div className="application-card-body">
                  <div className="application-card-icon"><RepositoryFlowIcon /></div>
                  <div className="application-card-copy">
                    <div className="application-card-heading">
                      <h2>{application.name}</h2>
                      <span>{application.category}</span>
                    </div>
                    <p>{application.description}</p>
                  </div>
                </div>
                <button type="button" onClick={onOpenGitHub}>
                  <span>查看集成</span>
                  <ArrowIcon />
                </button>
              </article>
            ))}
          </div>
        ) : (
          <div className="applications-empty" role="status">
            <RepositoryFlowIcon />
            <h2>没有匹配的应用</h2>
            <p>请尝试搜索其他名称</p>
          </div>
        )}
      </section>
    </div>
  );
}

