import { useCallback, useEffect, useRef, useState } from "react";
import {
  createSkillWorkbenchTask,
  deleteSkillWorkbenchTask,
  getSkillWorkbenchArtifact,
  getSkillWorkbenchTask,
  listSkillWorkbenchTasks,
  reserveSkillWorkbenchTask,
  SkillWorkbenchApiError,
  stopSkillWorkbenchTask,
} from "./api";
import type {
  SkillCenterOptimizationSource,
  SkillWorkbenchArtifact,
  SkillWorkbenchOperation,
  SkillWorkbenchProvisioningTask,
  SkillWorkbenchTask,
  SkillWorkbenchTaskListItem,
  SkillWorkbenchTaskSummary,
} from "./types";

const LIST_POLL_INTERVAL_MS = 10_000;
const DETAIL_POLL_INTERVAL_MS = 2_000;
const MAX_POLL_INTERVAL_MS = 16_000;
const SYNC_ERROR_REVEAL_THRESHOLD = 3;
const ARTIFACT_RETRY_INTERVAL_MS = 900;
const ARTIFACT_RETRY_LIMIT = 4;
const PROVISIONING_TTL_SECONDS = 10 * 60;
const TERMINAL_STATES = new Set(["ready", "failed", "cancelled", "expired", "published"]);
const JOB_ID_PATTERN = /^sw-[0-9a-f]{12}-[0-9a-f]{24}$/;

interface ProvisioningReference {
  jobId: string;
  reservedAt: number;
  cancelRequested?: true;
}

function isRetryableSyncFailure(cause: unknown): boolean {
  if (cause instanceof SkillWorkbenchApiError) {
    if (cause.retryable) return true;
    return cause.code === "SKILL_WORKBENCH_ERROR" &&
      [408, 429, 502, 503, 504].includes(cause.status);
  }
  if (cause instanceof TypeError) return true;
  return typeof DOMException !== "undefined" &&
    cause instanceof DOMException &&
    ["NetworkError", "TimeoutError"].includes(cause.name);
}

function pollDelay(baseDelay: number, failures: number): number {
  return Math.min(
    baseDelay * 2 ** Math.min(failures, 3),
    MAX_POLL_INTERVAL_MS,
  );
}

export interface StartSkillWorkbenchTaskArgs {
  operation: SkillWorkbenchOperation;
  intent: string;
  source?: SkillCenterOptimizationSource;
  file?: File;
}

function storageKey(identityKey: string): string {
  return `veadk.skill-workbench.provisioning.v1:${identityKey}`;
}

export function loadProvisioningReferences(
  storage: Storage,
  identityKey: string,
  nowSeconds = Math.floor(Date.now() / 1_000),
): ProvisioningReference[] {
  try {
    const value = JSON.parse(storage.getItem(storageKey(identityKey)) || "[]");
    if (!Array.isArray(value)) return [];
    return value.flatMap((item) => {
      if (!item || typeof item !== "object" || Array.isArray(item)) return [];
      const record = item as Record<string, unknown>;
      const cancelRequested = record.cancelRequested === true;
      if (
        typeof record.jobId !== "string" ||
        !JOB_ID_PATTERN.test(record.jobId) ||
        typeof record.reservedAt !== "number" ||
        record.reservedAt > nowSeconds + 60 ||
        (!cancelRequested && nowSeconds - record.reservedAt > PROVISIONING_TTL_SECONDS)
      ) return [];
      return [{
        jobId: record.jobId,
        reservedAt: record.reservedAt,
        ...(cancelRequested ? { cancelRequested: true as const } : {}),
      }];
    });
  } catch {
    return [];
  }
}

export function saveProvisioningReferences(
  storage: Storage,
  identityKey: string,
  references: ProvisioningReference[],
): void {
  storage.setItem(storageKey(identityKey), JSON.stringify(references.map((reference) => ({
    jobId: reference.jobId,
    reservedAt: reference.reservedAt,
    ...(reference.cancelRequested ? { cancelRequested: true } : {}),
  }))));
}

