import type {
  SandboxModel,
  SandboxStatus,
  SandboxThreadSnapshot,
} from "../adk/sandbox";
import type { Turn, TurnActivityDetail } from "../blocks";
import { i18n } from "../i18n/runtime";
import { sandboxT } from "./sandboxI18n";

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

interface SandboxSlashCommandDefinition {
  name: SandboxSlashCommandName;
  usage: string;
}

export const SANDBOX_SLASH_COMMANDS: readonly SandboxSlashCommandDefinition[] = [
  {
    name: "model",
    usage: "/model [model]",
  },
  {
    name: "models",
    usage: "/models",
  },
  {
    name: "skill",
    usage: "/skill",
  },
  {
    name: "skills",
    usage: "/skills",
  },
  {
    name: "new",
    usage: "/new",
  },
  {
    name: "resume",
    usage: "/resume [thread]",
  },
  {
    name: "fork",
    usage: "/fork",
  },
  {
    name: "compact",
    usage: "/compact",
  },
  {
    name: "archive",
    usage: "/archive",
  },
  {
    name: "status",
    usage: "/status",
  },
  {
    name: "clear",
    usage: "/clear",
  },
  {
    name: "help",
    usage: "/help",
  },
];

function localizedCommand(
  command: SandboxSlashCommandDefinition,
): SandboxSlashCommand {
  return {
    ...command,
    description: sandboxT(`commands.${command.name}.description`),
    keywords: sandboxT(`commands.${command.name}.keywords`).split(/\s+/),
  };
}

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
  return SANDBOX_SLASH_COMMANDS.map(localizedCommand)
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
  if (!query) {
    return SANDBOX_SLASH_COMMANDS.findIndex(
      (candidate) => candidate.name === command.name,
    );
  }
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
  return SANDBOX_SLASH_COMMANDS.map(localizedCommand).map((command) => ({
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
      label: model.id === currentModel
        ? sandboxT("commands.currentModel")
        : sandboxT("commands.availableModel"),
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
    {
      label: sandboxT("commands.workspace"),
      value: status.cwd || sandboxT("commands.notSet"),
      code: Boolean(status.cwd),
    },
  ];
  if (status.model) {
    details.push({
      label: sandboxT("commands.modelLabel"),
      value: status.model,
      code: true,
    });
  }
  details.push({
    label: sandboxT("commands.statusLabel"),
    value: status.busy
      ? sandboxT("commands.running")
      : sandboxT("commands.idle"),
  });
  if (status.threadTotal) {
    details.push({
      label: sandboxT("commands.totalTokens"),
      value: status.threadTotal.totalTokens.toLocaleString(
        i18n.resolvedLanguage ?? i18n.language,
      ),
    });
  }
  if (status.modelContextWindow !== undefined) {
    details.push({
      label: sandboxT("commands.contextWindow"),
      value: status.modelContextWindow.toLocaleString(
        i18n.resolvedLanguage ?? i18n.language,
      ),
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
    if (message.role === "user" && message.images?.length) {
      blocks.push({
        kind: "attachment",
        files: message.images.map((image, index) => ({
          id: `${message.id}-image-${index}`,
          mimeType: image.mimeType,
          data: image.data,
          name: image.alt || image.name || sandboxT("commands.imageFallback"),
        })),
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
