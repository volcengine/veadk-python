import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import collapseIcon from "./assets/create-workspace/collapse.svg";
import messageIcon from "./assets/create-workspace/message.svg";
import sendIcon from "./assets/create-workspace/send.svg";
import { chatWithGeneratedAgent } from "../adk/client";
import type { CloudProvider } from "../adk/cloudProvider";
import { AgentConfigPanel } from "../ui/AgentConfigPanel";
import {
  createDefaultAgentStorageCapabilities,
  type AgentStorageCapabilities,
} from "../ui/AgentStorageConfigDialog";
import {
  activeAgentModelName,
  type AgentModelConfigValue,
} from "../ui/AgentModelConfigFields";
import {
  CreationFlowCanvas,
  type CreationFlowAgentSelection,
} from "./CreationFlowCanvas";
import { CreateNavbar } from "./CreateNavbar";
import { DebugWorkspace } from "./DebugWorkspace";
import { DeploymentWorkspace } from "./DeploymentWorkspace";
import {
  normalizeDraft,
  sanitizeGeneratedDraftCapabilities,
} from "./normalizeDraft";
import {
  agentDraftAtNodeId,
  agentDraftForConversation,
  updateAgentDraftAtNodeId,
} from "./agentDraftWorkflow";
import { emptyDraft, type AgentDraft } from "./types";
import "./CreateWorkspace.css";

interface CreateWorkspaceProps {
  cloudProvider: CloudProvider;
  initialPrompt?: string;
  onBack: () => void;
}

interface CreateChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  status?: "processing" | "complete";
  startedAt?: number;
  elapsedSeconds?: number;
}

interface AgentConfigDraft {
  agentName: string;
  agentDescription: string;
  systemPrompt: string;
  modelConfig: AgentModelConfigValue;
  selectedTools: string[];
  selectedMcps: string[];
  selectedSkills: string[];
  storageCapabilities: AgentStorageCapabilities;
}

function modelConfigFromSelection(
  agent: CreationFlowAgentSelection,
): AgentModelConfigValue {
  return {
    category: agent.modelSource === "custom" ? "custom" : "volcano-ark",
    customProvider: agent.modelProvider,
    customModelName: agent.modelSource === "custom" ? agent.model : "",
    customBaseUrl: agent.modelApiBase,
    customApiKey: "",
    volcanoApiKey: "",
    volcanoModelName: agent.modelSource === "custom" ? "" : agent.model,
  };
}

function storageCapabilitiesFromDraft(
  agent: AgentDraft | null,
): AgentStorageCapabilities {
  if (!agent) return createDefaultAgentStorageCapabilities();
  return {
    shortTermMemory: {
      enabled: agent.memory.shortTerm,
      mode: agent.shortTermBackend === "local" ? "local" : "enterprise",
      database: "",
    },
    longTermMemory: {
      enabled: agent.memory.longTerm,
      mode:
        agent.longTermBackend === "local"
          ? "local"
          : agent.longTermBackend === "viking"
            ? "managed"
            : "enterprise",
      database: agent.longTermMemoryIndex ?? "",
    },
    knowledgeBase: {
      enabled: agent.knowledgebase,
      mode:
        agent.knowledgebaseBackend === "viking" ? "managed" : "enterprise",
      database: agent.knowledgebaseIndex ?? "",
    },
  };
}

function configFromAgentSelection(
  selection: CreationFlowAgentSelection,
  draft: AgentDraft | null,
): AgentConfigDraft {
  return {
    agentName: selection.title,
    agentDescription: selection.description,
    systemPrompt: selection.systemPrompt,
    modelConfig: modelConfigFromSelection(selection),
    selectedTools: [...(draft?.builtinTools ?? [])],
    selectedMcps: Array.from(
      new Set((draft?.mcpTools ?? []).map((tool) => tool.name).filter(Boolean)),
    ),
    selectedSkills: Array.from(
      new Set([
        ...(draft?.skills ?? []),
        ...(draft?.selectedSkills ?? []).map(
          (skill) => skill.slug || skill.name || skill.folder,
        ),
      ]),
    ).filter(Boolean),
    storageCapabilities: storageCapabilitiesFromDraft(draft),
  };
}

