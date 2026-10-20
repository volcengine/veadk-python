import { useState } from "react";
import { useTranslation } from "react-i18next";
import { deployAgentkitProject } from "../../adk/client";
import { defaultCloudRegion, type CloudProvider } from "../../adk/cloudProvider";
import { ProjectPreview, type ProjectPreviewProps } from "../../ui/ProjectPreview";
import { generateRuntimeName, runtimeNameProblem } from "../runtimeName";
import type { AgentProject } from "../project";
import type { NetworkConfig } from "../types";
import type { NativeConfigDraft } from "./nativeConfig";

export interface NativeDeploymentCallbacks {
  cloudProvider?: CloudProvider;
  initialDeployRegion?: string;
  onDeploymentTaskChange?: ProjectPreviewProps["onDeploymentTaskChange"];
  onDeploymentStarted?: ProjectPreviewProps["onDeploymentStarted"];
  onDeploymentComplete?: ProjectPreviewProps["onDeploymentComplete"];
}

interface Props extends NativeDeploymentCallbacks {
  project: AgentProject;
  draft: NativeConfigDraft;
  onBack: () => void;
}

export function NativeDeployment({ project, draft, onBack, cloudProvider = "volcengine", initialDeployRegion, ...callbacks }: Props) {
  const { t } = useTranslation("create");
  const [runtimeName, setRuntimeName] = useState(() => generateRuntimeName("deepseek-harness"));
  const [region, setRegion] = useState(initialDeployRegion ?? defaultCloudRegion(cloudProvider));
  const [network, setNetwork] = useState<NetworkConfig>();
  const requiredKeys = new Set(draft.providers.map(provider => provider.apiKeyEnv.trim()));
  if (!draft.fields["agent-default-model.provider"] || draft.fields["agent-default-model.provider"] === "deepseek-official" || draft.allowedModels.some(route => route.provider === "deepseek-official")) {
    requiredKeys.add(draft.fields["llm-deepseek.apiKeyEnv"]?.trim() || "DEEPSEEK_API_KEY");
  }
  const nameError = runtimeNameProblem(runtimeName, key => t(`validation.runtimeName.${key}`));
  const deploy: NonNullable<ProjectPreviewProps["onDeploy"]> = (candidate, onStage, options) => deployAgentkitProject(
    candidate.name,
    candidate.files,
    {
      region,
      projectName: "default",
      network: network && network.mode !== "public" ? {
        mode: network.mode,
        vpc_id: network.vpcId,
        subnet_ids: network.subnetIds,
        enable_shared_internet_access: network.enableSharedInternetAccess,
      } : undefined,
    },
    { ...options, runtimeName, onStage, description: "DeepSeek Harness" },
  );
  return <ProjectPreview
    {...callbacks}
    project={{ ...project, name: runtimeName }}
    agentName="DeepSeek Harness"
    showGitSync={false}
    showMessageChannels={false}
    showEvaluationSets={false}
    cloudProvider={cloudProvider}
    onDeploy={deploy}
    onBack={onBack}
    deploymentRuntimeName={runtimeName}
    deploymentRuntimeNameCustomized
    onDeploymentRuntimeNameChange={setRuntimeName}
    deployRegion={region}
    onDeployRegionChange={setRegion}
    network={network}
    onNetworkChange={setNetwork}
    requiredSecretEnv={[...requiredKeys].filter(Boolean).map(key => ({ key, label: key }))}
    deployDisabled={Boolean(nameError)}
    deployDisabledReason={nameError ?? undefined}
  />;
}
