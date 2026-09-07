import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  getEnvironmentResources,
  getSystemInfo,
  listIdentityUserPools,
  getSandboxImageUpdates,
  updateSandboxTool,
  type SandboxImageState,
  type IdentityUserPool,
  type EnvironmentResourcesResponse,
  type SandboxToolInfo,
  type StudioRole,
} from "../adk/client";
import type { CloudProvider } from "../adk/cloudProvider";
import { PageBackButton } from "./PageBackButton";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import {
  identityUserPoolConsoleUrl,
  sandboxToolConsoleUrl,
  tosConsoleUrl,
} from "./systemInfoConsoleLinks";
import "./SystemInfo.css";

export interface SystemInfoProps {
  version: string;
  localMode: boolean;
  role: StudioRole;
  provider: CloudProvider;
  region: string;
  onBack: () => void;
}

interface ConsoleLinkProps {
  href: string | null;
  label: string;
  children: string;
}

function ConsoleLink({ href, label, children }: ConsoleLinkProps) {
  if (!href) return <span>{children}</span>;
  return (
    <a
      className="system-info-resource-link"
      href={href}
      target="_blank"
      rel="noreferrer"
      aria-label={label}
      title={label}
    >
      <span>{children}</span>
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path d="M7.75 5.25h-2.5a1.5 1.5 0 0 0-1.5 1.5v8a1.5 1.5 0 0 0 1.5 1.5h8a1.5 1.5 0 0 0 1.5-1.5v-2.5" />
        <path d="M10.25 3.75h6v6M16 4 9 11" />
      </svg>
    </a>
  );
}

function isMissingLocalCredentials(cause: unknown): boolean {
  return (
    cause instanceof Error &&
    cause.message.includes("Volcengine credentials not found")
  );
}

function SandboxUpdateIcon({ spinning }: { spinning: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" className={spinning ? "is-spinning" : ""}>
      <path d="M19.5 9A8 8 0 0 0 5 6L3 9m0-5v5h5M4.5 15A8 8 0 0 0 19 18l2-3m0 5v-5h-5" />
    </svg>
  );
}

interface SandboxToolUpdateState {
  busy: boolean;
  error: string;
  message: string;
}

function defaultSandboxToolUpdateState(): SandboxToolUpdateState {
  return { busy: false, error: "", message: "" };
}