function taskSummary(task: SkillWorkbenchTask): SkillWorkbenchTaskSummary {
  return {
    jobId: task.jobId,
    operation: task.operation,
    intent: task.intent,
    revision: task.revision,
    state: task.state,
    stage: task.stage,
    createdAt: Math.floor(Date.now() / 1_000),
    ...(task.name ? { name: task.name } : {}),
    ...(task.source?.name ? { sourceName: task.source.name } : {}),
    ...(typeof task.recoveryAvailable === "boolean"
      ? { recoveryAvailable: task.recoveryAvailable }
      : {}),
  };
}

function restoredProvisioning(reference: ProvisioningReference): SkillWorkbenchProvisioningTask {
  return {
    jobId: reference.jobId,
    operation: null,
    intent: "Skill 会话",
    revision: 1,
    state: "provisioning",
    stage: "provisioning",
    createdAt: reference.reservedAt,
  };
}

const RELEASED_DEVENV_MESSAGE =
  "DevEnv 已到期或被释放，当前产物已无法下载或发布。";
const CLEANUP_FAILED_MESSAGE =
  "删除 Skill 会话失败，临时 DevEnv 可能仍在运行，请稍后重试。";

function cleanupFailureMessage(cause: unknown): string {
  const message = cause instanceof Error ? cause.message.trim() : "";
  return message.includes("临时 DevEnv 可能仍在运行")
    ? message
    : CLEANUP_FAILED_MESSAGE;
}

function expiredTask(
  jobId: string,
  previous: SkillWorkbenchTask | SkillWorkbenchTaskListItem | null,
): SkillWorkbenchTask {
  const activities = previous && "activities" in previous
    ? previous.activities
    : [];
  const name = previous && "name" in previous ? previous.name : undefined;
  const recoveryAvailable =
    previous && "recoveryAvailable" in previous
      ? previous.recoveryAvailable
      : undefined;
  const toolId = previous && "toolId" in previous ? previous.toolId : undefined;
  const sessionId = previous && "sessionId" in previous ? previous.sessionId : undefined;
  return {
    jobId,
    operation: previous?.operation ?? "create",
    intent: previous?.intent || "Skill 会话",
    revision: previous?.revision ?? 1,
    state: "expired",
    stage: "expired",
    activities,
    files: [],
    ...(toolId ? { toolId } : {}),
    ...(sessionId ? { sessionId } : {}),
    ...(name ? { name } : {}),
    ...(typeof recoveryAvailable === "boolean" ? { recoveryAvailable } : {}),
    error: RELEASED_DEVENV_MESSAGE,
  };
}

