import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
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
import type { EnvVar } from "./veadkCatalog";
import {
  isMigrationRuntimeEnvironmentKey,
  isSecretEnvironmentKey,
} from "../migrations/deploymentEnvironment";

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
  const { t } = useTranslation("create");
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
  const environment = delivery.environment ?? {
    required: [],
    optional: [],
    defaults: {},
  };
  const [deploymentEnvValues, setDeploymentEnvValues] = useState<
    Record<string, string>
  >(() => ({ ...environment.defaults }));
  const deploymentSecretEnv = environment.required
    .filter(isMigrationRuntimeEnvironmentKey)
    .filter(isSecretEnvironmentKey)
    .map((key) => ({ key, label: key }));
  const deploymentEnv: EnvVar[] = [
    ...environment.required
      .filter(isMigrationRuntimeEnvironmentKey)
      .filter((key) => !isSecretEnvironmentKey(key))
      .map((key) => ({
        key,
        required: true,
        comment: key,
        placeholder: t("intelligentDeployment.env.requiredPlaceholder", { key }),
      })),
    ...environment.optional
      .filter(isMigrationRuntimeEnvironmentKey)
      .map((key) => ({
        key,
        required: false,
        comment: key,
        placeholder: t("intelligentDeployment.env.optionalPlaceholder", { key }),
      })),
  ];
  const runtimeNameError = runtimeNameProblem(project.name, (key) =>
    t(`validation.runtimeName.${key}`),
  );
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
      deploymentEnv={deploymentEnv}
      requiredSecretEnv={deploymentSecretEnv}
      deploymentEnvValues={deploymentEnvValues}
      onDeploymentEnvChange={(key, value) =>
        setDeploymentEnvValues((current) => ({ ...current, [key]: value }))
      }
      deploymentActionLabel={t("common.deploy")}
      deployDisabled={Boolean(runtimeNameError) || runtimeNameAvailable === false || runtimeNameChecking}
      deployDisabledReason={
        runtimeNameError
          ?? (runtimeNameAvailable === false
            ? t("intelligentDeployment.runtimeNameExists")
            : runtimeNameChecking
              ? t("intelligentDeployment.checkingRuntimeName")
              : undefined)
      }
      deploymentTelemetry={{
        source: "intelligent_development",
        createMode: "intelligent",
        aiAssisted: true,
      }}
      onBack={onBack}
      backLabel={t("intelligentDeployment.back")}
      deploymentPrimaryPane={
        <section
          className="trusted-source-pane"
          aria-label={delivery.verified ? t("intelligentDeployment.verifiedSource") : t("intelligentDeployment.deployableSource")}
        >
          <div className="trusted-source-pane__badge">
            {delivery.verified ? t("intelligentDeployment.verifiedByCodex") : t("intelligentDeployment.deployableSource")}
          </div>
          <h2>{delivery.agentName}</h2>
          <label className="trusted-source-pane__runtime-name">
            <span>{t("intelligentDeployment.runtimeName")}</span>
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
            <div><dt>{t("intelligentDeployment.entryPoint")}</dt><dd><code>{delivery.entryPoint}</code></dd></div>
            <div><dt>{t("intelligentDeployment.files")}</dt><dd>{delivery.fileCount}</dd></div>
            <div><dt>Artifact</dt><dd><code>{delivery.artifactSha256.slice(0, 16)}</code></dd></div>
            <div><dt>{t("intelligentDeployment.validationReport")}</dt><dd><code>{delivery.validationReportSha256.slice(0, 16)}</code></dd></div>
          </dl>
          <p>
            {delivery.verified
              ? t("intelligentDeployment.verifiedHint")
              : t("intelligentDeployment.unverifiedHint")}
          </p>
        </section>
      }
    />
  );
}
