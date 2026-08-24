import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type SVGProps,
} from "react";

import {
  cancelAgentkitDeployment,
  type DeployAgentkitResult,
  type DeployStage,
} from "../../adk/client";
import {
  beginAgentDeploy,
  classifyTelemetryError,
  safeTelemetryErrorMessage,
  type AgentDeployFailedProps,
} from "../../telemetry";
import feishuLogo from "../../assets/feishu-logo.svg";
import { agentNameProblem } from "../../create/agentNameValidation";
import { TextShimmer } from "../../ui/text-shimmer/TextShimmer";
import { deployFeishuBotRuntime } from "./deployment";
import "./FeishuBotIntegration.css";

interface FeishuBotIntegrationProps {
  onBack: () => void;
}

type Region = "cn-beijing" | "cn-shanghai";
type DeploymentStatus =
  | "idle"
  | "preparing"
  | "running"
  | "cancelling"
  | "succeeded"
  | "failed"
  | "cancelled";

const REGIONS: readonly { value: Region; label: string }[] = [
  { value: "cn-beijing", label: "北京" },
  { value: "cn-shanghai", label: "上海" },
];

const DEPLOYMENT_STEPS = [
  { phase: "prepare", label: "生成智能体" },
  { phase: "build", label: "构建镜像" },
  { phase: "deploy", label: "创建 Runtime" },
  { phase: "publish", label: "发布服务" },
] as const;

function BackIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path d="m9.8 3.5-4.5 4.5 4.5 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 18 18" fill="none" aria-hidden="true" {...props}>
      <path d="m5 7 4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CheckIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 18 18" fill="none" aria-hidden="true" {...props}>
      <path d="m4 9.2 3.1 3.1L14 5.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ExternalIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path d="M6.5 4H4.8A1.8 1.8 0 0 0 3 5.8v5.4A1.8 1.8 0 0 0 4.8 13h5.4a1.8 1.8 0 0 0 1.8-1.8V9.5M9 3h4v4M12.5 3.5 7.2 8.8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function stageIndex(phase: string | null): number {
  if (!phase || phase === "upload") return 0;
  const index = DEPLOYMENT_STEPS.findIndex((step) => step.phase === phase);
  return index < 0 ? 0 : index;
}

function telemetryDeployPhase(
  phase: string | undefined,
): AgentDeployFailedProps["failedPhase"] {
  switch (phase) {
    case "prepare":
    case "upload":
    case "build":
    case "deploy":
    case "publish":
    case "update":
    case "evaluation":
      return phase;
    default:
      return "unknown";
  }
}