export function useSkillWorkbenchTasks(enabled: boolean, identityKey: string) {
  const [tasks, setTasks] = useState<SkillWorkbenchTaskListItem[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksError, setTasksError] = useState("");
  const [activeJobId, setActiveJobId] = useState("");
  const [activeSelectionRevision, setActiveSelectionRevision] = useState(0);
  const [activeTask, setActiveTask] = useState<SkillWorkbenchTask | null>(null);
  const [activeTaskLoading, setActiveTaskLoading] = useState(false);
  const [activeTaskError, setActiveTaskError] = useState("");
  const [activeTaskRecovering, setActiveTaskRecovering] = useState(false);
  const [activeArtifact, setActiveArtifact] = useState<SkillWorkbenchArtifact | null>(null);
  const [activeArtifactLoading, setActiveArtifactLoading] = useState(false);
  const [activeArtifactError, setActiveArtifactError] = useState("");
  const [startingTask, setStartingTask] = useState(false);
  const [startError, setStartError] = useState("");
  const [cleanupError, setCleanupError] = useState("");
  const generationRef = useRef(0);
  const listRequestRef = useRef(0);
  const detailRequestRef = useRef(0);
  const artifactRequestRef = useRef(0);
  const listFailureCountRef = useRef(0);
  const detailFailureCountRef = useRef(0);
  const referencesRef = useRef<ProvisioningReference[]>([]);
  const cleanupRequestsRef = useRef<Map<string, Promise<void>>>(new Map());
  const selectedTaskRef = useRef<SkillWorkbenchTaskListItem | null>(null);
  const tasksRef = useRef<SkillWorkbenchTaskListItem[]>([]);
  const activeTaskRef = useRef<SkillWorkbenchTask | null>(null);

  useEffect(() => {
    tasksRef.current = tasks;
  }, [tasks]);

  useEffect(() => {
    activeTaskRef.current = activeTask;
  }, [activeTask]);

  const persistReferences = useCallback((next: ProvisioningReference[]) => {
    referencesRef.current = next;
    if (identityKey && typeof localStorage !== "undefined") {
      saveProvisioningReferences(localStorage, identityKey, next);
    }
  }, [identityKey]);

  const requestProvisioningCleanup = useCallback((jobId: string): Promise<void> => {
    const pending = cleanupRequestsRef.current.get(jobId);
    if (pending) return pending;
    const request = (async () => {
      try {
        await deleteSkillWorkbenchTask(jobId);
      } finally {
        cleanupRequestsRef.current.delete(jobId);
      }
    })();
    cleanupRequestsRef.current.set(jobId, request);
    return request;
  }, []);

  const confirmProvisioningCleanup = useCallback(async (jobId: string) => {
    const generation = generationRef.current;
    await requestProvisioningCleanup(jobId);
    if (generation !== generationRef.current) return;
    persistReferences(referencesRef.current.filter((item) => item.jobId !== jobId));
    setTasks((current) => current.filter((item) => item.jobId !== jobId));
    setActiveJobId((current) => current === jobId ? "" : current);
    setActiveTask((current) => current?.jobId === jobId ? null : current);
    setCleanupError("");
  }, [persistReferences, requestProvisioningCleanup]);

  const reconcileTasks = useCallback((durable: SkillWorkbenchTaskSummary[]) => {
    const durableIds = new Set(durable.map((task) => task.jobId));
    const now = Math.floor(Date.now() / 1_000);
    const remaining = referencesRef.current.filter((reference) => (
      reference.cancelRequested ||
      (
        !durableIds.has(reference.jobId) &&
        now - reference.reservedAt <= PROVISIONING_TTL_SECONDS
      )
    ));
    if (remaining.length !== referencesRef.current.length) persistReferences(remaining);
    setTasks((current) => {
      const cancelledIds = new Set(
        remaining
          .filter((reference) => reference.cancelRequested)
          .map((reference) => reference.jobId),
      );
      const cancelledPlaceholders = current.filter(
        (task) => task.state === "provisioning" && cancelledIds.has(task.jobId),
      );
      const missing = current.filter((task) =>
        task.state !== "provisioning" && !durableIds.has(task.jobId)
      );
      return [
        ...cancelledPlaceholders,
        ...remaining
          .filter((reference) => !reference.cancelRequested)
          .map((reference) =>
            current.find((task) =>
              task.jobId === reference.jobId &&
              task.state === "provisioning"
            ) ?? restoredProvisioning(reference)
          ),
        ...durable.filter((task) => !cancelledIds.has(task.jobId)),
        ...missing,
      ].sort((a, b) => b.createdAt - a.createdAt);
    });

    for (const reference of remaining) {
      if (
        reference.cancelRequested &&
        (
          durableIds.has(reference.jobId) ||
          now - reference.reservedAt > PROVISIONING_TTL_SECONDS
        )
      ) {
        void confirmProvisioningCleanup(reference.jobId).catch((cause) => {
          setCleanupError(cleanupFailureMessage(cause));
        });
      }
    }
  }, [confirmProvisioningCleanup, persistReferences]);

  const refreshTasks = useCallback(async (signal?: AbortSignal) => {
    if (!enabled || !identityKey) return;
    const generation = generationRef.current;
    const request = ++listRequestRef.current;
    if (tasksRef.current.length === 0) setTasksLoading(true);
    try {
      const next = await listSkillWorkbenchTasks(signal);
      if (generation !== generationRef.current || request !== listRequestRef.current) return;
      listFailureCountRef.current = 0;
      reconcileTasks(next);
      setTasksError("");
    } catch (cause) {
      if (signal?.aborted || generation !== generationRef.current || request !== listRequestRef.current) return;
      const retryable = isRetryableSyncFailure(cause);
      listFailureCountRef.current = retryable
        ? listFailureCountRef.current + 1
        : 0;
      if (
        !retryable ||
        tasksRef.current.length === 0 ||
        listFailureCountRef.current >= SYNC_ERROR_REVEAL_THRESHOLD
      ) {
        setTasksError(retryable
          ? "Skill 会话列表连接不稳定，正在自动重试。"
          : cause instanceof Error ? cause.message : String(cause));
      }
    } finally {
      if (generation === generationRef.current && request === listRequestRef.current) setTasksLoading(false);
    }
  }, [enabled, identityKey, reconcileTasks]);

  const refreshActiveTask = useCallback(async (signal?: AbortSignal) => {
    if (!enabled || !identityKey || !activeJobId) return;
    const generation = generationRef.current;
    const request = ++detailRequestRef.current;
    const requestedJobId = activeJobId;
    const provisioning = referencesRef.current.find((item) => item.jobId === requestedJobId);
    setActiveTaskLoading(!provisioning);
    try {
      const next = await getSkillWorkbenchTask(requestedJobId, signal);
      if (generation !== generationRef.current || request !== detailRequestRef.current || requestedJobId !== activeJobId) return;
      detailFailureCountRef.current = 0;
      persistReferences(referencesRef.current.filter((item) => item.jobId !== requestedJobId));
      setActiveTask(next);
      setActiveTaskError("");
      setActiveTaskRecovering(false);
      setTasks((current) => {
        const existing = current.find((item) => item.jobId === next.jobId);
        const summary = { ...taskSummary(next), ...(existing ? { createdAt: existing.createdAt } : {}) };
        selectedTaskRef.current = summary;
        return [summary, ...current.filter((item) => item.jobId !== next.jobId)];
      });
    } catch (cause) {
      if (signal?.aborted || generation !== generationRef.current || request !== detailRequestRef.current || requestedJobId !== activeJobId) return;
      if (
        provisioning &&
        cause instanceof SkillWorkbenchApiError &&
        (
          cause.status === 404 ||
          cause.code === "SKILL_TASK_INITIALIZING"
        )
      ) {
        detailFailureCountRef.current = 0;
        setActiveTaskError("");
        setActiveTaskRecovering(false);
      } else if (
        cause instanceof SkillWorkbenchApiError &&
        (
          cause.code === "SKILL_TASK_EXPIRED" ||
          cause.code === "SKILL_TASK_NOT_FOUND" ||
          cause.status === 410
        )
      ) {
        const released = expiredTask(
          requestedJobId,
          selectedTaskRef.current,
        );
        persistReferences(
          referencesRef.current.filter((item) => item.jobId !== requestedJobId),
        );
        setActiveTask(released);
        setActiveTaskError("");
        setActiveTaskRecovering(false);
        detailFailureCountRef.current = 0;
        setTasks((current) => {
          const existing = current.find((item) => item.jobId === requestedJobId);
          const summary = {
            ...taskSummary(released),
            ...(existing ? { createdAt: existing.createdAt } : {}),
          };
          selectedTaskRef.current = summary;
          return [summary, ...current.filter((item) => item.jobId !== requestedJobId)];
        });
      } else {
        const retryable = isRetryableSyncFailure(cause);
        if (retryable) {
          detailFailureCountRef.current += 1;
          const reveal =
            detailFailureCountRef.current >= SYNC_ERROR_REVEAL_THRESHOLD;
          setActiveTaskRecovering(reveal);
          if (reveal) {
            setActiveTaskError(
              "暂时无法读取 DevEnv 状态，正在自动重试。当前会话和已完成内容已保留。",
            );
          } else {
            setActiveTaskError("");
          }
        } else {
          detailFailureCountRef.current = 0;
          setActiveTaskRecovering(false);
          setActiveTaskError(cause instanceof Error ? cause.message : String(cause));
        }
      }
    } finally {
      if (generation === generationRef.current && request === detailRequestRef.current && requestedJobId === activeJobId) {
        setActiveTaskLoading(false);
      }
    }
  }, [activeJobId, enabled, identityKey, persistReferences]);

  useEffect(() => {
    generationRef.current += 1;
    const references = enabled && identityKey && typeof localStorage !== "undefined"
      ? loadProvisioningReferences(localStorage, identityKey)
      : [];
    referencesRef.current = references;
    setTasks(references.filter((item) => !item.cancelRequested).map(restoredProvisioning));
    selectedTaskRef.current = null;
    setTasksError("");
    setActiveJobId("");
    setActiveTask(null);
    setActiveTaskError("");
    setActiveTaskRecovering(false);
    setActiveArtifact(null);
    setActiveArtifactError("");
    setStartError("");
    setCleanupError("");
    listFailureCountRef.current = 0;
    detailFailureCountRef.current = 0;
    setStartingTask(false);
    if (!enabled || !identityKey) return;
    const controller = new AbortController();
    void refreshTasks(controller.signal);
    return () => controller.abort();
  }, [enabled, identityKey, refreshTasks]);

  const hasActiveTask = tasks.some((task) => task.state === "running" || task.state === "provisioning");
  const hasPendingCleanup = referencesRef.current.some((reference) => reference.cancelRequested);
  useEffect(() => {
    if (!enabled || !identityKey || (!hasActiveTask && !hasPendingCleanup)) return;
    let timer: number | undefined;
    let stopped = false;
    const poll = async () => {
      await refreshTasks();
      if (!stopped) {
        timer = window.setTimeout(
          poll,
          pollDelay(LIST_POLL_INTERVAL_MS, listFailureCountRef.current),
        );
      }
    };
    timer = window.setTimeout(poll, LIST_POLL_INTERVAL_MS);
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [enabled, hasActiveTask, hasPendingCleanup, identityKey, refreshTasks]);

  useEffect(() => {
    if (!activeJobId) {
      setActiveTask(null);
      setActiveTaskError("");
      return;
    }
    const controller = new AbortController();
    void refreshActiveTask(controller.signal);
    return () => controller.abort();
  }, [activeJobId, activeSelectionRevision, refreshActiveTask]);

  const activeIsProvisioning = tasks.some((task) => task.jobId === activeJobId && task.state === "provisioning");
  useEffect(() => {
    if (!activeJobId || (!activeIsProvisioning && (!activeTask || TERMINAL_STATES.has(activeTask.state)))) return;
    let timer: number | undefined;
    let stopped = false;
    const poll = async () => {
      await refreshActiveTask();
      if (!stopped) {
        timer = window.setTimeout(
          poll,
          pollDelay(DETAIL_POLL_INTERVAL_MS, detailFailureCountRef.current),
        );
      }
    };
    timer = window.setTimeout(poll, DETAIL_POLL_INTERVAL_MS);
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [activeIsProvisioning, activeJobId, activeTask?.state, refreshActiveTask]);

  const refreshActiveArtifact = useCallback(async (signal?: AbortSignal) => {
    if (
      !activeJobId ||
      !activeTask ||
      (activeTask.state !== "ready" && activeTask.state !== "published")
    ) return;
    const request = ++artifactRequestRef.current;
    setActiveArtifactLoading(true);
    setActiveArtifactError("");
    try {
      const artifact = await getSkillWorkbenchArtifact(activeJobId, signal);
      if (request === artifactRequestRef.current) setActiveArtifact(artifact);
    } catch (cause) {
      if (signal?.aborted || request !== artifactRequestRef.current) return;
      setActiveArtifactError(cause instanceof Error ? cause.message : String(cause));
      throw cause;
    } finally {
      if (request === artifactRequestRef.current) setActiveArtifactLoading(false);
    }
  }, [activeJobId, activeTask]);

  useEffect(() => {
    if (
      !activeJobId ||
      !activeTask ||
      (activeTask.state !== "ready" && activeTask.state !== "published")
    ) {
      artifactRequestRef.current += 1;
      setActiveArtifact(null);
      setActiveArtifactLoading(false);
      setActiveArtifactError("");
      return;
    }
    const controller = new AbortController();
    let timer: number | undefined;
    let attempts = 0;
    const load = () => {
      void refreshActiveArtifact(controller.signal).catch((cause) => {
        if (controller.signal.aborted) return;
        const retryable = isRetryableSyncFailure(cause);
        if (retryable && attempts < ARTIFACT_RETRY_LIMIT) {
          attempts += 1;
          setActiveArtifactError("");
          setActiveArtifactLoading(true);
          timer = window.setTimeout(load, ARTIFACT_RETRY_INTERVAL_MS);
        }
      });
    };
    load();
    return () => {
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [
    activeJobId,
    activeTask?.revision,
    activeTask?.state,
    refreshActiveArtifact,
  ]);

  useEffect(() => {
    if (!enabled || !identityKey) return;
    const refreshVisible = () => {
      if (document.visibilityState === "visible") void refreshTasks();
    };
    window.addEventListener("focus", refreshVisible);
    document.addEventListener("visibilitychange", refreshVisible);
    return () => {
      window.removeEventListener("focus", refreshVisible);
      document.removeEventListener("visibilitychange", refreshVisible);
    };
  }, [enabled, identityKey, refreshTasks]);

  const selectTask = useCallback((jobId: string) => {
    selectedTaskRef.current = tasks.find((task) => task.jobId === jobId) ?? null;
    setActiveJobId(jobId);
    setActiveSelectionRevision((revision) => revision + 1);
    setActiveTask((current) => current?.jobId === jobId ? current : null);
    setActiveTaskError("");
    setActiveTaskRecovering(false);
    detailFailureCountRef.current = 0;
  }, [tasks]);

  const upsertTask = useCallback((task: SkillWorkbenchTask) => {
    persistReferences(referencesRef.current.filter((item) => item.jobId !== task.jobId));
    setActiveJobId(task.jobId);
    selectedTaskRef.current = taskSummary(task);
    setActiveTask(task);
    setActiveTaskError("");
    setActiveTaskRecovering(false);
    detailFailureCountRef.current = 0;
    setTasks((current) => {
      const existing = current.find((item) => item.jobId === task.jobId);
      const summary = { ...taskSummary(task), ...(existing ? { createdAt: existing.createdAt } : {}) };
      return [summary, ...current.filter((item) => item.jobId !== task.jobId)];
    });
  }, [persistReferences]);

  const startTask = useCallback(async (args: StartSkillWorkbenchTaskArgs) => {
    setStartingTask(true);
    setStartError("");
    const generation = generationRef.current;
    let reservation: { jobId: string; reservedAt: number };
    try {
      reservation = await reserveSkillWorkbenchTask();
    } catch (cause) {
      if (cause instanceof SkillWorkbenchApiError && cause.status === 404) {
        try {
          const task = await createSkillWorkbenchTask(args);
          if (generation === generationRef.current) upsertTask(task);
          return task;
        } finally {
          if (generation === generationRef.current) setStartingTask(false);
        }
      }
      const message = cause instanceof Error ? cause.message : String(cause);
      setStartError(message);
      setStartingTask(false);
      throw cause;
    }
    if (generation !== generationRef.current) {
      setStartingTask(false);
      throw new Error("用户身份已变化，请重新创建任务。");
    }
    const reference: ProvisioningReference = reservation;
    persistReferences([...referencesRef.current.filter((item) => item.jobId !== reference.jobId), reference]);
    const placeholder: SkillWorkbenchProvisioningTask = {
      jobId: reference.jobId,
      operation: args.operation,
      intent: args.intent,
      ...(args.source?.name || args.file?.name
        ? { sourceName: args.source?.name || args.file?.name }
        : {}),
      revision: 1,
      state: "provisioning",
      stage: "provisioning",
      createdAt: reference.reservedAt,
    };
    setTasks((current) => [placeholder, ...current.filter((item) => item.jobId !== reference.jobId)]);
    setActiveJobId(reference.jobId);
    setActiveTask(null);
    setStartingTask(false);
    try {
      const task = await createSkillWorkbenchTask({ ...args, jobId: reference.jobId });
      if (generation !== generationRef.current) return task;
      const cancelled = referencesRef.current.find((item) => item.jobId === reference.jobId)?.cancelRequested;
      if (cancelled) {
        try {
          await confirmProvisioningCleanup(reference.jobId);
        } catch (cause) {
          setCleanupError(cleanupFailureMessage(cause));
          throw cause;
        }
        return task;
      }
      upsertTask(task);
      return task;
    } catch (cause) {
      if (generation === generationRef.current) {
        const message = cause instanceof Error ? cause.message : String(cause);
        setStartError(message);
        setActiveTaskError(message);
      }
      throw cause;
    }
  }, [confirmProvisioningCleanup, persistReferences, upsertTask]);

  const cancelProvisioning = useCallback(async (jobId: string) => {
    const current = referencesRef.current.find((item) => item.jobId === jobId);
    if (!current) return;
    const generation = generationRef.current;
    persistReferences(referencesRef.current.map((item) => item.jobId === jobId
      ? { ...item, cancelRequested: true }
      : item));
    try {
      await requestProvisioningCleanup(jobId);
      if (generation !== generationRef.current) return;
      setTasks((tasksNow) => tasksNow.filter((item) => item.jobId !== jobId));
      setActiveJobId((value) => value === jobId ? "" : value);
      setCleanupError("");
    } catch (cause) {
      if (generation !== generationRef.current) throw cause;
      const message = cleanupFailureMessage(cause);
      setCleanupError(message);
      throw new Error(message);
    }
  }, [persistReferences, requestProvisioningCleanup]);

  const removeTask = useCallback((jobId: string) => {
    persistReferences(referencesRef.current.filter((item) => item.jobId !== jobId));
    setTasks((current) => current.filter((item) => item.jobId !== jobId));
    setActiveJobId((current) => current === jobId ? "" : current);
    setActiveTask((current) => current?.jobId === jobId ? null : current);
    if (activeTaskRef.current?.jobId === jobId) activeTaskRef.current = null;
    if (selectedTaskRef.current?.jobId === jobId) selectedTaskRef.current = null;
  }, [persistReferences]);

  const deleteTask = useCallback(async (jobId: string) => {
    if (referencesRef.current.some((item) => item.jobId === jobId)) {
      await cancelProvisioning(jobId);
      return;
    }
    await deleteSkillWorkbenchTask(jobId);
    removeTask(jobId);
  }, [cancelProvisioning, removeTask]);

  const stopTask = useCallback(async (
    jobId: string,
    expectedRevision: number,
  ): Promise<SkillWorkbenchTask> => {
    detailRequestRef.current += 1;
    const task = await stopSkillWorkbenchTask({ jobId, expectedRevision });
    upsertTask(task);
    return task;
  }, [upsertTask]);

  return {
    tasks,
    tasksLoading,
    tasksError: cleanupError || tasksError,
    activeJobId,
    activeTask,
    activeProvisioningTask: tasks.find(
      (task): task is SkillWorkbenchProvisioningTask =>
        task.jobId === activeJobId && task.state === "provisioning",
    ) ?? null,
    activeTaskLoading,
    activeTaskError,
    activeTaskRecovering,
    activeArtifact,
    activeArtifactLoading,
    activeArtifactError,
    startingTask,
    startError,
    selectTask,
    clearActiveTask: () => selectTask(""),
    startTask,
    cancelProvisioning,
    upsertTask,
    removeTask,
    deleteTask,
    stopTask,
    refreshTasks,
    refreshActiveTask,
    refreshActiveArtifact,
  };
}