export function SystemInfo({
  version,
  localMode,
  role,
  provider,
  region,
  onBack,
}: SystemInfoProps) {
  const { t } = useTranslation("ui");
  const isAdmin = role === "admin";
  const [tosAddress, setTosAddress] = useState("");
  const [sandboxTools, setSandboxTools] = useState<SandboxToolInfo[]>([]);
  const [userPools, setUserPools] = useState<IdentityUserPool[]>([]);
  const [environmentResources, setEnvironmentResources] =
    useState<EnvironmentResourcesResponse | null>(null);
  const [sandboxLoading, setSandboxLoading] = useState(true);
  const [sandboxError, setSandboxError] = useState("");
  const [userPoolsLoading, setUserPoolsLoading] = useState(true);
  const [userPoolsError, setUserPoolsError] = useState("");
  const [environmentResourcesLoading, setEnvironmentResourcesLoading] = useState(true);
  const [environmentResourcesError, setEnvironmentResourcesError] = useState("");
  const [sandboxReloadKey, setSandboxReloadKey] = useState(0);
  const [userPoolsReloadKey, setUserPoolsReloadKey] = useState(0);
  const [environmentResourcesReloadKey, setEnvironmentResourcesReloadKey] = useState(0);
  const mountedRef = useRef(false);
  const [sandboxToolUpdates, setSandboxToolUpdates] = useState<
    Record<string, SandboxToolUpdateState>
  >({});

  const [imageStates, setImageStates] = useState<Record<string, SandboxImageState>>({});
  const [imageError, setImageError] = useState("");
  const [imageLoading, setImageLoading] = useState(true);
  const pendingTools = useRef(new Set<string>());
  const imageRequestVersion = useRef(0);
  const scope = `${provider}:${region}`;
  const scopeRef = useRef(scope);
  scopeRef.current = scope;

  useEffect(() => {
    setImageStates({});
    setSandboxToolUpdates({});
  }, [scope]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  function patchSandboxToolUpdate(
    kind: string,
    patch: Partial<SandboxToolUpdateState>,
  ) {
    setSandboxToolUpdates((current) => ({
      ...current,
      [kind]: {
        ...defaultSandboxToolUpdateState(),
        ...current[kind],
        ...patch,
      },
    }));
  }

  async function updateSandboxToolModelEnv(tool: SandboxToolInfo) {
    if (!tool.toolId || pendingTools.current.has(tool.toolId)) return;
    const updateScope = scope;
    pendingTools.current.add(tool.toolId);
    imageRequestVersion.current += 1;
    patchSandboxToolUpdate(tool.toolId, { busy: true, error: "", message: "" });
    try {
      const result = await updateSandboxTool(tool.kind);
      if (!mountedRef.current || scopeRef.current !== updateScope) return;
      imageRequestVersion.current += 1;
      setImageStates((current) => ({ ...current, [tool.toolId]: result.state }));
      patchSandboxToolUpdate(tool.toolId, {
        busy: false, error: "",
        message: result.updated ? t("systemInfo.modelEnvUpdated") : t("systemInfo.modelEnvAlreadyCurrent"),
      });
    } catch (cause) {
      if (!mountedRef.current || scopeRef.current !== updateScope) return;
      imageRequestVersion.current += 1;
      patchSandboxToolUpdate(tool.toolId, {
        busy: false,
        error: t("systemInfo.sandboxUpdateError"),
        message: "",
      });
    } finally {
      pendingTools.current.delete(tool.toolId);
    }
  }

  useEffect(() => {
    if (!isAdmin) return;
    const controller = new AbortController();
    const version = ++imageRequestVersion.current;
    setImageError("");
    setImageLoading(true);
    void getSandboxImageUpdates(controller.signal).then((states) => {
      if (controller.signal.aborted || version !== imageRequestVersion.current) return;
      setImageStates(Object.fromEntries(states.map((state) => [state.toolId, state])));
    }).catch(() => {
      if (!controller.signal.aborted && version === imageRequestVersion.current) {
        setImageError(t("systemInfo.versionCheckError"));
      }
    }).finally(() => {
      if (!controller.signal.aborted) setImageLoading(false);
    });
    return () => controller.abort();
  }, [isAdmin, provider, region, sandboxReloadKey]);

  useEffect(() => {
    if (!Object.values(imageStates).some((state) => state.status === "Updating" || state.status === "Creating")) return;
    const timer = window.setTimeout(() => setSandboxReloadKey((key) => key + 1), 5000);
    return () => window.clearTimeout(timer);
  }, [imageStates]);

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
        if (controller.signal.aborted) return;
        setTosAddress(systemInfo.storage.tosAddress);
        setSandboxTools(systemInfo.sandboxTools);
      })
      .catch((cause) => {
        if ((cause as Error)?.name === "AbortError") return;
        setSandboxError(t("systemInfo.sandboxInfoError"));
      })
      .finally(() => {
        if (!controller.signal.aborted) setSandboxLoading(false);
      });
    return () => controller.abort();
  }, [isAdmin, provider, region, sandboxReloadKey]);

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
        setUserPoolsError(t("systemInfo.userPoolError"));
      })
      .finally(() => {
        if (!controller.signal.aborted) setUserPoolsLoading(false);
      });
    return () => controller.abort();
  }, [isAdmin, localMode, userPoolsReloadKey]);

  useEffect(() => {
    if (!isAdmin) {
      setEnvironmentResources(null);
      setEnvironmentResourcesLoading(false);
      setEnvironmentResourcesError("");
      return;
    }
    const controller = new AbortController();
    setEnvironmentResourcesLoading(true);
    setEnvironmentResourcesError("");
    void getEnvironmentResources(controller.signal)
      .then(setEnvironmentResources)
      .catch((cause) => {
        if ((cause as Error)?.name === "AbortError") return;
        setEnvironmentResourcesError(t("systemInfo.environmentResourcesError"));
      })
      .finally(() => {
        if (!controller.signal.aborted) setEnvironmentResourcesLoading(false);
      });
    return () => controller.abort();
  }, [isAdmin, environmentResourcesReloadKey]);

  return (
    <div className="system-info-page">
      <header className="system-info-page-header">
        <PageBackButton label={t("common.back")} onClick={onBack} />
        <div>
          <h1>{t("systemInfo.title")}</h1>
          <p>{t("systemInfo.description")}</p>
        </div>
      </header>

      <div className="system-info-scroll">
        <section
          className="system-info-section"
          aria-labelledby="studio-info-title"
        >
          <h2 id="studio-info-title">{t("systemInfo.general")}</h2>
          <dl className="system-info-summary">
            <div>
              <dt>{t("systemInfo.currentVersion")}</dt>
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
              <h2 id="storage-info-title">{t("systemInfo.storage")}</h2>
              {sandboxLoading ? (
                <div
                  className="system-info-loading"
                  role="status"
                  aria-live="polite"
                >
                  <TextShimmer as="span">{t("systemInfo.loadingStorage")}</TextShimmer>
                </div>
              ) : sandboxError ? (
                <div className="system-info-error" role="alert">
                  <p>{sandboxError}</p>
                  <button
                    type="button"
                    onClick={() => setSandboxReloadKey((key) => key + 1)}
                  >
                    {t("common.reload")}
                  </button>
                </div>
              ) : (
                <dl className="system-info-summary">
                  <div className="system-info-resource-row">
                    <dt>{t("systemInfo.tosAddress")}</dt>
                    <dd
                      className={`system-info-resource-value${tosAddress ? "" : " is-empty"}`}
                    >
                      <ConsoleLink
                        href={tosConsoleUrl(provider, tosAddress)}
                        label={t("systemInfo.openTosConsole")}
                      >
                        {tosAddress || t("common.notConfigured")}
                      </ConsoleLink>
                    </dd>
                  </div>
                </dl>
              )}
            </section>

            <section
              className="system-info-section"
              aria-labelledby="environment-build-info-title"
            >
              <h2 id="environment-build-info-title">{t("systemInfo.environmentBuild")}</h2>
              {environmentResourcesLoading ? (
                <div className="system-info-loading" role="status" aria-live="polite">
                  <TextShimmer as="span">{t("systemInfo.loadingEnvironmentResources")}</TextShimmer>
                </div>
              ) : environmentResourcesError ? (
                <div className="system-info-error" role="alert">
                  <p>{environmentResourcesError}</p>
                  <button
                    type="button"
                    onClick={() => setEnvironmentResourcesReloadKey((key) => key + 1)}
                  >
                    {t("common.reload")}
                  </button>
                </div>
              ) : environmentResources ? (
                <dl className="system-info-summary">
                  <div className="system-info-resource-row">
                    <dt>{t("systemInfo.codePipelineWorkspace")}</dt>
                    <dd className="system-info-resource-value">
                      <ConsoleLink
                        href={environmentResources.codePipeline.consoleUrl || null}
                        label={t("systemInfo.openCodePipelineWorkspace")}
                      >
                        {environmentResources.codePipeline.workspaceName ||
                          environmentResources.codePipeline.workspaceId ||
                          t("systemInfo.createdOnFirstBuild")}
                      </ConsoleLink>
                    </dd>
                  </div>
                  <div className="system-info-resource-row">
                    <dt>{t("systemInfo.codePipelinePipeline")}</dt>
                    <dd className="system-info-resource-value">
                      {environmentResources.codePipeline.pipelineName ||
                        environmentResources.codePipeline.pipelineId ||
                        t("systemInfo.createdOnFirstBuild")}
                    </dd>
                  </div>
                  <div className="system-info-resource-row">
                    <dt>{t("systemInfo.containerRegistryRepository")}</dt>
                    <dd className="system-info-resource-value">
                      <ConsoleLink
                        href={environmentResources.containerRegistry.consoleUrl || null}
                        label={t("systemInfo.openContainerRegistryRepository")}
                      >
                        {environmentResources.containerRegistry.imageRepository ||
                          [
                            environmentResources.containerRegistry.registry,
                            environmentResources.containerRegistry.namespace,
                            environmentResources.containerRegistry.repository,
                          ].filter(Boolean).join("/") ||
                          t("systemInfo.createdOnFirstBuild")}
                      </ConsoleLink>
                    </dd>
                  </div>
                </dl>
              ) : null}
            </section>

            <section
              className="system-info-section"
              aria-labelledby="sandbox-tool-title"
            >
              <h2 id="sandbox-tool-title">{t("systemInfo.sandboxInfo")}</h2>
              <button type="button" className="system-info-refresh"
                disabled={imageLoading} onClick={() => setSandboxReloadKey((key) => key + 1)}>
                {imageLoading ? t("systemInfo.checkingVersions") : t("systemInfo.checkUpdates")}
              </button>
              {sandboxLoading ? (
                <div
                  className="system-info-loading"
                  role="status"
                  aria-live="polite"
                >
                  <TextShimmer as="span">{t("systemInfo.loadingSandboxInfo")}</TextShimmer>
                </div>
              ) : sandboxError ? (
                <div className="system-info-error" role="alert">
                  <p>{sandboxError}</p>
                  <button
                    type="button"
                    onClick={() => setSandboxReloadKey((key) => key + 1)}
                  >
                    {t("common.reload")}
                  </button>
                </div>
              ) : (
                <div className="system-info-tool-list">
                  {imageError ? <span className="system-info-inline-error" role="alert">{imageError}</span> : null}
                  {sandboxTools.map((tool) => {
                    const imageState = imageStates[tool.toolId];
                    const updateState = sandboxToolUpdates[tool.toolId];
                    const updateVisible = Boolean(tool.toolId) && Boolean(imageState?.canUpdate);
                    const inlineError = updateState?.error || (imageState?.error ? t("systemInfo.versionCheckError") : imageState?.modelEnvError ? t("systemInfo.modelEnvRepairUnavailable") : "");
                    return (
                      <dl className="system-info-tool" key={tool.kind}>
                        <div className="system-info-resource-row">
                          <dt className="system-info-tool-label">
                            <span>{tool.label}</span>
                            {tool.snapshot ? (
                              <span className="system-info-tool-badge">{t("systemInfo.snapshot")}</span>
                            ) : null}
                          </dt>
                          <dd
                            className={`system-info-resource-value${tool.toolId ? "" : " is-empty"}`}
                          >
                            <ConsoleLink
                              href={sandboxToolConsoleUrl(
                                provider,
                                imageState?.region || region,
                                tool.toolId,
                              )}
                              label={t("systemInfo.openToolConsole", { name: tool.label })}
                            >
                              {tool.toolId || t("common.notConfigured")}
                            </ConsoleLink>
                            {updateVisible ? (
                              <button
                                type="button"
                                className="system-info-resource-update"
                                disabled={updateState?.busy}
                                aria-busy={updateState?.busy || undefined}
                                aria-label={t("systemInfo.updateSandbox", {
                                  name: tool.label,
                                  variant: tool.snapshot ? t("systemInfo.snapshotWithSpace") : "",
                                })}
                                title={t("systemInfo.updateSandbox", {
                                  name: tool.label,
                                  variant: tool.snapshot ? t("systemInfo.snapshotWithSpace") : "",
                                })}
                                onClick={() => void updateSandboxToolModelEnv(tool)}
                              >
                                <SandboxUpdateIcon spinning={updateState?.busy || false} />
                              </button>
                            ) : null}
                            {imageState?.currentImage ? (
                              <span className="system-info-inline-status" title={`${imageState.currentImage} → ${imageState.latestImage}`}>
                                {imageState.currentImage.split(":").pop()}
                                {imageState.needsImageUpdate ? ` → ${imageState.latestImage?.split(":").pop()}` : ""}
                                {imageState.status === "Updating" ? ` · ${t("systemInfo.updatingSandbox")}` : ""}
                              </span>
                            ) : null}
                            {updateState?.message ? (
                              <span className="system-info-inline-status" role="status">
                                {updateState.message}
                              </span>
                            ) : null}
                            {inlineError ? (
                              <span className="system-info-inline-error" role="alert">
                                {inlineError}
                              </span>
                            ) : null}
                          </dd>
                        </div>
                      </dl>
                    );
                  })}
                </div>
              )}
            </section>

            <section
              className="system-info-section"
              aria-labelledby="user-pool-title"
            >
              <h2 id="user-pool-title">{t("systemInfo.userPool")}</h2>
              {userPoolsLoading ? (
                <div
                  className="system-info-loading"
                  role="status"
                  aria-live="polite"
                >
                  <TextShimmer as="span">{t("systemInfo.loadingUserPool")}</TextShimmer>
                </div>
              ) : userPoolsError ? (
                <div className="system-info-error" role="alert">
                  <p>{userPoolsError}</p>
                  <button
                    type="button"
                    onClick={() => setUserPoolsReloadKey((key) => key + 1)}
                  >
                    {t("common.reload")}
                  </button>
                </div>
              ) : userPools.length > 0 ? (
                <div className="system-info-pool-list">
                  {userPools.map((pool) => (
                    <dl className="system-info-pool" key={pool.uid}>
                      <div>
                        <dt>{t("common.name")}</dt>
                        <dd className="system-info-resource-value">
                          <ConsoleLink
                            href={identityUserPoolConsoleUrl(
                              provider,
                              pool.region || region,
                              pool.uid,
                            )}
                            label={t("systemInfo.openUserPoolConsole", {
                              name: pool.name || "",
                            })}
                          >
                            {pool.name || t("systemInfo.unnamedUserPool")}
                          </ConsoleLink>
                        </dd>
                      </div>
                      <div>
                        <dt>{t("systemInfo.id")}</dt>
                        <dd>{pool.uid || "—"}</dd>
                      </div>
                      <div>
                        <dt>{t("systemInfo.domain")}</dt>
                        <dd>{pool.domain || "—"}</dd>
                      </div>
                      <div>
                        <dt>{t("systemInfo.region")}</dt>
                        <dd>{pool.region || "—"}</dd>
                      </div>
                    </dl>
                  ))}
                </div>
              ) : (
                <p className="system-info-empty">
                  {localMode
                    ? t("systemInfo.noLocalUserPool")
                    : t("systemInfo.noUserPool")}
                </p>
              )}
            </section>
          </>
        ) : null}
      </div>
    </div>
  );
}