function updateDraftFromConfigField(
  agent: AgentDraft,
  field: Exclude<keyof AgentConfigDraft, "modelConfig">,
  value: AgentConfigDraft[Exclude<keyof AgentConfigDraft, "modelConfig">],
): AgentDraft {
  if (field === "agentName" && typeof value === "string") {
    return { ...agent, name: value };
  }
  if (field === "agentDescription" && typeof value === "string") {
    return { ...agent, description: value };
  }
  if (field === "systemPrompt" && typeof value === "string") {
    return { ...agent, instruction: value };
  }
  if (field === "selectedTools" && Array.isArray(value)) {
    return { ...agent, builtinTools: Array.from(new Set(value)) };
  }
  if (field === "selectedSkills" && Array.isArray(value)) {
    const selected = new Set(value);
    const selectedSkills = (agent.selectedSkills ?? []).filter((skill) =>
      selected.has(skill.slug || skill.name || skill.folder),
    );
    const structuredSkillNames = new Set(
      selectedSkills.map((skill) => skill.slug || skill.name || skill.folder),
    );
    return {
      ...agent,
      skills: Array.from(selected).filter(
        (skill) => !structuredSkillNames.has(skill),
      ),
      selectedSkills,
    };
  }
  if (field === "selectedMcps" && Array.isArray(value)) {
    const selected = new Set(value);
    return {
      ...agent,
      mcpTools: (agent.mcpTools ?? []).filter((tool) =>
        selected.has(tool.name),
      ),
    };
  }
  if (field === "storageCapabilities" && !Array.isArray(value)) {
    const storage = value as AgentStorageCapabilities;
    return {
      ...agent,
      memory: {
        shortTerm: storage.shortTermMemory.enabled,
        longTerm: storage.longTermMemory.enabled,
      },
      knowledgebase: storage.knowledgeBase.enabled,
      longTermMemoryIndex: storage.longTermMemory.database,
      knowledgebaseIndex: storage.knowledgeBase.database,
    };
  }
  return agent;
}

function updateDraftModelConfig(
  agent: AgentDraft,
  value: AgentModelConfigValue,
): AgentDraft {
  const modelName = activeAgentModelName(value);
  const isCustom = value.category === "custom";
  return {
    ...agent,
    model: modelName,
    modelName,
    modelSource: isCustom ? "custom" : "ark",
    modelProvider: isCustom ? value.customProvider : "",
    modelApiBase: isCustom ? value.customBaseUrl : "",
  };
}

