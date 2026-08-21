import { useEffect, useMemo, useState, type FormEvent, type SVGProps } from "react";
import { Button, CopyButton } from "@openai/apps-sdk-ui/components/Button";
import { EmptyMessage } from "@openai/apps-sdk-ui/components/EmptyMessage";
import { Input } from "@openai/apps-sdk-ui/components/Input";
import { Select, type Option } from "@openai/apps-sdk-ui/components/Select";

import { getRuntimes, probeRuntimeApps, type CloudRuntime } from "../../adk/client";
import {
  createWebsiteIntegration,
  deleteWebsiteIntegration,
  listWebsiteIntegrations,
  type WebsiteIntegrationRecord,
} from "../../adk/websiteIntegration";
import "./WebsiteIntegration.css";

interface WebsiteIntegrationProps {
  onBack: () => void;
}

interface RuntimeOption extends Option {
  runtime: CloudRuntime;
}

function BackIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path d="m9.8 3.5-4.5 4.5 4.5 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function WebsiteIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden="true" {...props}>
      <rect x="3.5" y="5" width="20" height="17" rx="3.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M4.5 10h18M8.5 7.5h.1M11.5 7.5h.1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M17 18.5a5 5 0 0 1 5-5h1.5a5 5 0 0 1 5 5V23a5 5 0 0 1-5 5H22l-3.5 2.5v-3.3A5 5 0 0 1 17 23v-4.5Z" fill="hsl(var(--background))" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M21 19h4M21 22.5h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function formatCreatedAt(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function loadAllRuntimes(signal: AbortSignal): Promise<CloudRuntime[]> {
  const runtimes: CloudRuntime[] = [];
  let nextToken = "";
  for (let page = 0; page < 10; page += 1) {
    const result = await getRuntimes({
      nextToken: nextToken || undefined,
      pageSize: 100,
      region: "all",
      scope: "all",
    });
    if (signal.aborted) return [];
    runtimes.push(...result.runtimes);
    nextToken = result.nextToken;
    if (!nextToken) break;
  }
  return runtimes;
}

export function WebsiteIntegration({ onBack }: WebsiteIntegrationProps) {
  const [integrations, setIntegrations] = useState<WebsiteIntegrationRecord[]>([]);
  const [runtimes, setRuntimes] = useState<CloudRuntime[]>([]);
  const [selectedRuntime, setSelectedRuntime] = useState("");
  const [selectedIntegrationId, setSelectedIntegrationId] = useState("");
  const [domain, setDomain] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    Promise.all([
      listWebsiteIntegrations(controller.signal),
      loadAllRuntimes(controller.signal),
    ])
      .then(([integrationItems, runtimeItems]) => {
        if (controller.signal.aborted) return;
        setIntegrations(integrationItems);
        setRuntimes(runtimeItems);
        setSelectedIntegrationId(integrationItems[0]?.id ?? "");
        const firstRuntime = runtimeItems[0];
        if (firstRuntime) setSelectedRuntime(`${firstRuntime.region}::${firstRuntime.runtimeId}`);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "加载网站集成失败");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const runtimeOptions = useMemo<RuntimeOption[]>(() => runtimes.map((runtime) => ({
    value: `${runtime.region}::${runtime.runtimeId}`,
    label: runtime.name || runtime.runtimeId,
    description: `${runtime.region} · ${runtime.status}`,
    runtime,
  })), [runtimes]);
  const runtimeByValue = useMemo(
    () => new Map(runtimeOptions.map((option) => [option.value, option.runtime])),
    [runtimeOptions],
  );
  const selectedIntegration = integrations.find(
    (integration) => integration.id === selectedIntegrationId,
  ) ?? integrations[0];
  const embedSnippet = selectedIntegration
    ? `<script async src="${window.location.origin}/website-integration.js" data-token="${selectedIntegration.token}"></script>`
    : "";

  async function addIntegration(event: FormEvent) {
    event.preventDefault();
    const runtime = runtimeByValue.get(selectedRuntime);
    if (!runtime || !domain.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      const apps = await probeRuntimeApps(runtime.runtimeId, runtime.region, {
        retryProbe: true,
      });
      if (!apps?.length) throw new Error("该 Runtime 暂未发现可对话的 Agent");
      const created = await createWebsiteIntegration({
        domain: domain.trim(),
        runtimeId: runtime.runtimeId,
        runtimeName: runtime.name || runtime.runtimeId,
        region: runtime.region,
        appName: apps[0],
      });
      setIntegrations((current) => [created, ...current]);
      setSelectedIntegrationId(created.id);
      setDomain("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "创建网站集成失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function removeIntegration(integration: WebsiteIntegrationRecord) {
    if (!window.confirm(`确定删除 ${integration.domain} 的网站集成吗？`)) return;
    setDeletingId(integration.id);
    setError("");
    try {
      await deleteWebsiteIntegration(integration.id);
      setIntegrations((current) => current.filter((item) => item.id !== integration.id));
      if (selectedIntegrationId === integration.id) {
        const next = integrations.find((item) => item.id !== integration.id);
        setSelectedIntegrationId(next?.id ?? "");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "删除网站集成失败");
    } finally {
      setDeletingId("");
    }
  }

  return (
    <div className="website-integration-page">
      <header className="website-integration-header">
        <button type="button" className="website-integration-back" onClick={onBack} aria-label="返回自动化列表">
          <BackIcon />
        </button>
        <WebsiteIcon className="website-integration-logo" />
        <div>
          <h1>网站集成</h1>
          <p>将 AgentKit Runtime 以悬浮聊天窗口嵌入网站</p>
        </div>
      </header>

      <div className="website-integration-scroll">
        <div className="website-integration-content">
          <section className="website-integration-section" aria-labelledby="website-add-title">
            <div className="website-integration-section-heading">
              <div>
                <span>1</span>
                <h2 id="website-add-title">添加网站</h2>
              </div>
            </div>
            <form className="website-integration-form" onSubmit={addIntegration}>
              <label htmlFor="website-runtime">AgentKit Runtime</label>
              <Select
                id="website-runtime"
                options={runtimeOptions}
                value={selectedRuntime}
                onChange={(option) => setSelectedRuntime(option.value)}
                placeholder={loading ? "正在加载 Runtime" : "选择 Runtime"}
                loading={loading}
                disabled={loading || submitting || runtimeOptions.length === 0}
                size="lg"
                pill={false}
                align="start"
              />
              <label htmlFor="website-domain">网站域名</label>
              <Input
                id="website-domain"
                value={domain}
                onChange={(event) => setDomain(event.target.value)}
                placeholder="例如 xxxx.com 或 localhost:5173"
                autoComplete="off"
                disabled={submitting}
                size="lg"
              />
              <Button
                type="submit"
                color="primary"
                size="lg"
                pill={false}
                loading={submitting}
                disabled={!domain.trim() || !selectedRuntime || loading}
              >
                {submitting ? "正在生成" : "生成 Token"}
              </Button>
            </form>
            {error ? <div className="website-integration-error" role="alert">{error}</div> : null}
          </section>

          <section className="website-integration-section" aria-labelledby="website-list-title">
            <div className="website-integration-section-heading">
              <div>
                <span>2</span>
                <h2 id="website-list-title">已添加网站</h2>
              </div>
              <small>{integrations.length} 个</small>
            </div>
            {loading ? (
              <div className="website-integration-loading" role="status">正在加载网站集成</div>
            ) : integrations.length ? (
              <div className="website-integration-list">
                {integrations.map((integration) => (
                  <div
                    key={integration.id}
                    className={`website-integration-row${selectedIntegration?.id === integration.id ? " is-selected" : ""}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => setSelectedIntegrationId(integration.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelectedIntegrationId(integration.id);
                      }
                    }}
                  >
                    <span className="website-integration-row-main">
                      <strong>{integration.domain}</strong>
                      <small>{integration.runtimeName} · {integration.appName}</small>
                    </span>
                    <span className="website-integration-token">{integration.token.slice(0, 12)}…</span>
                    <span className="website-integration-created">{formatCreatedAt(integration.createdAt)}</span>
                    <Button
                      type="button"
                      color="danger"
                      variant="ghost"
                      size="sm"
                      pill={false}
                      loading={deletingId === integration.id}
                      onClick={(event) => {
                        event.stopPropagation();
                        void removeIntegration(integration);
                      }}
                    >
                      删除
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyMessage className="website-integration-empty">
                <EmptyMessage.Icon><WebsiteIcon /></EmptyMessage.Icon>
                <EmptyMessage.Title>还没有网站集成</EmptyMessage.Title>
                <EmptyMessage.Description>选择 Runtime 并输入网站域名即可生成 Token</EmptyMessage.Description>
              </EmptyMessage>
            )}
          </section>

          <section className="website-integration-section" aria-labelledby="website-embed-title">
            <div className="website-integration-section-heading">
              <div>
                <span>3</span>
                <h2 id="website-embed-title">引入方法</h2>
              </div>
            </div>
            {selectedIntegration ? (
              <div className="website-integration-embed">
                <div>
                  <strong>{selectedIntegration.domain}</strong>
                  <span>将下面代码放到网页的 body 结束标签前</span>
                </div>
                <pre><code>{embedSnippet}</code></pre>
                <CopyButton
                  copyValue={embedSnippet}
                  color="secondary"
                  variant="outline"
                  size="sm"
                  pill={false}
                >
                  {({ copied }) => copied ? "已复制" : "复制代码"}
                </CopyButton>
              </div>
            ) : (
              <p className="website-integration-hint">添加网站后会在这里生成引入代码。</p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
