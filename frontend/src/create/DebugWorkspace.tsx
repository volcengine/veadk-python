import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import {
  createGeneratedAgentTestRun,
  createGeneratedAgentTestSession,
  deleteGeneratedAgentTestRun,
  runGeneratedAgentTestSSE,
  type GeneratedAgentTestRun,
} from "../adk/client";
import {
  defaultModelApiBase,
  type CloudProvider,
} from "../adk/cloudProvider";
import { applyEvent, emptyAcc, type Block } from "../blocks";
import {
  AgentDebugConfigPanel,
  type AgentDebugConfigValue,
} from "../ui/AgentDebugConfigPanel";
import {
  activeAgentModelName,
  type AgentModelConfigValue,
} from "../ui/AgentModelConfigFields";
import { Blocks, ThinkingPlaceholder } from "../ui/Blocks";
import { DeploymentErrorMessage } from "../ui/DeploymentErrorMessage";
import { Markdown } from "../ui/Markdown";
import sendIcon from "./assets/create-workspace/send.svg";
import { CreateNavbar } from "./CreateNavbar";
import {
  CreationFlowCanvas,
  type CreationFlowAgentOverrides,
  type CreationFlowAgentSelection,
} from "./CreationFlowCanvas";
import { customModelEnvironmentBindings } from "./customModelCredentials";
import { emptyDraft, type AgentDraft } from "./types";
import "./DebugWorkspace.css";

interface DebugWorkspaceProps {
  agentDraft?: AgentDraft | null;
  agentOverrides?: CreationFlowAgentOverrides;
  agentModelConfigs?: Record<string, AgentModelConfigValue>;
  cloudProvider: CloudProvider;
  onBack: () => void;
  onExit: () => void;
}

const SUGGESTED_QUESTIONS = [
  "规则核查：帮我确认这项规则要求",
  "问题排查：帮我判断问题并给出建议",
  "问答咨询：请根据知识库解答我的问题",
];

const INITIAL_DEBUG_CONFIG: AgentDebugConfigValue = {
  agentName: "Meeting Assistant",
  description:
    "Prepares you for meetings by gathering and summarizing relevant information。",
  modelConfig: {
    category: "volcano-ark",
    customProvider: "",
    customModelName: "",
    customBaseUrl: "",
    customApiKey: "",
    volcanoApiKey: "",
    volcanoModelName: "doubao-seed-2.0-lite",
  },
  systemPrompt: [
    "你是一个专业、可靠的智能助手。",
    "你的目标是准确理解用户的需求，并给出条理清晰、简洁有用的回答。",
    "约束：",
    "• 信息不足时主动提问澄清，不要臆造事实。",
    "• 需要时合理调用可用的工具，并说明关键结论。",
    "• 保持礼貌、专业的语气。",
  ].join("\n"),
};

type DebugGroup = "baseline" | "comparison";

interface DebugAgentConfigState {
  savedConfig: AgentDebugConfigValue;
  draft: AgentDebugConfigValue;
  phase: "idle" | "starting" | "ready" | "sending" | "error";
  runtimeSnapshot: string;
  messages: DebugMessage[];
}

interface DebugMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  blocks?: Block[];
  error?: string;
}

interface DebugRuntime {
  run: GeneratedAgentTestRun;
  sessionId: string;
  snapshot: string;
}

interface DebugGroupState {
  configOpen: boolean;
  agentConfigs: Record<string, DebugAgentConfigState>;
}

function createDebugGroupState(): DebugGroupState {
  return {
    configOpen: false,
    agentConfigs: {},
  };
}

