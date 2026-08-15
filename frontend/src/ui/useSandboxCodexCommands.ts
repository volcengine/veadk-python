import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  sandboxClient,
  type AgentKitSandboxClient,
  type SandboxModel,
  type SandboxSession,
  type SandboxSkill,
  type SandboxThreadSnapshot,
  type SandboxThreadSummary,
} from "../adk/sandbox";
import type { TurnActivityDetail } from "../blocks";
import {
  SANDBOX_SLASH_COMMANDS,
  parseSandboxSlash,
  sandboxHelpDetails,
  sandboxModelDetails,
  sandboxStatusDetails,
} from "./sandboxCommands";

interface UseSandboxCodexCommandsOptions {
  client?: AgentKitSandboxClient;
  allowSkillSelection?: boolean;
  allowThreadManagement?: boolean;
  session: SandboxSession | null;
  conversationBusy: boolean;
  onInputChange: (value: string) => void;
  onSessionPatch: (patch: Partial<SandboxSession>) => void;
  onSnapshot: (snapshot: SandboxThreadSnapshot) => void;
  onActivity: (title: string, details?: TurnActivityDetail[]) => void;
  onError: (message: string) => void;
}

export function useSandboxCodexCommands({
  client = sandboxClient,
  allowSkillSelection = true,
  allowThreadManagement = true,
  session,
  conversationBusy,
  onInputChange,
  onSessionPatch,
  onSnapshot,
  onActivity,
  onError,
}: UseSandboxCodexCommandsOptions) {
  const sessionIdRef = useRef(session?.id ?? "");
  const threadsRequestRef = useRef(0);
  sessionIdRef.current = session?.id ?? "";
  const [commandBusy, setCommandBusy] = useState(false);
  const [models, setModels] = useState<SandboxModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const [skills, setSkills] = useState<SandboxSkill[]>([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsLoaded, setSkillsLoaded] = useState(false);
  const [selectedSkills, setSelectedSkills] = useState<SandboxSkill[]>([]);
  const [threadsOpen, setThreadsOpen] = useState(false);
  const [threads, setThreads] = useState<SandboxThreadSummary[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);
  const [threadsError, setThreadsError] = useState("");
  const [threadsNextCursor, setThreadsNextCursor] = useState("");
  const [threadActionId, setThreadActionId] = useState("");

  useEffect(() => {
    threadsRequestRef.current += 1;
    setCommandBusy(false);
    setModels([]);
    setModelsLoading(false);
    setModelsLoaded(false);
    setSkills([]);
    setSkillsLoading(false);
    setSkillsLoaded(false);
    setSelectedSkills([]);
    setThreadsOpen(false);
    setThreads([]);
    setThreadsLoading(false);
    setThreadsError("");
    setThreadsNextCursor("");
    setThreadActionId("");
  }, [session?.id]);

  const loadModels = useCallback(async (): Promise<SandboxModel[]> => {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId) return [];
    setModelsLoading(true);
    try {
      const available = await client.listModels(activeSessionId);
      if (sessionIdRef.current === activeSessionId) {
        setModels(available);
        setModelsLoaded(true);
      }
      return available;
    } catch (error) {
      if (sessionIdRef.current === activeSessionId) {
        setModelsLoaded(true);
        onError(error instanceof Error ? error.message : String(error));
      }
      return [];
    } finally {
      if (sessionIdRef.current === activeSessionId) setModelsLoading(false);
    }
  }, [client, onError]);

  const loadSkills = useCallback(async (): Promise<SandboxSkill[]> => {
    if (!allowSkillSelection) return [];
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId) return [];
    setSkillsLoading(true);
    try {
      const available = await client.listSkills(activeSessionId);
      if (sessionIdRef.current === activeSessionId) {
        setSkills(available);
        setSkillsLoaded(true);
      }
      return available;
    } catch (error) {
      if (sessionIdRef.current === activeSessionId) {
        setSkillsLoaded(true);
        onError(error instanceof Error ? error.message : String(error));
      }
      return [];
    } finally {
      if (sessionIdRef.current === activeSessionId) setSkillsLoading(false);
    }
  }, [allowSkillSelection, client, onError]);

  const loadThreadsPage = useCallback(async (
    cursor = "",
    append = false,
  ) => {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId) return;
    const requestId = ++threadsRequestRef.current;
    setThreadsLoading(true);
    setThreadsError("");
    try {
      const page = await client.listThreads(
        activeSessionId,
        cursor ? { cursor } : {},
      );
      if (
        sessionIdRef.current === activeSessionId &&
        threadsRequestRef.current === requestId
      ) {
        setThreads((current) => {
          if (!append) return page.threads;
          const merged = new Map(current.map((thread) => [thread.id, thread]));
          for (const thread of page.threads) merged.set(thread.id, thread);
          return [...merged.values()];
        });
        setThreadsNextCursor(page.nextCursor ?? "");
      }
    } catch (error) {
      if (
        sessionIdRef.current === activeSessionId &&
        threadsRequestRef.current === requestId
      ) {
        setThreadsError(error instanceof Error ? error.message : String(error));
      }
    } finally {
      if (
        sessionIdRef.current === activeSessionId &&
        threadsRequestRef.current === requestId
      ) {
        setThreadsLoading(false);
      }
    }
  }, [client]);

  const refreshThreads = useCallback(
    () => loadThreadsPage("", false),
    [loadThreadsPage],
  );

  const loadMoreThreads = useCallback(async () => {
    if (!threadsNextCursor || threadsLoading) return;
    await loadThreadsPage(threadsNextCursor, true);
  }, [loadThreadsPage, threadsLoading, threadsNextCursor]);

  const openThreads = useCallback(async () => {
    setThreadsOpen(true);
    await refreshThreads();
  }, [refreshThreads]);

  useEffect(() => {
    if (!allowThreadManagement || !session?.id) return;
    void refreshThreads();
  }, [allowThreadManagement, refreshThreads, session?.id]);

  function applySnapshot(snapshot: SandboxThreadSnapshot) {
    onSnapshot(snapshot);
    setThreads((current) => [
      snapshot.thread,
      ...current.filter((thread) => thread.id !== snapshot.thread.id),
    ]);
    setSelectedSkills([]);
    setSkills([]);
    setSkillsLoaded(false);
    setThreadsOpen(false);
  }

  async function requestNewThread(activeSessionId: string) {
    const snapshot = await client.newThread(activeSessionId);
    if (sessionIdRef.current !== activeSessionId) return;
    applySnapshot(snapshot);
    onActivity("已新建 Codex 对话", [
      { label: "Thread", value: snapshot.threadId, code: true },
    ]);
  }

  async function newThread() {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId || commandBusy || conversationBusy) return;
    setCommandBusy(true);
    setThreadsError("");
    onError("");
    try {
      await requestNewThread(activeSessionId);
    } catch (error) {
      if (sessionIdRef.current === activeSessionId) {
        const message = error instanceof Error ? error.message : String(error);
        setThreadsError(message);
        onError(message);
      }
    } finally {
      if (sessionIdRef.current === activeSessionId) setCommandBusy(false);
    }
  }

  async function resumeThread(threadId: string) {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId || commandBusy || conversationBusy) return;
    if (threadId === session?.threadId) {
      setThreadsOpen(false);
      return;
    }
    setCommandBusy(true);
    onError("");
    try {
      const snapshot = await client.resumeThread(
        activeSessionId,
        threadId,
      );
      if (sessionIdRef.current !== activeSessionId) return;
      applySnapshot(snapshot);
      onActivity("已恢复 Codex 对话", [
        { label: "Thread", value: snapshot.threadId, code: true },
      ]);
    } catch (error) {
      if (sessionIdRef.current === activeSessionId) {
        onError(error instanceof Error ? error.message : String(error));
      }
    } finally {
      if (sessionIdRef.current === activeSessionId) setCommandBusy(false);
    }
  }

  async function deleteThread(threadId: string): Promise<boolean> {
    const activeSessionId = sessionIdRef.current;
    if (!activeSessionId || commandBusy || conversationBusy) return false;
    threadsRequestRef.current += 1;
    setThreadsLoading(false);
    setCommandBusy(true);
    setThreadActionId(threadId);
    setThreadsError("");
    onError("");
    try {
      const result = await client.deleteThread(activeSessionId, threadId);
      if (sessionIdRef.current !== activeSessionId) return false;
      if (result.snapshot) applySnapshot(result.snapshot);
      setThreads((current) => current.filter((thread) => thread.id !== threadId));
      onActivity("已删除 Codex 历史会话", [
        { label: "Thread", value: threadId, code: true },
      ]);
      return true;
    } catch (error) {
      if (sessionIdRef.current === activeSessionId) {
        const message = error instanceof Error ? error.message : String(error);
        setThreadsError(message);
        onError(message);
      }
      return false;
    } finally {
      if (sessionIdRef.current === activeSessionId) {
        setCommandBusy(false);
        setThreadActionId("");
      }
    }
  }

  async function executeSlash(value: string): Promise<boolean> {
    const activeSession = session;
    const content = value.trim();
    if (!content.startsWith("/")) return false;
    if (!activeSession || conversationBusy || commandBusy) return true;

    const invocation = parseSandboxSlash(content);
    const command = invocation &&
      SANDBOX_SLASH_COMMANDS.find((candidate) =>
        candidate.name === invocation.name
      );
    if (!invocation || !command) {
      onError(
        `未知快捷命令：${content.split(/\s/, 1)[0]}。输入 /help 查看可用命令。`,
      );
      return true;
    }
    onError("");
    setSelectedSkills([]);

    if (command.name === "model" && !invocation.argument) {
      onInputChange("/model ");
      if (!modelsLoaded) await loadModels();
      return true;
    }
    if (command.name === "skill" || command.name === "skills") {
      if (!allowSkillSelection) {
        onError("智能开发模式会自动使用开发能力，无需手动选择 Skill。");
        return true;
      }
      onInputChange("$");
      if (!skillsLoaded) {
        const available = await loadSkills();
        if (available.length === 0) onInputChange("");
      }
      return true;
    }
    if (command.name === "resume" && !invocation.argument) {
      onInputChange("");
      await openThreads();
      return true;
    }

    onInputChange("");
    setCommandBusy(true);
    try {
      if (command.name === "model") {
        const model = await client.setModel(
          activeSession.id,
          invocation.argument,
        );
        if (sessionIdRef.current !== activeSession.id) return true;
        onSessionPatch({ model });
        onActivity("已切换 Codex 模型", [
          { label: "模型", value: model, code: true },
        ]);
      } else if (command.name === "models") {
        const available = modelsLoaded ? models : await loadModels();
        if (sessionIdRef.current !== activeSession.id) return true;
        onActivity(
          available.length > 0 ? "Codex 可用模型" : "当前没有可用模型",
          sandboxModelDetails(available, activeSession.model),
        );
      } else if (command.name === "new" || command.name === "clear") {
        await requestNewThread(activeSession.id);
      } else if (command.name === "resume") {
        const snapshot = await client.resumeThread(
          activeSession.id,
          invocation.argument,
        );
        if (sessionIdRef.current !== activeSession.id) return true;
        applySnapshot(snapshot);
        onActivity("已恢复 Codex 对话", [
          { label: "Thread", value: snapshot.threadId, code: true },
        ]);
      } else if (command.name === "fork") {
        const snapshot = await client.forkThread(activeSession.id);
        if (sessionIdRef.current !== activeSession.id) return true;
        applySnapshot(snapshot);
        onActivity("已分叉 Codex 对话", [
          { label: "Thread", value: snapshot.threadId, code: true },
        ]);
      } else if (command.name === "compact") {
        await client.compactThread(activeSession.id);
        if (sessionIdRef.current !== activeSession.id) return true;
        onActivity("已开始压缩当前 Codex 对话", [
          { label: "Thread", value: activeSession.threadId, code: true },
        ]);
      } else if (command.name === "archive") {
        const archivedThreadId = activeSession.threadId;
        const result = await client.archiveThread(
          activeSession.id,
          archivedThreadId,
        );
        if (sessionIdRef.current !== activeSession.id) return true;
        if (result.snapshot) applySnapshot(result.snapshot);
        setThreads((current) =>
          current.filter((thread) => thread.id !== archivedThreadId)
        );
        onActivity("已归档 Codex 对话", [
          { label: "Thread", value: archivedThreadId, code: true },
        ]);
      } else if (command.name === "status") {
        const status = await client.getStatus(activeSession.id);
        if (sessionIdRef.current !== activeSession.id) return true;
        onSessionPatch(status);
        onActivity("Codex 当前状态", sandboxStatusDetails(status));
      } else if (command.name === "help") {
        onActivity(
          "Sandbox 支持的 Codex 快捷命令",
          sandboxHelpDetails(),
        );
      }
    } catch (error) {
      if (sessionIdRef.current === activeSession.id) {
        onInputChange(content);
        onError(error instanceof Error ? error.message : String(error));
      }
    } finally {
      if (sessionIdRef.current === activeSession.id) setCommandBusy(false);
    }
    return true;
  }

  function invalidateSkills() {
    setSkills([]);
    setSkillsLoaded(false);
    setSelectedSkills([]);
  }

  return {
    commandBusy,
    models,
    modelsLoading,
    modelsLoaded,
    loadModels,
    skills,
    skillsLoading,
    skillsLoaded,
    loadSkills,
    selectedSkills,
    setSelectedSkills,
    invalidateSkills,
    threadsOpen,
    threads,
    threadsLoading,
    threadsError,
    threadsHasMore: Boolean(threadsNextCursor),
    threadActionId,
    openThreads,
    refreshThreads,
    loadMoreThreads,
    closeThreads: () => {
      if (commandBusy) return;
      setThreadsOpen(false);
      setThreadsError("");
    },
    newThread,
    resumeThread,
    deleteThread,
    executeSlash,
  };
}
