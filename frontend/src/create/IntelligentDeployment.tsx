import { useEffect, useState } from "react";
import {
  checkRuntimeNameAvailability,
  deployAgentkitProject,
  type DeployStage,
  type IntelligentDevelopmentDeploymentSource,
} from "../adk/client";
import { defaultCloudRegion, type CloudProvider } from "../adk/cloudProvider";
import type { IntelligentDevelopmentReleaseRef } from "../blocks";
import { ProjectPreview, type DeployResult, type DeploymentTaskUpdate } from "../ui/ProjectPreview";
import { generateRuntimeName, runtimeNameProblem } from "./runtimeName";
import type { AgentProject } from "./project";
import type { NetworkConfig } from "./types";

export interface IntelligentDeploymentProps {
  delivery: IntelligentDevelopmentReleaseRef;
  onBack: () => void;
  onAgentAdded?: (agentId: string, agentName: string) => void | Promise<void>;
  onDeploymentTaskChange?: (task: DeploymentTaskUpdate) => void;
  onDeploymentStarted?: (task: DeploymentTaskUpdate) => void;
  onDeploymentComplete?: (result: DeployResult) => void | Promise<void>;
  cloudProvider?: CloudProvider;
  initialDeployRegion?: string;
}

export function IntelligentDeployment({
  delivery,
  onBack,
  onAgentAdded,
  onDeploymentTaskChange,
  onDeploymentStarted,
  onDeploymentComplete,
  cloudProvider = "volcengine",
  initialDeployRegion,
}: IntelligentDeploymentProps) {
  const [deployRegion, setDeployRegion] = useState(
    initialDeployRegion ?? defaultCloudRegion(cloudProvider),
  );
  const [network, setNetwork] = useState<NetworkConfig>();
  const [runtimeNameAvailable, setRuntimeNameAvailable] = useState<boolean | null>(null);
  const [runtimeNameChecking, setRuntimeNameChecking] = useState(false);
  const [project, setProject] = useState<AgentProject>(() => ({
    name: generateRuntimeName(delivery.agentName),
    files: delivery.files ?? [],
  }));
  const runtimeNameError = runtimeNameProblem(project.name);
  useEffect(() => {
    if (runtimeNameError) {
      setRuntimeNameAvailable(null);
      return;
    }
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      setRuntimeNameChecking(true);
      void checkRuntimeNameAvailability(project.name, deployRegion)
        .then((value) => {
          if (!controller.signal.aborted) setRuntimeNameAvailable(value.available === true);
        })
        .catch(() => {
          if (!controller.signal.aborted) setRuntimeNameAvailable(null);
        })
        .finally(() => {
          if (!controller.signal.aborted) setRuntimeNameChecking(false);
        });
    }, 250);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [deployRegion, project.name, runtimeNameError]);
  const source: IntelligentDevelopmentDeploymentSource = {
    kind: "intelligentDevelopment",
    sessionId: delivery.sessionId,
    ...(delivery.projectId && delivery.versionId
      ? { projectId: delivery.projectId, versionId: delivery.versionId }
      : {}),
    artifactSha256: delivery.artifactSha256,
    validationReportSha256: delivery.validationReportSha256,
    ...(delivery.verified ? {} : { acknowledgeUnverified: true }),
  };

  async function deploy(
    candidate: AgentProject,
    onStage?: (stage: DeployStage) => void,
    options?: Parameters<typeof deployAgentkitProject>[3],
  ) {
    const runtimeNetwork = network && network.mode !== "public"
      ? {
          mode: network.mode,
          vpc_id: network.vpcId,
          subnet_ids: network.subnetIds,
          enable_shared_internet_access: network.enableSharedInternetAccess,
        }
      : undefined;
    return deployAgentkitProject(
      candidate.name,
      [],
      { region: deployRegion, projectName: "default", network: runtimeNetwork },
      { ...options, onStage, runtimeName: candidate.name, source },
    );
  }

  return (
    <ProjectPreview
      cloudProvider={cloudProvider}
      project={project}
      agentName={project.name}
      onDeploy={deploy}
      onAgentAdded={onAgentAdded}
      onDeploymentTaskChange={onDeploymentTaskChange}
      onDeploymentStarted={onDeploymentStarted}
      onDeploymentComplete={onDeploymentComplete}
      network={network}
      onNetworkChange={setNetwork}
      deployRegion={deployRegion}
      onDeployRegionChange={setDeployRegion}
      deploymentActionLabel="部署"
      deployDisabled={Boolean(runtimeNameError) || runtimeNameAvailable === false || runtimeNameChecking}
      deployDisabledReason={
        runtimeNameError
          ?? (runtimeNameAvailable === false
            ? "Runtime 名称已存在，请更换后重试"
            : runtimeNameChecking
              ? "正在检查 Runtime 名称"
              : undefined)
      }
      deploymentTelemetry={{
        source: "intelligent_development",
        createMode: "intelligent",
        aiAssisted: true,
      }}
      onBack={onBack}
      backLabel="返回开发会话"
      deploymentPrimaryPane={
        <section
          className="trusted-source-pane"
          aria-label={delivery.verified ? "已验证源码" : "可部署源码"}
        >
          <div className="trusted-source-pane__badge">
            {delivery.verified ? "已通过 Codex 云端验证" : "可部署源码"}
          </div>
          <h2>{delivery.agentName}</h2>
          <label className="trusted-source-pane__runtime-name">
            <span>Runtime 名称</span>
            <input
              value={project.name}
              maxLength={64}
              onChange={(event) => setProject((current) => ({
                ...current,
                name: event.target.value,
              }))}
            />
          </label>
          <dl>
            <div><dt>入口</dt><dd><code>{delivery.entryPoint}</code></dd></div>
            <div><dt>文件</dt><dd>{delivery.fileCount}</dd></div>
            <div><dt>Artifact</dt><dd><code>{delivery.artifactSha256.slice(0, 16)}</code></dd></div>
            <div><dt>验证报告</dt><dd><code>{delivery.validationReportSha256.slice(0, 16)}</code></dd></div>
          </dl>
          <p>
            {delivery.verified
              ? "源码由服务端从已验证交付物物化，浏览器文件不能替换。"
              : "源码已由服务端安全物化，部署前请确认 Runtime 配置。"}
          </p>
        </section>
      }
    />
  );
}