function initialAgentSelection(
  agentDraft: AgentDraft | null,
  agentOverrides: CreationFlowAgentOverrides,
): CreationFlowAgentSelection {
  const id = agentDraft ? "agent-root" : "meeting-assistant";
  const base: CreationFlowAgentSelection = agentDraft
    ? {
        id,
        title: agentDraft.name || "Agent",
        description: agentDraft.description,
        systemPrompt: agentDraft.instruction,
        model:
          agentDraft.modelName ||
          agentDraft.model ||
          INITIAL_DEBUG_CONFIG.modelConfig.volcanoModelName,
        modelSource: agentDraft.modelSource === "custom" ? "custom" : "ark",
        modelProvider: agentDraft.modelProvider ?? "",
        modelApiBase: agentDraft.modelApiBase ?? "",
        tone: "root",
      }
    : {
        id,
        title: INITIAL_DEBUG_CONFIG.agentName,
        description: INITIAL_DEBUG_CONFIG.description,
        systemPrompt: INITIAL_DEBUG_CONFIG.systemPrompt,
        model: INITIAL_DEBUG_CONFIG.modelConfig.volcanoModelName,
        modelSource: "ark",
        modelProvider: "",
        modelApiBase: "",
        tone: "root",
      };
  const override = agentOverrides[id];
  return {
    ...base,
    title: override?.title ?? base.title,
    description: override?.description ?? base.description,
    systemPrompt: override?.systemPrompt ?? base.systemPrompt,
    model: override?.model ?? base.model,
  };
}

function debugConfigFromAgent(
  agent: CreationFlowAgentSelection,
  syncedModelConfig?: AgentModelConfigValue,
): AgentDebugConfigValue {
  return {
    agentName: agent.title,
    description: agent.description,
    modelConfig: syncedModelConfig ?? {
      category: agent.modelSource === "custom" ? "custom" : "volcano-ark",
      customProvider: agent.modelProvider,
      customModelName: agent.modelSource === "custom" ? agent.model : "",
      customBaseUrl: agent.modelApiBase,
      customApiKey: "",
      volcanoApiKey: "",
      volcanoModelName:
        agent.modelSource === "custom"
          ? ""
          : agent.model || INITIAL_DEBUG_CONFIG.modelConfig.volcanoModelName,
    },
    systemPrompt: agent.systemPrompt,
  };
}

function debugAgentConfigState(
  agent: CreationFlowAgentSelection,
  syncedModelConfig?: AgentModelConfigValue,
): DebugAgentConfigState {
  const config = debugConfigFromAgent(agent, syncedModelConfig);
  return {
    savedConfig: config,
    draft: { ...config, modelConfig: { ...config.modelConfig } },
    phase: "idle",
    runtimeSnapshot: "",
    messages: [],
  };
}

function selectedAgentDraft(
  root: AgentDraft | null,
  agentId: string,
): AgentDraft | null {
  if (!root) return null;
  if (agentId === "agent-root") return root;
  const match = /^agent-(\d+(?:-\d+)*)$/.exec(agentId);
  if (!match) return null;
  let current = root;
  for (const segment of match[1].split("-")) {
    const child = current.subAgents[Number(segment)];
    if (!child) return null;
    current = child;
  }
  return current;
}

function debugDraftForAgent(
  root: AgentDraft | null,
  agentId: string,
  config: AgentDebugConfigValue,
  cloudProvider: CloudProvider,
): AgentDraft {
  const source = selectedAgentDraft(root, agentId) ?? emptyDraft(cloudProvider);
  const modelConfig = config.modelConfig;
  const modelName = activeAgentModelName(modelConfig).trim();
  const sourceDeployment = source.deployment;
  const envValues = { ...(sourceDeployment?.envValues ?? {}) };
  const draft: AgentDraft = {
    ...source,
    name: config.agentName,
    description: config.description,
    instruction: config.systemPrompt,
    cloudProvider,
    model: modelName,
    modelName,
    modelSource: modelConfig.category === "custom" ? "custom" : "ark",
    modelProvider:
      modelConfig.category === "custom" ? modelConfig.customProvider : "",
    modelApiBase:
      modelConfig.category === "custom" ? modelConfig.customBaseUrl : "",
    deployment: {
      feishuEnabled: sourceDeployment?.feishuEnabled ?? false,
      modelApiKeyId: sourceDeployment?.modelApiKeyId,
      modelApiKeyName: sourceDeployment?.modelApiKeyName,
      envValues,
    },
  };

  if (modelConfig.category === "custom") {
    const binding = customModelEnvironmentBindings(
      draft,
      defaultModelApiBase(cloudProvider),
    )[0];
    if (binding && modelConfig.customApiKey.trim()) {
      envValues[binding.apiKeyKey] = modelConfig.customApiKey.trim();
    }
  } else if (modelConfig.volcanoApiKey.trim()) {
    envValues.MODEL_AGENT_API_KEY = modelConfig.volcanoApiKey.trim();
  }
  return draft;
}

