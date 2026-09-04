import {
  deployAgentkitProject,
  generateAgentProject,
  type DeployAgentkitResult,
  type DeployStage,
} from "../../adk/client";
import { emptyDraft, type AgentDraft } from "../../create/types";
import { automationT } from "../i18n";

export interface FeishuBotDeploymentRequest {
  agentName: string;
  appId: string;
  appSecret: string;
  region: "cn-beijing" | "cn-shanghai";
  taskId: string;
  onStage?: (stage: DeployStage) => void;
}

export function buildFeishuBotDraft(agentName: string): AgentDraft {
  return {
    ...emptyDraft(),
    name: agentName,
    description: automationT("feishu.generatedAgent.description"),
    instruction: automationT("feishu.generatedAgent.instruction"),
    deployment: { feishuEnabled: true },
  };
}

export async function deployFeishuBotRuntime(
  request: FeishuBotDeploymentRequest,
): Promise<DeployAgentkitResult> {
  const draft = buildFeishuBotDraft(request.agentName);
  const project = await generateAgentProject(draft);
  return deployAgentkitProject(
    project.name,
    project.files,
    {
      region: request.region,
      projectName: "default",
    },
    {
      taskId: request.taskId,
      sessionStorage: "in-memory",
      minInstance: 1,
      maxInstance: 1,
      description: draft.description,
      im: { feishu: { enabled: true } },
      envs: [
        { key: "FEISHU_APP_ID", value: request.appId },
        { key: "FEISHU_APP_SECRET", value: request.appSecret },
      ],
      onStage: request.onStage,
    },
  );
}