export function FeishuBotIntegration({ onBack }: FeishuBotIntegrationProps) {
  const [agentName, setAgentName] = useState("feishu_assistant");
  const [appId, setAppId] = useState("");
  const [appSecret, setAppSecret] = useState("");
  const [showSecret, setShowSecret] = useState(false);
  const [region, setRegion] = useState<Region>("cn-beijing");
  const [regionOpen, setRegionOpen] = useState(false);
  const [agentNameError, setAgentNameError] = useState("");
  const [appIdError, setAppIdError] = useState("");
  const [appSecretError, setAppSecretError] = useState("");
  const [deploymentStatus, setDeploymentStatus] = useState<DeploymentStatus>("idle");
  const [activeStage, setActiveStage] = useState<DeployStage | null>(null);
  const [deployError, setDeployError] = useState("");
  const [result, setResult] = useState<DeployAgentkitResult | null>(null);
  const regionPickerRef = useRef<HTMLDivElement | null>(null);
  const regionTriggerRef = useRef<HTMLButtonElement | null>(null);
  const regionOptionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const regionFocusIndexRef = useRef(0);
  const taskIdRef = useRef<string | null>(null);
  const deploymentOperationRef = useRef<ReturnType<
    typeof beginAgentDeploy
  > | null>(null);
  const latestPhaseRef = useRef("prepare");
  const cancelledRef = useRef(false);
  const mountedRef = useRef(true);

  const deploymentActive = ["preparing", "running", "cancelling"].includes(
    deploymentStatus,
  );

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!regionOpen) return;
    regionOptionRefs.current[regionFocusIndexRef.current]?.focus();
    const handlePointerDown = (event: PointerEvent) => {
      if (
        event.target instanceof Node &&
        regionPickerRef.current &&
        !regionPickerRef.current.contains(event.target)
      ) {
        setRegionOpen(false);
      }
    };
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        setRegionOpen(false);
        regionTriggerRef.current?.focus();
      }
    };
    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [regionOpen]);

  const stopComposingSubmit = (event: KeyboardEvent<HTMLFormElement>) => {
    if (
      event.key === "Enter" &&
      (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229)
    ) {
      event.preventDefault();
    }
  };

  const validate = () => {
    const nextAgentNameError = agentNameProblem(agentName.trim()) ?? "";
    const nextAppIdError = appId.trim() ? "" : "请输入飞书 App ID";
    const nextAppSecretError = appSecret.trim() ? "" : "请输入飞书 App Secret";
    setAgentNameError(nextAgentNameError);
    setAppIdError(nextAppIdError);
    setAppSecretError(nextAppSecretError);
    return !nextAgentNameError && !nextAppIdError && !nextAppSecretError;
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!validate() || deploymentActive) return;

    const taskId = crypto.randomUUID();
    taskIdRef.current = taskId;
    latestPhaseRef.current = "prepare";
    cancelledRef.current = false;
    setDeploymentStatus("preparing");
    setActiveStage(null);
    setDeployError("");
    setResult(null);
    const operation = beginAgentDeploy({
      agentId: String(agentName.trim()),
      deployAction: "create",
      deploySource: "feishu_automation",
      createMode: "feishu_template",
      aiAssisted: 0,
      deployRegion: String(region),
      runtimeNetworkType: "public",
      feishuEnabled: 1,
    });
    deploymentOperationRef.current = operation;
    try {
      const deployed = await deployFeishuBotRuntime({
        agentName: agentName.trim(),
        appId: appId.trim(),
        appSecret: appSecret.trim(),
        region,
        taskId,
        onStage: (stage) => {
          latestPhaseRef.current = stage.phase || "deploy";
          if (!mountedRef.current || cancelledRef.current) return;
          setDeploymentStatus("running");
          setActiveStage(stage);
        },
      });
      if (cancelledRef.current) {
        operation.fail({
          failedPhase: telemetryDeployPhase(latestPhaseRef.current),
          errorKind: "abort",
          errorMessage: safeTelemetryErrorMessage("用户取消部署"),
        });
        return;
      }
      operation.succeed({ runtimeId: String(deployed.runtimeId || "") });
      if (!mountedRef.current) return;
      setResult(deployed);
      setAppSecret("");
      setShowSecret(false);
      setDeploymentStatus("succeeded");
    } catch (error) {
      operation.fail({
        failedPhase: telemetryDeployPhase(latestPhaseRef.current),
        ...(cancelledRef.current
          ? { errorKind: "abort" as const }
          : classifyTelemetryError(error, { phase: latestPhaseRef.current })),
        errorMessage: safeTelemetryErrorMessage(error),
      });
      if (!mountedRef.current || cancelledRef.current) return;
      setDeploymentStatus("failed");
      setDeployError(error instanceof Error ? error.message : String(error));
    } finally {
      if (taskIdRef.current === taskId) taskIdRef.current = null;
      if (deploymentOperationRef.current === operation) {
        deploymentOperationRef.current = null;
      }
    }
  };

  const cancelDeployment = async () => {
    const taskId = taskIdRef.current;
    if (!taskId || deploymentStatus !== "running") return;
    if (!window.confirm("取消部署将停止任务并清理已创建的 Runtime，确定继续吗？")) {
      return;
    }
    cancelledRef.current = true;
    setDeploymentStatus("cancelling");
    setDeployError("");
    try {
      await cancelAgentkitDeployment(taskId);
      deploymentOperationRef.current?.fail({
        failedPhase: telemetryDeployPhase(latestPhaseRef.current),
        errorKind: "abort",
        errorMessage: safeTelemetryErrorMessage("用户取消部署"),
      });
      if (mountedRef.current) setDeploymentStatus("cancelled");
    } catch (error) {
      cancelledRef.current = false;
      if (!mountedRef.current) return;
      setDeploymentStatus("failed");
      setDeployError(error instanceof Error ? error.message : String(error));
    }
  };

  const currentStepIndex = stageIndex(activeStage?.phase ?? null);
  const canSubmit = Boolean(
    agentName.trim() && appId.trim() && appSecret.trim() && !deploymentActive,
  );
  const selectedRegion = REGIONS.find((option) => option.value === region)!;

  return (
    <div className="feishu-integration-page">
      <header className="feishu-integration-header">
        <button
          type="button"
          className="feishu-back"
          onClick={onBack}
          aria-label="返回自动化列表"
          disabled={deploymentActive}
        >
          <BackIcon />
        </button>
        <img className="feishu-integration-logo" src={feishuLogo} alt="" aria-hidden="true" />
        <div>
          <h1>飞书机器人</h1>
          <p>创建一个由 AgentKit Runtime 驱动的飞书智能体</p>
        </div>
      </header>

      <div className="feishu-integration-layout">
        <section className="feishu-section-panel">
          <p className="feishu-panel-description">
            填写已发布飞书应用的凭据，Studio 将生成 basic 智能体、创建独立 Runtime，并启用飞书消息长连接。
          </p>

          <form className="feishu-form" onSubmit={onSubmit} onKeyDown={stopComposingSubmit} noValidate>
            <div className="feishu-field-grid">
              <div className="feishu-field">
                <label htmlFor="feishu-agent-name">智能体名称</label>
                <input
                  id="feishu-agent-name"
                  value={agentName}
                  maxLength={64}
                  disabled={deploymentActive}
                  onChange={(event) => {
                    setAgentName(event.target.value);
                    if (agentNameError) setAgentNameError("");
                  }}
                  onBlur={() => setAgentNameError(agentNameProblem(agentName.trim()) ?? "")}
                  aria-invalid={Boolean(agentNameError)}
                  aria-describedby={`feishu-agent-name-help${agentNameError ? " feishu-agent-name-error" : ""}`}
                />
                <span id="feishu-agent-name-help" className="feishu-field-help">
                  将作为新 Runtime 中的根智能体名称
                </span>
                {agentNameError ? <span id="feishu-agent-name-error" className="feishu-field-error" role="alert">{agentNameError}</span> : null}
              </div>

              <div className="feishu-field">
                <label id="feishu-region-label">部署地域</label>
                <div className="feishu-region-picker" ref={regionPickerRef}>
                  <button
                    ref={regionTriggerRef}
                    type="button"
                    className="feishu-region-trigger"
                    disabled={deploymentActive}
                    aria-haspopup="listbox"
                    aria-expanded={regionOpen}
                    aria-labelledby="feishu-region-label feishu-region-value"
                    onClick={() => {
                      regionFocusIndexRef.current = REGIONS.findIndex(
                        (option) => option.value === region,
                      );
                      setRegionOpen((open) => !open);
                    }}
                    onKeyDown={(event) => {
                      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
                      event.preventDefault();
                      regionFocusIndexRef.current = event.key === "ArrowUp"
                        ? REGIONS.length - 1
                        : REGIONS.findIndex((option) => option.value === region);
                      setRegionOpen(true);
                    }}
                  >
                    <span id="feishu-region-value">{selectedRegion.label}</span>
                    <ChevronIcon />
                  </button>
                  {regionOpen ? (
                    <div
                      className="feishu-region-menu"
                      role="listbox"
                      aria-label="部署地域"
                      onKeyDown={(event) => {
                        const currentIndex = regionOptionRefs.current.findIndex(
                          (option) => option === document.activeElement,
                        );
                        let nextIndex: number | null = null;
                        if (event.key === "ArrowDown") {
                          nextIndex = (currentIndex + 1) % REGIONS.length;
                        } else if (event.key === "ArrowUp") {
                          nextIndex = (currentIndex - 1 + REGIONS.length) % REGIONS.length;
                        } else if (event.key === "Home") {
                          nextIndex = 0;
                        } else if (event.key === "End") {
                          nextIndex = REGIONS.length - 1;
                        } else if (event.key === "Tab") {
                          setRegionOpen(false);
                        }
                        if (nextIndex === null) return;
                        event.preventDefault();
                        regionOptionRefs.current[nextIndex]?.focus();
                      }}
                    >
                      {REGIONS.map((option) => (
                        <button
                          key={option.value}
                          ref={(element) => {
                            const index = REGIONS.findIndex((item) => item.value === option.value);
                            regionOptionRefs.current[index] = element;
                          }}
                          type="button"
                          role="option"
                          aria-selected={region === option.value}
                          className={`feishu-region-option${region === option.value ? " is-selected" : ""}`}
                          onClick={() => {
                            setRegion(option.value);
                            setRegionOpen(false);
                            regionTriggerRef.current?.focus();
                          }}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
                <span className="feishu-field-help">Runtime 与构建产物将创建在该地域</span>
              </div>

              <div className="feishu-field">
                <label htmlFor="feishu-app-id">飞书 App ID</label>
                <input
                  id="feishu-app-id"
                  value={appId}
                  maxLength={128}
                  autoComplete="off"
                  disabled={deploymentActive}
                  placeholder="cli_xxxxxxxxxxxxxxxx"
                  onChange={(event) => {
                    setAppId(event.target.value);
                    if (appIdError) setAppIdError("");
                  }}
                  onBlur={() => setAppIdError(appId.trim() ? "" : "请输入飞书 App ID")}
                  aria-invalid={Boolean(appIdError)}
                  aria-describedby={`feishu-app-id-help${appIdError ? " feishu-app-id-error" : ""}`}
                />
                <span id="feishu-app-id-help" className="feishu-field-help">来自飞书开放平台的应用凭证</span>
                {appIdError ? <span id="feishu-app-id-error" className="feishu-field-error" role="alert">{appIdError}</span> : null}
              </div>

              <div className="feishu-field">
                <label htmlFor="feishu-app-secret">飞书 App Secret</label>
                <div className="feishu-secret-input">
                  <input
                    id="feishu-app-secret"
                    type={showSecret ? "text" : "password"}
                    value={appSecret}
                    maxLength={256}
                    autoComplete="off"
                    disabled={deploymentActive}
                    placeholder="请输入 App Secret"
                    onChange={(event) => {
                      setAppSecret(event.target.value);
                      if (appSecretError) setAppSecretError("");
                    }}
                    onBlur={() => setAppSecretError(appSecret.trim() ? "" : "请输入飞书 App Secret")}
                    aria-invalid={Boolean(appSecretError)}
                    aria-describedby={`feishu-app-secret-help${appSecretError ? " feishu-app-secret-error" : ""}`}
                  />
                  <button
                    type="button"
                    disabled={deploymentActive}
                    onClick={() => setShowSecret((visible) => !visible)}
                    aria-label={showSecret ? "隐藏 App Secret" : "显示 App Secret"}
                  >
                    {showSecret ? "隐藏" : "显示"}
                  </button>
                </div>
                <span id="feishu-app-secret-help" className="feishu-field-help">仅写入新 Runtime 的环境变量</span>
                {appSecretError ? <span id="feishu-app-secret-error" className="feishu-field-error" role="alert">{appSecretError}</span> : null}
              </div>
            </div>

            {deploymentStatus !== "idle" ? (
              <div className={`feishu-deployment-status is-${deploymentStatus}`} role={deploymentStatus === "failed" ? "alert" : "status"}>
                <div className="feishu-deployment-heading">
                  {deploymentStatus === "preparing" ? <TextShimmer as="strong">正在生成 basic 智能体</TextShimmer> : null}
                  {deploymentStatus === "running" ? <TextShimmer as="strong">{activeStage?.message || "正在创建 Runtime"}</TextShimmer> : null}
                  {deploymentStatus === "cancelling" ? <TextShimmer as="strong">正在取消部署</TextShimmer> : null}
                  {deploymentStatus === "succeeded" ? <strong><CheckIcon />飞书机器人 Runtime 已创建</strong> : null}
                  {deploymentStatus === "cancelled" ? <strong>部署已取消</strong> : null}
                  {deploymentStatus === "failed" ? <strong>创建失败</strong> : null}
                </div>
                {deploymentStatus === "preparing" || deploymentStatus === "running" || deploymentStatus === "cancelling" ? (
                  <ol className="feishu-deployment-steps">
                    {DEPLOYMENT_STEPS.map((step, index) => {
                      const done = deploymentStatus === "running" && index < currentStepIndex;
                      const active = index === currentStepIndex;
                      return (
                        <li key={step.phase} className={`${done ? "is-done" : ""}${active ? " is-active" : ""}`}>
                          <span aria-hidden="true">{done ? <CheckIcon /> : index + 1}</span>
                          {step.label}
                        </li>
                      );
                    })}
                  </ol>
                ) : null}
                {deployError ? <p className="feishu-deployment-error">{deployError}</p> : null}
                {result ? (
                  <div className="feishu-deployment-result">
                    <span>{result.agentName}</span>
                    <span>{REGIONS.find((option) => option.value === (result.region || region))?.label || result.region}</span>
                    {result.consoleUrl ? <a href={result.consoleUrl} target="_blank" rel="noreferrer">打开 Runtime 控制台<ExternalIcon /></a> : null}
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="feishu-form-actions">
              <div className="feishu-secrets-note">
                <strong>凭据处理</strong>
                <span>App Secret 仅用于本次部署，不会写入生成源码或浏览器存储。</span>
              </div>
              <div className="feishu-action-buttons">
                {deploymentStatus === "running" ? (
                  <button type="button" className="feishu-cancel" onClick={() => void cancelDeployment()}>
                    取消部署
                  </button>
                ) : null}
                <button type="submit" className="feishu-submit" disabled={!canSubmit}>
                  {deploymentActive ? "正在创建…" : "创建飞书机器人 Runtime"}
                </button>
              </div>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
