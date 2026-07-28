import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Plus } from "lucide-react";

import { getRuntimeAgentInfo, getRuntimes, type CloudRuntime } from "../adk/client";
import "./MyAgents.css";

export interface MyAgentCardData {
  id: string;
  name: string;
  description: string;
  toolCount: number;
  skillCount: number;
  createdAt: string;
  runtime?: {
    runtimeId: string;
    region: string;
    currentVersion?: number | null;
  };
}

interface MyAgentSectionData {
  title: string;
  agents: MyAgentCardData[];
}

const STATIC_SECTIONS: MyAgentSectionData[] = [
  {
    title: "Codex 智能体",
    agents: [
      {
        id: "codex-code-review",
        name: "代码评审助手",
        description: "检查代码变更，定位风险并给出可以直接执行的修改建议。",
        toolCount: 7,
        skillCount: 5,
        createdAt: "2026-07-22",
      },
      {
        id: "codex-test-coverage",
        name: "测试补全助手",
        description: "分析现有测试覆盖，补充关键路径与边界场景。",
        toolCount: 5,
        skillCount: 4,
        createdAt: "2026-07-15",
      },
    ],
  },
  {
    title: "OpenClaw 智能体",
    agents: [
      {
        id: "openclaw-research",
        name: "资料研究助手",
        description: "围绕目标主题收集资料、核对来源并整理关键结论。",
        toolCount: 8,
        skillCount: 3,
        createdAt: "2026-07-21",
      },
      {
        id: "openclaw-competitor-watch",
        name: "竞品观察助手",
        description: "持续整理竞品动态，提炼产品变化与市场信号。",
        toolCount: 6,
        skillCount: 4,
        createdAt: "2026-07-12",
      },
    ],
  },
  {
    title: "Hermes 智能体",
    agents: [
      {
        id: "hermes-data-analysis",
        name: "数据分析助手",
        description: "理解业务问题，分析数据并形成结构化结论。",
        toolCount: 5,
        skillCount: 6,
        createdAt: "2026-07-20",
      },
      {
        id: "hermes-report",
        name: "报告生成助手",
        description: "根据分析结果生成简洁、完整且便于分享的报告。",
        toolCount: 4,
        skillCount: 5,
        createdAt: "2026-07-10",
      },
    ],
  },
];

const MAX_ROWS = 2;
const MIN_CARD_WIDTH = 174;
const GRID_GAP = 12;

function formatCreatedAt(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date).replace(/\//g, "-");
}

function runtimeToAgent(runtime: CloudRuntime): MyAgentCardData {
  return {
    id: runtime.runtimeId,
    name: runtime.name,
    description: runtime.name,
    toolCount: 0,
    skillCount: 0,
    createdAt: formatCreatedAt(runtime.createdAt ?? ""),
    runtime: {
      runtimeId: runtime.runtimeId,
      region: runtime.region,
      currentVersion: runtime.currentVersion,
    },
  };
}

async function loadRuntimeAgents(
  nextToken: string,
  pageSize: number,
  onList: (agents: MyAgentCardData[]) => void,
): Promise<{ nextToken: string; count: number }> {
  const page = await getRuntimes({
    scope: "mine",
    region: "all",
    pageSize,
    nextToken,
  });
  onList(page.runtimes.map(runtimeToAgent));

  void Promise.all(
    page.runtimes.map(async (runtime) => {
      try {
        const info = await getRuntimeAgentInfo(runtime.runtimeId, runtime.region);
        const agent = {
          id: runtime.runtimeId,
          name: info.name || runtime.name,
          description: info.description || runtime.name,
          toolCount: info.tools.length,
          skillCount: info.skills.length,
          createdAt: formatCreatedAt(runtime.createdAt ?? ""),
          runtime: {
            runtimeId: runtime.runtimeId,
            region: runtime.region,
            currentVersion: runtime.currentVersion,
          },
        };
        onList([agent]);
      } catch {
        // Keep the Runtime fallback card already rendered above.
      }
    }),
  );
  return { nextToken: page.nextToken, count: page.runtimes.length };
}