function DebugTitleIcon() {
  return (
    <svg viewBox="0 0 40 40" aria-hidden="true">
      <g transform="translate(4.615 4.615)">
        <path d="M30.7695.001h-7.6924v7.6924h7.6924v7.6923L15.3848 30.7695H7.6924v.001H0V0h30.7695v.001ZM7.6924 23.0771h15.3847V7.6924H7.6924v15.3847Zm23.0771 7.6934h-7.6924v-.001h7.6924v.001Z" />
        <path d="M23.0769 23.0779h7.6923v7.6923h-7.6923z" />
      </g>
    </svg>
  );
}

function QuestionIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <g transform="translate(.6667 .6667)">
        <path d="M13.3333 7.33333C13.3333 4.01962 10.647 1.33333 7.33333 1.33333C4.01962 1.33333 1.33333 4.01962 1.33333 7.33333C1.33333 9.09791 2.0946 10.6836 3.30859 11.7826C3.53039 11.9833 3.59143 12.3073 3.45768 12.5749L3.07878 13.3333H7.31706L7.64648 13.3249C10.8143 13.1623 13.3333 10.542 13.3333 7.33333ZM14.6667 7.33333C14.6667 11.257 11.5855 14.4611 7.71029 14.6576C7.70452 14.6578 7.69848 14.6581 7.69271 14.6582L7.34961 14.6667H2C1.76897 14.6667 1.55442 14.5468 1.43294 14.3503C1.31158 14.1538 1.30039 13.9084 1.40365 13.7018L2.04753 12.4121C.781548 11.0949 0 9.30586 0 7.33333C0 3.28325 3.28325 0 7.33333 0C11.3834 0 14.6667 3.28325 14.6667 7.33333Z" />
        <path d="M9.66667 5.33333C10.0349 5.33333 10.3333 5.63181 10.3333 6C10.3333 6.36819 10.0349 6.66667 9.66667 6.66667H5C4.63181 6.66667 4.33333 6.36819 4.33333 6C4.33333 5.63181 4.63181 5.33333 5 5.33333H9.66667Z" />
        <path d="M7.66667 8C8.03486 8 8.33333 8.29848 8.33333 8.66667C8.33333 9.03486 8.03486 9.33333 7.66667 9.33333H5C4.63181 9.33333 4.33333 9.03486 4.33333 8.66667C4.33333 8.29848 4.63181 8 5 8H7.66667Z" />
      </g>
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg viewBox="0 0 18 18" aria-hidden="true">
      <path d="M2.25 6h9M11.25 6A2.25 2.25 0 1 0 15.75 6a2.25 2.25 0 0 0-4.5 0ZM6.75 12h9M6.75 12a2.25 2.25 0 1 0-4.5 0 2.25 2.25 0 0 0 4.5 0Z" />
    </svg>
  );
}

function CloseConfigIcon() {
  return (
    <svg viewBox="0 0 18 18" aria-hidden="true">
      <path d="M4.5 4.5 13.5 13.5M13.5 4.5 4.5 13.5" />
    </svg>
  );
}

interface DebugPanelContentProps {
  messages: DebugMessage[];
  busy: boolean;
  onQuestionSelect: (question: string) => void;
}

