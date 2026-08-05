import {
  deployAgentkitProject,
  generateAgentProject,
  type DeployAgentkitResult,
  type DeployStage,
} from "../../adk/client";
import { emptyDraft, type AgentDraft } from "../../create/types";

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
    description: "一个通过飞书接收消息并提供帮助的智能助手。",
    instruction:
      "你是一个通过飞书为用户提供帮助的智能助手。准确理解用户问题，给出简洁、可靠的回答；信息不足时先提问澄清，不要臆造事实。",
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