function AgentCard({
  agent,
  onUse,
  onViewDetails,
  connecting,
  connected,
}: {
  agent: MyAgentCardData;
  onUse?: (agent: MyAgentCardData) => Promise<void>;
  onViewDetails?: (agent: MyAgentCardData) => void;
  connecting?: boolean;
  connected?: boolean;
}) {
  return (
    <article className="my-agent-card">
      <div className="my-agent-card-content">
        <h3>{agent.name}</h3>
        <p className="my-agent-description">{agent.description}</p>
        <dl className="my-agent-meta">
          <div className="my-agent-label">
            <dt>工具</dt>
            <dd>{agent.toolCount} 个</dd>
          </div>
          <div className="my-agent-label">
            <dt>技能</dt>
            <dd>{agent.skillCount} 个</dd>
          </div>
          <div className="my-agent-created-at">
            <dt>创建时间</dt>
            <dd>{agent.createdAt}</dd>
          </div>
        </dl>
      </div>
      <div className="my-agent-actions">
        <button
          type="button"
          className={`my-agent-use${connected ? " is-connected" : ""}`}
          disabled={!agent.runtime || connecting || connected}
          aria-busy={connecting || undefined}
          onClick={() => void onUse?.(agent)}
        >
          {connecting ? (
            <>
              <span className="my-agent-use-spinner" aria-hidden="true" />
              <span>连接中</span>
            </>
          ) : connected ? "已连接" : "使用"}
        </button>
        <button
          type="button"
          className="my-agent-details"
          disabled={!agent.runtime}
          onClick={() => onViewDetails?.(agent)}
        >
          查看详情
        </button>
      </div>
    </article>
  );
}

function AgentSection({
  section,
  onCreateAgent,
  onUseAgent,
  onViewAgentDetails,
  connectingAgentId,
  connectedRuntimeId,
  loading,
  serverPagination,
  onPageSizeChange,
}: {
  section: MyAgentSectionData;
  onCreateAgent?: () => void;
  onUseAgent?: (agent: MyAgentCardData) => Promise<void>;
  onViewAgentDetails?: (agent: MyAgentCardData) => void;
  connectingAgentId?: string;
  connectedRuntimeId?: string;
  loading?: boolean;
  serverPagination?: {
    page: number;
    hasNext: boolean;
    onPrevious: () => void;
    onNext: () => void;
  };
  onPageSizeChange?: (pageSize: number) => void;
}) {
  const gridRef = useRef<HTMLDivElement>(null);
  const [columns, setColumns] = useState(1);
  const [page, setPage] = useState(1);
  const pageSize = Math.max(1, columns * MAX_ROWS - 1);
  const pageCount = Math.max(1, Math.ceil(section.agents.length / pageSize));
  const visibleAgents = useMemo(
    () => serverPagination
      ? section.agents
      : section.agents.slice((page - 1) * pageSize, page * pageSize),
    [page, pageSize, section.agents, serverPagination],
  );
  const currentPage = serverPagination?.page ?? page;

  useEffect(() => {
    const grid = gridRef.current;
    if (!grid) return;
    const updateColumns = () => {
      const width = grid.getBoundingClientRect().width;
      const nextColumns = Math.max(
        1,
        Math.floor((width + GRID_GAP) / (MIN_CARD_WIDTH + GRID_GAP)),
      );
      setColumns(nextColumns);
      onPageSizeChange?.(Math.max(1, nextColumns * MAX_ROWS - 1));
    };
    updateColumns();
    const observer = new ResizeObserver(updateColumns);
    observer.observe(grid);
    return () => observer.disconnect();
  }, [onPageSizeChange]);

  useEffect(() => {
    setPage((current) => Math.min(current, pageCount));
  }, [pageCount]);

  return (
    <section className="my-agents-section">
      <h2>{section.title}</h2>
      <div className="my-agent-grid" ref={gridRef}>
        <button
          type="button"
          className="my-agent-add"
          aria-label={`添加${section.title}`}
          disabled={!onCreateAgent}
          onClick={onCreateAgent}
        >
          <Plus aria-hidden="true" />
          <span>添加智能体</span>
        </button>
        {visibleAgents.map((agent) => (
          <AgentCard
            key={agent.id}
            agent={agent}
            onUse={onUseAgent}
            onViewDetails={onViewAgentDetails}
            connecting={agent.id === connectingAgentId}
            connected={agent.runtime?.runtimeId === connectedRuntimeId}
          />
        ))}
        {loading && (
          <div className="my-agent-loading" role="status" aria-live="polite">
            <span className="loading-gap-spinner" aria-hidden="true" />
            <span>加载中</span>
          </div>
        )}
      </div>
      <nav className="my-agent-pagination" aria-label={`${section.title}分页`}>
        <button
          type="button"
          aria-label="上一页"
          disabled={currentPage === 1 || loading}
          onClick={serverPagination?.onPrevious ?? (() => setPage(page - 1))}
        >
          ‹
        </button>
        <span>{serverPagination ? currentPage : `${page} / ${pageCount}`}</span>
        <button
          type="button"
          aria-label="下一页"
          disabled={loading || (serverPagination ? !serverPagination.hasNext : page === pageCount)}
          onClick={serverPagination?.onNext ?? (() => setPage(page + 1))}
        >
          ›
        </button>
      </nav>
    </section>
  );
}