function formatDuration(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes} 分 ${seconds} 秒`;
}

export function CreateWorkspace({
  cloudProvider,
  initialPrompt = "",
  onBack,
}: CreateWorkspaceProps) {
  const [workspaceMode, setWorkspaceMode] = useState<
    "create" | "debug" | "deploy"
  >("create");
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<CreateChatMessage[]>([]);
  const [clock, setClock] = useState(() => Date.now());
  const [agentDraft, setAgentDraft] = useState<AgentDraft | null>(null);
  const [selectedAgent, setSelectedAgent] =
    useState<CreationFlowAgentSelection | null>(null);
  const [agentConfigs, setAgentConfigs] = useState<
    Record<string, AgentConfigDraft>
  >({});
  const messageSequenceRef = useRef(0);
  const messageListRef = useRef<HTMLDivElement>(null);
  const compositionRef = useRef(false);
  const requestAbortRef = useRef<AbortController | null>(null);
  const requestInFlightRef = useRef(false);
  const initialPromptRef = useRef(initialPrompt.trim());
  const conversationSessionIdRef = useRef(
    `studio-create-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`,
  );

  const isProcessing = messages.some(
    (message) =>
      message.role === "assistant" && message.status === "processing",
  );
  const selectedAgentConfig = selectedAgent
    ? (agentConfigs[selectedAgent.id] ?? {
        agentName: selectedAgent.title,
        agentDescription: selectedAgent.description,
        systemPrompt: selectedAgent.systemPrompt,
        modelConfig: modelConfigFromSelection(selectedAgent),
        selectedTools: [],
        selectedMcps: [],
        selectedSkills: [],
        storageCapabilities: createDefaultAgentStorageCapabilities(),
      })
    : null;
  const agentOverrides = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(agentConfigs).map(([id, config]) => [
          id,
          {
            title: config.agentName,
            description: config.agentDescription,
            systemPrompt: config.systemPrompt,
            model: activeAgentModelName(config.modelConfig),
          },
        ]),
      ),
    [agentConfigs],
  );
  const agentModelConfigs = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(agentConfigs).map(([id, config]) => [
          id,
          config.modelConfig,
        ]),
      ),
    [agentConfigs],
  );

  useEffect(() => {
    if (!isProcessing) return;

    setClock(Date.now());
    const intervalId = window.setInterval(() => setClock(Date.now()), 1_000);
    return () => window.clearInterval(intervalId);
  }, [isProcessing]);

  useEffect(() => () => requestAbortRef.current?.abort(), []);

  useEffect(() => {
    const messageList = messageListRef.current;
    if (!messageList) return;
    messageList.scrollTop = messageList.scrollHeight;
  }, [messages]);

  async function sendMessage(content: string) {
    const trimmedContent = content.trim();
    if (!trimmedContent || requestInFlightRef.current) return;

    const userMessageId = messageSequenceRef.current;
    messageSequenceRef.current += 2;
    const startedAt = Date.now();
    const controller = new AbortController();
    requestAbortRef.current?.abort();
    requestAbortRef.current = controller;
    requestInFlightRef.current = true;
    setMessages((currentMessages) => [
      ...currentMessages,
      { id: userMessageId, role: "user", content: trimmedContent },
      {
        id: userMessageId + 1,
        role: "assistant",
        content: "",
        status: "processing",
        startedAt,
      },
    ]);
    setPrompt("");

    try {
      const result = await chatWithGeneratedAgent(
        conversationSessionIdRef.current,
        trimmedContent,
        agentDraft ? agentDraftForConversation(agentDraft) : undefined,
        controller.signal,
      );
      if (controller.signal.aborted) return;

      if (result.draft) {
        const nextDraft = sanitizeGeneratedDraftCapabilities(
          normalizeDraft({ ...result.draft, cloudProvider }),
          cloudProvider,
        );
        setAgentDraft(nextDraft);
        setAgentConfigs({});
        setSelectedAgent(null);
      }

      const elapsedSeconds = Math.max(
        1,
        Math.floor((Date.now() - startedAt) / 1_000),
      );
      setMessages((currentMessages) =>
        currentMessages.map((message) =>
          message.id === userMessageId + 1
            ? {
                ...message,
                content: result.reply,
                status: "complete",
                elapsedSeconds,
              }
            : message,
        ),
      );
    } catch (error) {
      if (controller.signal.aborted) return;
      const elapsedSeconds = Math.max(
        1,
        Math.floor((Date.now() - startedAt) / 1_000),
      );
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      setMessages((currentMessages) =>
        currentMessages.map((message) =>
          message.id === userMessageId + 1
            ? {
                ...message,
                content: errorMessage,
                status: "complete",
                elapsedSeconds,
              }
            : message,
        ),
      );
    } finally {
      if (requestAbortRef.current === controller) {
        requestAbortRef.current = null;
        requestInFlightRef.current = false;
      }
    }
  }

  function handleSend() {
    void sendMessage(prompt);
  }

  useEffect(() => {
    const content = initialPromptRef.current;
    if (!content) return;
    initialPromptRef.current = "";
    void sendMessage(content);
  }, []);

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    const isSafariComposition = event.nativeEvent.keyCode === 229;
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !compositionRef.current &&
      !isSafariComposition
    ) {
      event.preventDefault();
      handleSend();
    }
  }

  function handleChatToggle() {
    if (chatCollapsed) {
      setSelectedAgent(null);
      setChatCollapsed(false);
      return;
    }
    setChatCollapsed(true);
  }

  function handleAgentSelect(agent: CreationFlowAgentSelection | null) {
    setSelectedAgent(agent);
    if (agent) setChatCollapsed(true);
    if (!agent) return;

    setAgentConfigs((currentConfigs) => {
      if (currentConfigs[agent.id]) return currentConfigs;
      const selectedDraft = agentDraft
        ? agentDraftAtNodeId(agentDraft, agent.id)
        : null;
      return {
        ...currentConfigs,
        [agent.id]: configFromAgentSelection(agent, selectedDraft),
      };
    });
  }

  function updateSelectedAgentModelConfig(value: AgentModelConfigValue) {
    if (!selectedAgent || !selectedAgentConfig) return;
    const selectedAgentId = selectedAgent.id;
    setAgentConfigs((currentConfigs) => ({
      ...currentConfigs,
      [selectedAgentId]: {
        ...(currentConfigs[selectedAgentId] ?? selectedAgentConfig),
        modelConfig: value,
      },
    }));
    setAgentDraft((currentDraft) =>
      currentDraft
        ? updateAgentDraftAtNodeId(currentDraft, selectedAgentId, (agent) =>
            updateDraftModelConfig(agent, value),
          )
        : currentDraft,
    );
    setSelectedAgent((currentAgent) =>
      currentAgent?.id === selectedAgentId
        ? { ...currentAgent, model: activeAgentModelName(value) }
        : currentAgent,
    );
  }

  function updateSelectedAgentConfig<
    Field extends Exclude<keyof AgentConfigDraft, "modelConfig">,
  >(field: Field, value: AgentConfigDraft[Field]) {
    if (!selectedAgent || !selectedAgentConfig) return;

    const selectedAgentId = selectedAgent.id;
    setAgentConfigs((currentConfigs) => ({
      ...currentConfigs,
      [selectedAgentId]: {
        ...(currentConfigs[selectedAgentId] ?? selectedAgentConfig),
        [field]: value,
      },
    }));
    setAgentDraft((currentDraft) =>
      currentDraft
        ? updateAgentDraftAtNodeId(currentDraft, selectedAgentId, (agent) =>
            updateDraftFromConfigField(agent, field, value),
          )
        : currentDraft,
    );

    if (field === "agentName" && typeof value === "string") {
      setSelectedAgent((currentAgent) =>
        currentAgent?.id === selectedAgentId
          ? { ...currentAgent, title: value }
          : currentAgent,
      );
    } else if (field === "agentDescription" && typeof value === "string") {
      setSelectedAgent((currentAgent) =>
        currentAgent?.id === selectedAgentId
          ? { ...currentAgent, description: value }
          : currentAgent,
      );
    } else if (field === "systemPrompt" && typeof value === "string") {
      setSelectedAgent((currentAgent) =>
        currentAgent?.id === selectedAgentId
          ? { ...currentAgent, systemPrompt: value }
          : currentAgent,
      );
    }
  }

  function handleSubAgentAdd(parentAgentId: string) {
    setAgentDraft((currentDraft) =>
      currentDraft
        ? updateAgentDraftAtNodeId(currentDraft, parentAgentId, (parentAgent) => {
            const subAgentNumber = parentAgent.subAgents.length + 1;
            return {
              ...parentAgent,
              subAgents: [
                ...parentAgent.subAgents,
                {
                  ...emptyDraft(cloudProvider),
                  name: `SubAgent${subAgentNumber}`,
                },
              ],
            };
          })
        : currentDraft,
    );
  }

  if (workspaceMode === "debug") {
    return (
      <DebugWorkspace
        agentDraft={agentDraft}
        agentOverrides={agentOverrides}
        agentModelConfigs={agentModelConfigs}
        cloudProvider={cloudProvider}
        onBack={onBack}
        onExit={() => setWorkspaceMode("create")}
      />
    );
  }

  if (workspaceMode === "deploy") {
    return (
      <DeploymentWorkspace
        agentDraft={agentDraft}
        onBack={() => setWorkspaceMode("create")}
      />
    );
  }

  return (
    <section
      className={`create-workspace${chatCollapsed ? " create-workspace--chat-collapsed" : ""}`}
      aria-label="创建智能体工作台"
    >
      <CreateNavbar
        onBack={onBack}
        onDebug={() => setWorkspaceMode("debug")}
        onDeploy={() => setWorkspaceMode("deploy")}
        primaryLabel="部署"
      />

      <button
        type="button"
        className="create-workspace__chat-toggle"
        aria-label={chatCollapsed ? "展开对话面板" : "收起对话面板"}
        aria-controls="create-workspace-chat"
        aria-expanded={!chatCollapsed}
        onClick={handleChatToggle}
      >
        <span className="create-workspace__chat-mark">
          <img src={messageIcon} alt="" />
        </span>
      </button>

      <aside
        id="create-workspace-chat"
        className="create-workspace__chat"
        aria-label="创建对话"
        aria-hidden={chatCollapsed}
      >
        <div className="create-workspace__chat-header">
          <span aria-hidden="true" />
          <button
            type="button"
            className="create-workspace__collapse"
            aria-label="收起对话面板"
            onClick={() => setChatCollapsed(true)}
          >
            <img src={collapseIcon} alt="" />
          </button>
        </div>

        <div
          ref={messageListRef}
          className="create-workspace__chat-content"
          aria-live="polite"
        >
          {messages.map((message) =>
            message.role === "user" ? (
              <div
                key={message.id}
                className="create-workspace__message create-workspace__message--user"
                aria-label="你的消息"
              >
                {message.content}
              </div>
            ) : (
              <article
                key={message.id}
                className="create-workspace__message create-workspace__message--assistant"
                aria-label="模型回复"
              >
                <div className="create-workspace__assistant-status">
                  {message.status === "processing"
                    ? `已处理 ${formatDuration(
                        Math.max(
                          0,
                          Math.floor(
                            (clock - (message.startedAt ?? clock)) / 1_000,
                          ),
                        ),
                      )}`
                    : `耗时 ${formatDuration(message.elapsedSeconds ?? 0)}`}
                </div>
                {message.status !== "processing" && (
                  <>
                    <span className="create-workspace__assistant-divider" />
                    <p className="create-workspace__assistant-body">
                      {message.content}
                    </p>
                  </>
                )}
              </article>
            ),
          )}
        </div>

        <div className="create-workspace__composer-wrap">
          <form
            className="create-workspace__composer"
            aria-busy={isProcessing}
            onSubmit={(event) => {
              event.preventDefault();
              handleSend();
            }}
          >
            <textarea
              className="create-workspace__composer-input"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              onCompositionStart={() => {
                compositionRef.current = true;
              }}
              onCompositionEnd={() => {
                compositionRef.current = false;
              }}
              placeholder="描述你想创建的智能体"
              aria-label="描述你想创建的智能体"
            />
            <button
              type="submit"
              className="create-workspace__send"
              disabled={!prompt.trim() || isProcessing}
              aria-label="发送"
            >
              <img src={sendIcon} alt="" />
            </button>
          </form>
        </div>
      </aside>

      {selectedAgent && selectedAgentConfig && (
        <AgentConfigPanel
          key={selectedAgent.id}
          agentName={selectedAgentConfig.agentName}
          agentDescription={selectedAgentConfig.agentDescription}
          systemPrompt={selectedAgentConfig.systemPrompt}
          modelConfig={selectedAgentConfig.modelConfig}
          selectedTools={selectedAgentConfig.selectedTools}
          selectedMcps={selectedAgentConfig.selectedMcps}
          selectedSkills={selectedAgentConfig.selectedSkills}
          storageCapabilities={selectedAgentConfig.storageCapabilities}
          tone={selectedAgent.tone}
          onAgentNameChange={(value) =>
            updateSelectedAgentConfig("agentName", value)
          }
          onAgentDescriptionChange={(value) =>
            updateSelectedAgentConfig("agentDescription", value)
          }
          onSystemPromptChange={(value) =>
            updateSelectedAgentConfig("systemPrompt", value)
          }
          onModelConfigChange={updateSelectedAgentModelConfig}
          onSelectedToolsChange={(value) =>
            updateSelectedAgentConfig("selectedTools", value)
          }
          onSelectedMcpsChange={(value) =>
            updateSelectedAgentConfig("selectedMcps", value)
          }
          onSelectedSkillsChange={(value) =>
            updateSelectedAgentConfig("selectedSkills", value)
          }
          onStorageCapabilitiesChange={(value) =>
            updateSelectedAgentConfig("storageCapabilities", value)
          }
          onClose={() => setSelectedAgent(null)}
        />
      )}

      <CreationFlowCanvas
        selectedAgentId={selectedAgent?.id ?? null}
        configPanelOpen={selectedAgent !== null}
        onAgentSelect={handleAgentSelect}
        agentOverrides={agentOverrides}
        agentDraft={agentDraft}
        onSubAgentAdd={handleSubAgentAdd}
      />
    </section>
  );
}
