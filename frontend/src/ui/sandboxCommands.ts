import type {
  SandboxModel,
  SandboxStatus,
  SandboxThreadSnapshot,
} from "../adk/sandbox";
import type { Turn, TurnActivityDetail } from "../blocks";

export type SandboxSlashCommandName =
  | "model"
  | "models"
  | "skill"
  | "skills"
  | "new"
  | "resume"
  | "fork"
  | "compact"
  | "archive"
  | "status"
  | "clear"
  | "help";

export interface SandboxSlashCommand {
  name: SandboxSlashCommandName;
  usage: string;
  description: string;
  keywords: string[];
}

export const SANDBOX_SLASH_COMMANDS: readonly SandboxSlashCommand[] = [
  {
    name: "model",
    usage: "/model [model]",
    description: "显示或切换当前对话模型",
    keywords: ["模型", "switch"],
  },
  {
    name: "models",
    usage: "/models",
    description: "列出 app-server 可用模型",
    keywords: ["模型列表", "list"],
  },
  {
    name: "skill",
    usage: "/skill",
    description: "浏览并调用当前工作区可用的 Skill",
    keywords: ["技能", "workflow"],
  },
  {
    name: "skills",
    usage: "/skills",
    description: "浏览并调用当前工作区可用的 Skills",
    keywords: ["技能列表", "workflow", "list"],
  },
  {
    name: "new",
    usage: "/new",
    description: "开始一个新对话",
    keywords: ["新建", "对话"],
  },
  {
    name: "resume",
    usage: "/resume [thread]",
    description: "打开历史会话或恢复指定 thread",
    keywords: ["历史", "恢复", "session"],
  },
  {
    name: "fork",
    usage: "/fork",
    description: "从当前上下文分叉一个新对话",
    keywords: ["分叉", "branch"],
  },
  {
    name: "compact",
    usage: "/compact",
    description: "压缩当前对话上下文",
    keywords: ["压缩", "上下文"],
  },
  {
    name: "archive",
    usage: "/archive",
    description: "归档当前对话并新建对话",
    keywords: ["归档", "关闭"],
  },
  {
    name: "status",
    usage: "/status",
    description: "显示当前连接、thread、模型与 token 状态",
    keywords: ["状态", "连接", "token"],
  },
  {
    name: "clear",
    usage: "/clear",
    description: "清空当前视图并开始新对话",
    keywords: ["清空", "重置"],
  },
  {
    name: "help",
    usage: "/help",
    description: "显示 Sandbox 支持的快捷命令",
    keywords: ["帮助", "命令"],
  },
];

export interface SandboxSlashInvocation {
  name: string;
  argument: string;
}

export function parseSandboxSlash(
  value: string,
): SandboxSlashInvocation | undefined {
  const match = value.trim().match(/^\/([^\s]+)(?:\s+([\s\S]*))?$/);
  if (!match) return undefined;
  return {
    name: match[1].toLocaleLowerCase(),
    argument: match[2]?.trim() ?? "",
  };
}

export function matchingSandboxCommands(
  query: string,
): SandboxSlashCommand[] {
  const normalized = query.toLocaleLowerCase();
  return SANDBOX_SLASH_COMMANDS
    .filter((command) =>
      !normalized ||
      [command.name, command.description, ...command.keywords].some((value) =>
        value.toLocaleLowerCase().includes(normalized)
      )
    )
    .sort((left, right) =>
      commandScore(left, normalized) - commandScore(right, normalized)
    )
    .slice(0, 12);
}

function commandScore(
  command: SandboxSlashCommand,
  query: string,
): number {
  if (!query) return SANDBOX_SLASH_COMMANDS.indexOf(command);
  if (command.name === query) return 0;
  if (command.name.startsWith(query)) return 1;
  if (command.name.includes(query)) return 2;
  return 3;
}

export function matchingSandboxModels(
  models: readonly SandboxModel[],
  query: string,
): SandboxModel[] {
  const normalized = query.toLocaleLowerCase();
  return models
    .filter((model) =>
      !normalized ||
      `${model.id} ${model.displayName} ${model.description}`
        .toLocaleLowerCase()
        .includes(normalized)
    )
    .sort((left, right) => {
      if (!normalized) return Number(right.isDefault) - Number(left.isDefault);
      const leftId = left.id.toLocaleLowerCase();
      const rightId = right.id.toLocaleLowerCase();
      const score = (id: string, displayName: string) =>
        id === normalized
          ? 0
          : id.startsWith(normalized)
            ? 1
            : displayName.toLocaleLowerCase().startsWith(normalized)
              ? 2
              : 3;
      return score(leftId, left.displayName) -
        score(rightId, right.displayName);
    })
    .slice(0, 12);
}

export function sandboxHelpDetails(): TurnActivityDetail[] {
  return SANDBOX_SLASH_COMMANDS.map((command) => ({
    label: command.usage,
    value: command.description,
  }));
}

export function sandboxModelDetails(
  models: readonly SandboxModel[],
  currentModel?: string,
): TurnActivityDetail[] {
  return models.map((model) => {
    const displayName = model.displayName.trim();
    const modelName = displayName && displayName !== model.id
      ? `${displayName} · ${model.id}`
      : model.id;
    return {
      label: model.id === currentModel ? "当前模型" : "可用模型",
      value: model.description
        ? `${modelName} — ${model.description}`
        : modelName,
      code: false,
    };
  });
}

export function sandboxStatusDetails(
  status: SandboxStatus,
): TurnActivityDetail[] {
  const details: TurnActivityDetail[] = [
    { label: "Thread", value: status.threadId, code: true },
    { label: "工作空间", value: status.cwd || "未设置", code: Boolean(status.cwd) },
  ];
  if (status.model) details.push({ label: "模型", value: status.model, code: true });
  details.push({
    label: "状态",
    value: status.busy ? "运行中" : "空闲",
  });
  if (status.threadTotal) {
    details.push({
      label: "累计 Token",
      value: status.threadTotal.totalTokens.toLocaleString(),
    });
  }
  if (status.modelContextWindow !== undefined) {
    details.push({
      label: "上下文窗口",
      value: status.modelContextWindow.toLocaleString(),
    });
  }
  return details;
}

export function sandboxSnapshotTurns(snapshot: SandboxThreadSnapshot): Turn[] {
  return snapshot.messages.map((message) => {
    const blocks: Turn["blocks"] = [];
    if (message.role === "user" && message.skillNames?.length) {
      blocks.push({
        kind: "invocation",
        value: {
          skills: message.skillNames.map((name) => ({
            name,
            description: "",
          })),
        },
      });
    }
    if (message.content) blocks.push({ kind: "text", text: message.content });
    return {
      role: message.role,
      blocks,
      meta: {
        localId: message.id,
        ts: message.timestamp / 1_000,
      },
    };
  });
}