export interface MyAgentsProps {
  onCreateAgent: () => void;
  onUseAgent: (agent: MyAgentCardData) => Promise<void>;
  onViewAgentDetails: (agent: MyAgentCardData) => void;
  connectedRuntimeId?: string;
}

export function MyAgents({
  onCreateAgent,
  onUseAgent,
  onViewAgentDetails,
  connectedRuntimeId = "",
}: MyAgentsProps) {
  const [runtimeAgents, setRuntimeAgents] = useState<MyAgentCardData[]>([]);
  const [loadingRuntimes, setLoadingRuntimes] = useState(true);
  const [runtimePage, setRuntimePage] = useState(1);
  const [runtimeNextToken, setRuntimeNextToken] = useState("");
  const [runtimePageSize, setRuntimePageSize] = useState(0);
  const [connectingAgentId, setConnectingAgentId] = useState("");
  const runtimePageSizeRef = useRef(0);
  const runtimePageTokensRef = useRef([""]);
  const runtimeRequestRef = useRef(0);

  const updateRuntimePageSize = useCallback((pageSize: number) => {
    if (runtimePageSizeRef.current === pageSize) return;
    runtimePageSizeRef.current = pageSize;
    setRuntimePageSize(pageSize);
  }, []);

  const fetchRuntimePage = useCallback((page: number, token: string, pageSize: number) => {
    const requestId = ++runtimeRequestRef.current;
    setLoadingRuntimes(true);
    return loadRuntimeAgents(token, pageSize, (agents) => {
      if (runtimeRequestRef.current !== requestId) return;
      if (page > 1 && agents.length === 0) return;
      setRuntimeAgents((current) => {
        if (agents.length !== 1 || current.length === 0) return agents;
        return current.map((agent) => agent.id === agents[0].id ? agents[0] : agent);
      });
    })
      .then(({ nextToken, count }) => {
        if (runtimeRequestRef.current !== requestId) return;
        if (page > 1 && count === 0) {
          setRuntimeNextToken("");
          return;
        }
        setRuntimePage(page);
        setRuntimeNextToken(nextToken);
      })
      .catch(() => {
        if (runtimeRequestRef.current !== requestId) return;
      })
      .finally(() => {
        if (runtimeRequestRef.current === requestId) setLoadingRuntimes(false);
      });
  }, []);

  useEffect(() => {
    if (runtimePageSize === 0) return;
    runtimePageTokensRef.current = [""];
    setRuntimeNextToken("");
    void fetchRuntimePage(1, "", runtimePageSize);
    return () => {
      runtimeRequestRef.current += 1;
    };
  }, [fetchRuntimePage, runtimePageSize]);

  const nextRuntimePage = () => {
    if (!runtimeNextToken) return;
    runtimePageTokensRef.current[runtimePage] = runtimeNextToken;
    void fetchRuntimePage(runtimePage + 1, runtimeNextToken, runtimePageSize);
  };

  const previousRuntimePage = () => {
    if (runtimePage <= 1) return;
    const previousPage = runtimePage - 1;
    const previousToken = runtimePageTokensRef.current[previousPage - 1] ?? "";
    void fetchRuntimePage(previousPage, previousToken, runtimePageSize);
  };

  const useAgent = useCallback(async (agent: MyAgentCardData) => {
    if (connectingAgentId) return;
    setConnectingAgentId(agent.id);
    try {
      await onUseAgent(agent);
    } finally {
      setConnectingAgentId("");
    }
  }, [connectingAgentId, onUseAgent]);

  const sections = useMemo<MyAgentSectionData[]>(
    () => [
      { title: "通用智能体", agents: runtimeAgents },
      ...STATIC_SECTIONS,
    ],
    [runtimeAgents],
  );

  return (
    <div className="my-agents-page">
      {sections.map((section, index) => (
        <AgentSection
          section={section}
          key={section.title}
          onCreateAgent={index === 0 ? onCreateAgent : undefined}
          onUseAgent={useAgent}
          onViewAgentDetails={onViewAgentDetails}
          connectingAgentId={connectingAgentId}
          connectedRuntimeId={connectedRuntimeId}
          loading={index === 0 && loadingRuntimes}
          onPageSizeChange={index === 0 ? updateRuntimePageSize : undefined}
          serverPagination={index === 0 ? {
            page: runtimePage,
            hasNext: Boolean(runtimeNextToken),
            onPrevious: previousRuntimePage,
            onNext: nextRuntimePage,
          } : undefined}
        />
      ))}
    </div>
  );
}
