import { useEffect, useState } from "react";
import {
  getSystemInfo,
  listIdentityUserPools,
  type IdentityUserPool,
  type SandboxToolInfo,
  type StudioRole,
} from "../adk/client";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import "./SystemInfo.css";

export interface SystemInfoProps {
  version: string;
  localMode: boolean;
  role: StudioRole;
}

function isMissingLocalCredentials(cause: unknown): boolean {
  return (
    cause instanceof Error &&
    cause.message.includes("Volcengine credentials not found")
  );
}

export function SystemInfo({ version, localMode, role }: SystemInfoProps) {
  const isAdmin = role === "admin";
  const [tosAddress, setTosAddress] = useState("");
  const [sandboxTools, setSandboxTools] = useState<SandboxToolInfo[]>([]);
  const [userPools, setUserPools] = useState<IdentityUserPool[]>([]);
  const [sandboxLoading, setSandboxLoading] = useState(true);
  const [sandboxError, setSandboxError] = useState("");
  const [userPoolsLoading, setUserPoolsLoading] = useState(true);
  const [userPoolsError, setUserPoolsError] = useState("");
  const [sandboxReloadKey, setSandboxReloadKey] = useState(0);
  const [userPoolsReloadKey, setUserPoolsReloadKey] = useState(0);

  useEffect(() => {
    if (!isAdmin) {
      setTosAddress("");
      setSandboxTools([]);
      setSandboxLoading(false);
      setSandboxError("");
      return;
    }
    const controller = new AbortController();
    setSandboxLoading(true);
    setSandboxError("");
    void getSystemInfo(controller.signal)
      .then((systemInfo) => {
        setTosAddress(systemInfo.storage.tosAddress);
        setSandboxTools(systemInfo.sandboxTools);
      })
      .catch((cause) => {
        if ((cause as Error)?.name === "AbortError") return;
        setSandboxError(cause instanceof Error ? cause.message : String(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setSandboxLoading(false);
      });
    return () => controller.abort();
  }, [isAdmin, sandboxReloadKey]);

  useEffect(() => {
    if (!isAdmin) {
      setUserPools([]);
      setUserPoolsLoading(false);
      setUserPoolsError("");
      return;
    }
    const controller = new AbortController();
    setUserPoolsLoading(true);
    setUserPoolsError("");
    void listIdentityUserPools(controller.signal)
      .then((pools) => {
        setUserPools(pools.filter((pool) => pool.isCurrent));
      })
      .catch((cause) => {
        if ((cause as Error)?.name === "AbortError") return;
        if (localMode && isMissingLocalCredentials(cause)) {
          setUserPools([]);
          return;
        }
        setUserPoolsError(cause instanceof Error ? cause.message : String(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setUserPoolsLoading(false);
      });
    return () => controller.abort();
  }, [isAdmin, localMode, userPoolsReloadKey]);

  return (
    <div className="system-info-page">
      <header className="system-info-page-header">
        <h1>系统信息</h1>
        <p>查看当前 Studio 版本及关联的基础资源</p>
      </header>

      <div className="system-info-scroll">
        <section
          className="system-info-section"
          aria-labelledby="studio-info-title"
        >
          <h2 id="studio-info-title">通用</h2>
          <dl className="system-info-summary">
            <div>
              <dt>当前版本</dt>
              <dd>{version || "—"}</dd>
            </div>
          </dl>
        </section>

        {isAdmin ? (
          <>
            <section
              className="system-info-section"
              aria-labelledby="storage-info-title"
            >
              <h2 id="storage-info-title">存储</h2>
              {sandboxLoading ? (
                <div
                  className="system-info-loading"
                  role="status"
                  aria-live="polite"
                >
                  <TextShimmer as="span">正在加载存储信息</TextShimmer>
                </div>
              ) : sandboxError ? (
                <div className="system-info-error" role="alert">
                  <p>{sandboxError}</p>
                  <button
                    type="button"
                    onClick={() => setSandboxReloadKey((key) => key + 1)}
                  >
                    重新加载
                  </button>
                </div>
              ) : (
                <dl className="system-info-summary">
                  <div>
                    <dt>TOS 地址</dt>
                    <dd className={tosAddress ? "" : "is-empty"}>
                      {tosAddress || "未配置"}
                    </dd>
                  </div>
                </dl>
              )}
            </section>

            <section
              className="system-info-section"
              aria-labelledby="sandbox-tool-title"
            >
              <h2 id="sandbox-tool-title">沙箱信息</h2>
              {sandboxLoading ? (
                <div
                  className="system-info-loading"
                  role="status"
                  aria-live="polite"
                >
                  <TextShimmer as="span">正在加载沙箱信息</TextShimmer>
                </div>
              ) : sandboxError ? (
                <div className="system-info-error" role="alert">
                  <p>{sandboxError}</p>
                  <button
                    type="button"
                    onClick={() => setSandboxReloadKey((key) => key + 1)}
                  >
                    重新加载
                  </button>
                </div>
              ) : (
                <div className="system-info-tool-list">
                  {sandboxTools.map((tool) => (
                    <dl className="system-info-tool" key={tool.kind}>
                      <div>
                        <dt>{tool.label}</dt>
                        <dd className={tool.toolId ? "" : "is-empty"}>
                          {tool.toolId || "未配置"}
                        </dd>
                      </div>
                    </dl>
                  ))}
                </div>
              )}
            </section>

            <section
              className="system-info-section"
              aria-labelledby="user-pool-title"
            >
              <h2 id="user-pool-title">用户池</h2>
              {userPoolsLoading ? (
                <div
                  className="system-info-loading"
                  role="status"
                  aria-live="polite"
                >
                  <TextShimmer as="span">正在加载用户池</TextShimmer>
                </div>
              ) : userPoolsError ? (
                <div className="system-info-error" role="alert">
                  <p>{userPoolsError}</p>
                  <button
                    type="button"
                    onClick={() => setUserPoolsReloadKey((key) => key + 1)}
                  >
                    重新加载
                  </button>
                </div>
              ) : userPools.length > 0 ? (
                <div className="system-info-pool-list">
                  {userPools.map((pool) => (
                    <article className="system-info-pool" key={pool.uid}>
                      <header>
                        <h3>{pool.name || "未命名用户池"}</h3>
                        {pool.isCurrent ? <span>当前 Studio</span> : null}
                      </header>
                      <dl>
                        <div>
                          <dt>UID</dt>
                          <dd>{pool.uid || "—"}</dd>
                        </div>
                        <div>
                          <dt>域名</dt>
                          <dd>{pool.domain || "—"}</dd>
                        </div>
                        <div>
                          <dt>区域</dt>
                          <dd>{pool.region || "—"}</dd>
                        </div>
                      </dl>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="system-info-empty">
                  {localMode
                    ? "本地模式未配置用户池"
                    : "当前 Studio 未配置用户池"}
                </p>
              )}
            </section>
          </>
        ) : null}
      </div>
    </div>
  );
}
