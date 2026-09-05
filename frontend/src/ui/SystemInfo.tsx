import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  getEnvironmentResources,
  getSystemInfo,
  listIdentityUserPools,
  updateCodexSandboxToolModelEnv,
  type CodexSandboxToolKind,
  type IdentityUserPool,
  type EnvironmentResourcesResponse,
  type SandboxToolInfo,
  type SandboxToolKind,
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

function isCodexSandboxToolKind(kind: SandboxToolKind): kind is CodexSandboxToolKind {
  return kind === "codex" || kind === "codex_snapshot";
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
    Partial<Record<CodexSandboxToolKind, SandboxToolUpdateState>>
  >({});

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  function patchSandboxToolUpdate(
    kind: CodexSandboxToolKind,
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
    if (!isCodexSandboxToolKind(tool.kind) || !tool.toolId) return;
    const currentState =
      sandboxToolUpdates[tool.kind] ?? defaultSandboxToolUpdateState();
    if (currentState.busy) return;
    patchSandboxToolUpdate(tool.kind, { busy: true, error: "", message: "" });
    try {
      const result = await updateCodexSandboxToolModelEnv(tool.kind);
      if (!mountedRef.current) return;
      setSandboxTools((current) =>
        current.map((item) =>
          item.kind === tool.kind
            ? {
                ...item,
                needsModelEnvUpdate: false,
                canUpdateModelEnv: false,
                modelEnvError: "",
                modelEnvErrorCode: "",
              }
            : item,
        ),
      );
      patchSandboxToolUpdate(tool.kind, {
        busy: false,
        error: "",
        message: result.updated
          ? t("systemInfo.modelEnvUpdated")
          : t("systemInfo.modelEnvAlreadyCurrent"),
      });
    } catch (cause) {
      if (!mountedRef.current) return;
      patchSandboxToolUpdate(tool.kind, {
        busy: false,
        error: t("systemInfo.modelEnvUpdateError"),
        message: "",
      });
    }
  }

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
        setSandboxError(t("systemInfo.sandboxInfoError"));
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
                  {sandboxTools.map((tool) => {
                    const codexKind = isCodexSandboxToolKind(tool.kind)
                      ? tool.kind
                      : null;
                    const updateState = codexKind
                      ? sandboxToolUpdates[codexKind]
                      : undefined;
                    const updateVisible =
                      codexKind !== null &&
                      Boolean(tool.toolId) &&
                      tool.needsModelEnvUpdate &&
                      tool.canUpdateModelEnv;
                    const inlineError = codexKind
                      ? updateState?.error || tool.modelEnvError
                      : "";
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
                                region,
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
                                aria-label={t("systemInfo.updateModelEnv", {
                                  name: tool.label,
                                  variant: tool.snapshot ? t("systemInfo.snapshotWithSpace") : "",
                                })}
                                title={t("systemInfo.updateModelEnv", {
                                  name: tool.label,
                                  variant: tool.snapshot ? t("systemInfo.snapshotWithSpace") : "",
                                })}
                                onClick={() => void updateSandboxToolModelEnv(tool)}
                              >
                                <RefreshCw
                                  aria-hidden="true"
                                  className={updateState?.busy ? "is-spinning" : ""}
                                />
                              </button>
                            ) : null}
                            {codexKind && updateState?.message ? (
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