function DebugPanelContent({
  messages,
  busy,
  onQuestionSelect,
}: DebugPanelContentProps) {
  if (messages.length > 0) {
    return (
      <div
        className={`debug-workspace__conversation transcript${busy ? " is-streaming" : ""}`}
        aria-live="polite"
      >
        {messages.map((message, index) => {
          const isLast = index === messages.length - 1;
          if (message.role === "user") {
            return (
              <div key={message.id} className="turn turn--user">
                <div className="bubble">
                  <Markdown text={message.content} />
                </div>
              </div>
            );
          }
          return (
            <div key={message.id} className="turn turn--assistant">
              {message.error ? (
                <DeploymentErrorMessage
                  message={message.error}
                  className="debug-workspace__conversation-error"
                  defaultExpanded
                />
              ) : message.blocks && message.blocks.length > 0 ? (
                <Blocks
                  blocks={message.blocks}
                  streaming={busy && isLast}
                  onAction={() => {}}
                />
              ) : busy && isLast ? (
                <ThinkingPlaceholder />
              ) : (
                <div className="turn-empty">本次没有返回可显示的内容。</div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="debug-workspace__intro">
      <div className="debug-workspace__title">
        <span className="debug-workspace__title-icon"><DebugTitleIcon /></span>
        <h2>调试你的 Agent</h2>
      </div>

      <div className="debug-workspace__suggestions">
        <p>线上高频问题</p>
        <div className="debug-workspace__suggestion-list">
          {SUGGESTED_QUESTIONS.map((question) => (
            <button
              key={question}
              type="button"
              className="debug-workspace__suggestion"
              onClick={() => onQuestionSelect(question)}
            >
              <QuestionIcon />
              <span>{question}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

interface DebugComposerProps {
  prompt: string;
  disabled: boolean;
  onPromptChange: (prompt: string) => void;
  onSend: () => void;
}

function DebugComposer({
  prompt,
  disabled,
  onPromptChange,
  onSend,
}: DebugComposerProps) {
  const compositionRef = useRef(false);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    const isSafariComposition = event.nativeEvent.keyCode === 229;
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !compositionRef.current &&
      !isSafariComposition
    ) {
      event.preventDefault();
      onSend();
    }
  };

  return (
    <div className="debug-workspace__composer-wrap">
      <div className="debug-workspace__composer">
        <textarea
          value={prompt}
          onChange={(event) => onPromptChange(event.target.value)}
          onKeyDown={handleKeyDown}
          onCompositionStart={() => {
            compositionRef.current = true;
          }}
          onCompositionEnd={() => {
            compositionRef.current = false;
          }}
          placeholder="请输入你的问题"
          aria-label="请输入你的问题"
        />
        <button
          type="button"
          disabled={!prompt.trim() || disabled}
          aria-label="发送调试问题"
          onClick={onSend}
        >
          <img src={sendIcon} alt="" />
        </button>
      </div>
    </div>
  );
}

export function DebugWorkspace({
  agentDraft = null,
  agentOverrides = {},
  agentModelConfigs = {},
  cloudProvider,
  onBack,
  onExit,
}: DebugWorkspaceProps) {
  const [prompt, setPrompt] = useState("");
  const [comparisonOpen, setComparisonOpen] = useState(false);
  const runtimesRef = useRef(new Map<string, DebugRuntime>());
  const sendControllersRef = useRef(new Map<string, AbortController>());
  const sendingRef = useRef(false);
  const messageSequenceRef = useRef(0);
  const [selectedAgent, setSelectedAgent] = useState<CreationFlowAgentSelection>(
    () => initialAgentSelection(agentDraft, agentOverrides),
  );
  const [groupStates, setGroupStates] = useState<Record<DebugGroup, DebugGroupState>>({
    baseline: createDebugGroupState(),
    comparison: createDebugGroupState(),
  });

  useEffect(() => () => {
    for (const controller of sendControllersRef.current.values()) {
      controller.abort();
    }
    sendControllersRef.current.clear();
    for (const runtime of runtimesRef.current.values()) {
      void deleteGeneratedAgentTestRun(runtime.run.runId);
    }
    runtimesRef.current.clear();
  }, []);

  const stateForAgent = (agent: CreationFlowAgentSelection) =>
    debugAgentConfigState(agent, agentModelConfigs[agent.id]);

  const updateGroupAgentState = (
    group: DebugGroup,
    agent: CreationFlowAgentSelection,
    update: (state: DebugAgentConfigState) => DebugAgentConfigState,
  ) => {
    setGroupStates((current) => {
      const state =
        current[group].agentConfigs[agent.id] ?? stateForAgent(agent);
      return {
        ...current,
        [group]: {
          ...current[group],
          agentConfigs: {
            ...current[group].agentConfigs,
            [agent.id]: update(state),
          },
        },
      };
    });
  };

  const runtimeKey = (group: DebugGroup, agentId: string) =>
    `${group}:${agentId}`;

  const cleanupRuntime = async (group: DebugGroup, agentId: string) => {
    const key = runtimeKey(group, agentId);
    sendControllersRef.current.get(key)?.abort();
    sendControllersRef.current.delete(key);
    const runtime = runtimesRef.current.get(key);
    runtimesRef.current.delete(key);
    if (runtime) {
      await deleteGeneratedAgentTestRun(runtime.run.runId).catch(() => {});
    }
  };

  const ensureDebugRuntime = async (
    group: DebugGroup,
    agent: CreationFlowAgentSelection,
    config: AgentDebugConfigValue,
  ) => {
    const key = runtimeKey(group, agent.id);
    const draft = debugDraftForAgent(
      agentDraft,
      agent.id,
      config,
      cloudProvider,
    );
    const snapshot = JSON.stringify({ agentId: agent.id, draft });
    const currentRuntime = runtimesRef.current.get(key);
    if (currentRuntime?.snapshot === snapshot) return currentRuntime;

    if (currentRuntime) await cleanupRuntime(group, agent.id);
    updateGroupAgentState(group, agent, (state) => ({
      ...state,
      phase: "starting",
      runtimeSnapshot: "",
    }));

    let run: GeneratedAgentTestRun | null = null;
    try {
      run = await createGeneratedAgentTestRun(draft);
      const sessionId = await createGeneratedAgentTestSession(
        run.runId,
        "test_user",
      );
      const runtime = { run, sessionId, snapshot };
      runtimesRef.current.set(key, runtime);
      updateGroupAgentState(group, agent, (state) => ({
        ...state,
        phase: "ready",
        runtimeSnapshot: snapshot,
      }));
      return runtime;
    } catch (error) {
      if (run) await deleteGeneratedAgentTestRun(run.runId).catch(() => {});
      throw error;
    }
  };

  const openGroupConfig = (group: DebugGroup) => {
    setGroupStates((current) => ({
      ...current,
      [group]: {
        ...current[group],
        configOpen: true,
        agentConfigs: {
          ...current[group].agentConfigs,
          [selectedAgent.id]: {
            ...(current[group].agentConfigs[selectedAgent.id] ??
              stateForAgent(selectedAgent)),
            draft: {
              ...(current[group].agentConfigs[selectedAgent.id]?.savedConfig ??
                debugConfigFromAgent(
                  selectedAgent,
                  agentModelConfigs[selectedAgent.id],
                )),
              modelConfig: {
                ...(current[group].agentConfigs[selectedAgent.id]?.savedConfig
                  .modelConfig ??
                  debugConfigFromAgent(
                    selectedAgent,
                    agentModelConfigs[selectedAgent.id],
                  ).modelConfig),
              },
            },
          },
        },
      },
    }));
  };

  const closeGroupConfig = (group: DebugGroup) => {
    setGroupStates((current) => ({
      ...current,
      [group]: {
        ...current[group],
        configOpen: false,
        agentConfigs: {
          ...current[group].agentConfigs,
          [selectedAgent.id]: {
            ...(current[group].agentConfigs[selectedAgent.id] ??
              stateForAgent(selectedAgent)),
            draft: {
              ...(current[group].agentConfigs[selectedAgent.id]?.savedConfig ??
                debugConfigFromAgent(
                  selectedAgent,
                  agentModelConfigs[selectedAgent.id],
                )),
              modelConfig: {
                ...(current[group].agentConfigs[selectedAgent.id]?.savedConfig
                  .modelConfig ??
                  debugConfigFromAgent(
                    selectedAgent,
                    agentModelConfigs[selectedAgent.id],
                  ).modelConfig),
              },
            },
          },
        },
      },
    }));
  };

  const updateGroupDraft = (group: DebugGroup, value: AgentDebugConfigValue) => {
    setGroupStates((current) => ({
      ...current,
      [group]: {
        ...current[group],
        agentConfigs: {
          ...current[group].agentConfigs,
          [selectedAgent.id]: {
            ...(current[group].agentConfigs[selectedAgent.id] ??
              stateForAgent(selectedAgent)),
            draft: value,
          },
        },
      },
    }));
  };

  const confirmGroupConfig = (group: DebugGroup) => {
    setGroupStates((current) => ({
      ...current,
      [group]: {
        ...current[group],
        configOpen: false,
        agentConfigs: {
          ...current[group].agentConfigs,
          [selectedAgent.id]: {
            ...(current[group].agentConfigs[selectedAgent.id] ??
              stateForAgent(selectedAgent)),
            savedConfig: {
              ...(current[group].agentConfigs[selectedAgent.id]?.draft ??
                debugConfigFromAgent(
                  selectedAgent,
                  agentModelConfigs[selectedAgent.id],
                )),
              modelConfig: {
                ...(current[group].agentConfigs[selectedAgent.id]?.draft
                  .modelConfig ??
                  debugConfigFromAgent(
                    selectedAgent,
                    agentModelConfigs[selectedAgent.id],
                  ).modelConfig),
              },
            },
          },
        },
      },
    }));
  };

  const handleAgentSelect = (agent: CreationFlowAgentSelection | null) => {
    if (agent) setSelectedAgent(agent);
  };

  const baselineAgentConfig =
    groupStates.baseline.agentConfigs[selectedAgent.id] ??
    stateForAgent(selectedAgent);
  const comparisonAgentConfig =
    groupStates.comparison.agentConfigs[selectedAgent.id] ??
    stateForAgent(selectedAgent);

  const activeGroups: DebugGroup[] = comparisonOpen
    ? ["baseline", "comparison"]
    : ["baseline"];
  const activeAgentStates: Record<DebugGroup, DebugAgentConfigState> = {
    baseline: baselineAgentConfig,
    comparison: comparisonAgentConfig,
  };
  const sending = activeGroups.some((group) =>
    ["starting", "sending"].includes(activeAgentStates[group].phase),
  );

  const sendPrompt = async () => {
    const text = prompt.trim();
    if (!text || sendingRef.current) return;
    sendingRef.current = true;
    setPrompt("");
    const agent = selectedAgent;
    const targets = activeGroups.map((group) => ({
      group,
      config: activeAgentStates[group].savedConfig,
      userMessageId: messageSequenceRef.current++,
      assistantMessageId: messageSequenceRef.current++,
    }));

    for (const target of targets) {
      updateGroupAgentState(target.group, agent, (state) => ({
        ...state,
        phase: "starting",
        messages: [
          ...state.messages,
          {
            id: target.userMessageId,
            role: "user",
            content: text,
          },
          {
            id: target.assistantMessageId,
            role: "assistant",
            content: "",
            blocks: [],
          },
        ],
      }));
    }

    await Promise.all(
      targets.map(async (target) => {
        const key = runtimeKey(target.group, agent.id);
        try {
          const runtime = await ensureDebugRuntime(
            target.group,
            agent,
            target.config,
          );
          const controller = new AbortController();
          sendControllersRef.current.set(key, controller);
          updateGroupAgentState(target.group, agent, (state) => ({
            ...state,
            phase: "sending",
          }));

          let acc = emptyAcc();
          for await (const event of runGeneratedAgentTestSSE({
            runId: runtime.run.runId,
            userId: "test_user",
            sessionId: runtime.sessionId,
            text,
            signal: controller.signal,
          })) {
            const eventError =
              event.error || event.errorMessage || event.error_message;
            if (eventError) throw new Error(String(eventError));
            acc = applyEvent(acc, event);
            const blocks = acc.blocks;
            updateGroupAgentState(target.group, agent, (state) => ({
              ...state,
              messages: state.messages.map((message) =>
                message.id === target.assistantMessageId
                  ? {
                      ...message,
                      content: blocks
                        .filter((block) => block.kind === "text")
                        .map((block) => block.text)
                        .join(""),
                      blocks,
                    }
                  : message,
              ),
            }));
          }
          updateGroupAgentState(target.group, agent, (state) => ({
            ...state,
            phase: "ready",
          }));
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          updateGroupAgentState(target.group, agent, (state) => ({
            ...state,
            phase: runtimesRef.current.has(key) ? "ready" : "error",
            messages: state.messages.map((item) =>
              item.id === target.assistantMessageId
                ? { ...item, error: message }
                : item,
            ),
          }));
        } finally {
          if (sendControllersRef.current.get(key)) {
            sendControllersRef.current.delete(key);
          }
        }
      }),
    );
    sendingRef.current = false;
  };

  const anyConfigOpen =
    groupStates.baseline.configOpen || groupStates.comparison.configOpen;

  return (
    <section className="create-workspace create-workspace--debug" aria-label="智能体调试工作台">
      <CreateNavbar
        mode="debug"
        onBack={onBack}
        onExitDebug={onExit}
        onAddComparison={() => setComparisonOpen(true)}
        primaryLabel="部署"
      />

      <CreationFlowCanvas
        mode="debug"
        centerViewport
        selectedAgentId={selectedAgent.id}
        configPanelOpen={false}
        onAgentSelect={handleAgentSelect}
        agentOverrides={agentOverrides}
        agentDraft={agentDraft}
        debugComparison={comparisonOpen}
      />

      <aside
        className={`debug-workspace__panel${comparisonOpen ? " debug-workspace__panel--comparison" : ""}${anyConfigOpen ? " is-configuring" : ""}`}
        aria-label={comparisonOpen ? "调试对照组" : "调试你的 Agent"}
      >
        {comparisonOpen ? (
          <div className="debug-workspace__comparison-columns">
            <section className="debug-workspace__comparison-column" aria-label="基准组 A">
              <header className="debug-workspace__comparison-header">
                <span className="debug-workspace__comparison-tag">基准组 A</span>
                <button
                  type="button"
                  className="debug-workspace__comparison-settings"
                  aria-label={groupStates.baseline.configOpen ? "关闭基准组 A 配置" : "配置基准组 A"}
                  onClick={() => groupStates.baseline.configOpen
                    ? closeGroupConfig("baseline")
                    : openGroupConfig("baseline")}
                >
                  {groupStates.baseline.configOpen ? <CloseConfigIcon /> : <SettingsIcon />}
                </button>
              </header>
              {groupStates.baseline.configOpen ? (
                <AgentDebugConfigPanel
                  idPrefix="debug-agent-baseline"
                  value={baselineAgentConfig.draft}
                  showChangeBadges={false}
                  onChange={(value) => updateGroupDraft("baseline", value)}
                  onConfirm={() => confirmGroupConfig("baseline")}
                  onCancel={() => closeGroupConfig("baseline")}
                />
              ) : (
                <DebugPanelContent
                  messages={baselineAgentConfig.messages}
                  busy={["starting", "sending"].includes(
                    baselineAgentConfig.phase,
                  )}
                  onQuestionSelect={setPrompt}
                />
              )}
            </section>
            <section className="debug-workspace__comparison-column" aria-label="对照组 B">
              <header className="debug-workspace__comparison-header">
                <span className="debug-workspace__comparison-header-start">
                  <span className="debug-workspace__comparison-tag">对照组 B</span>
                  <span className="debug-workspace__comparison-changes">提示词、模型 2 处改动</span>
                </span>
                <button
                  type="button"
                  className="debug-workspace__comparison-settings"
                  aria-label={groupStates.comparison.configOpen ? "关闭对照组 B 配置" : "配置对照组 B"}
                  onClick={() => groupStates.comparison.configOpen
                    ? closeGroupConfig("comparison")
                    : openGroupConfig("comparison")}
                >
                  {groupStates.comparison.configOpen ? <CloseConfigIcon /> : <SettingsIcon />}
                </button>
              </header>
              {groupStates.comparison.configOpen ? (
                <AgentDebugConfigPanel
                  idPrefix="debug-agent-comparison"
                  value={comparisonAgentConfig.draft}
                  showChangeBadges
                  onChange={(value) => updateGroupDraft("comparison", value)}
                  onConfirm={() => confirmGroupConfig("comparison")}
                  onCancel={() => closeGroupConfig("comparison")}
                />
              ) : (
                <DebugPanelContent
                  messages={comparisonAgentConfig.messages}
                  busy={["starting", "sending"].includes(
                    comparisonAgentConfig.phase,
                  )}
                  onQuestionSelect={setPrompt}
                />
              )}
            </section>
          </div>
        ) : (
          <DebugPanelContent
            messages={baselineAgentConfig.messages}
            busy={["starting", "sending"].includes(
              baselineAgentConfig.phase,
            )}
            onQuestionSelect={setPrompt}
          />
        )}

        {!anyConfigOpen && (
          <DebugComposer
            prompt={prompt}
            disabled={sending}
            onPromptChange={setPrompt}
            onSend={() => void sendPrompt()}
          />
        )}
      </aside>
    </section>
  );
}
