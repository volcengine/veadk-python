import { useCallback, useEffect, useRef, useState } from "react";
import {
  createSkillWorkbenchTask,
  deleteSkillWorkbenchTask,
  getSkillWorkbenchArtifact,
  getSkillWorkbenchTask,
  listSkillWorkbenchTasks,
  reserveSkillWorkbenchTask,
  SkillWorkbenchApiError,
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

const LIST_POLL_INTERVAL_MS = 2_500;
const DETAIL_POLL_INTERVAL_MS = 1_200;
const PROVISIONING_TTL_SECONDS = 10 * 60;
const TERMINAL_STATES = new Set(["ready", "failed", "cancelled", "expired", "published"]);
const JOB_ID_PATTERN = /^sw-[0-9a-f]{12}-[0-9a-f]{24}$/;

interface ProvisioningReference {
  jobId: string;
  reservedAt: number;
  cancelRequested?: true;
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
      if (
        typeof record.jobId !== "string" ||
        !JOB_ID_PATTERN.test(record.jobId) ||
        typeof record.reservedAt !== "number" ||
        record.reservedAt > nowSeconds + 60 ||
        nowSeconds - record.reservedAt > PROVISIONING_TTL_SECONDS
      ) return [];
      return [{
        jobId: record.jobId,
        reservedAt: record.reservedAt,
        ...(record.cancelRequested === true ? { cancelRequested: true as const } : {}),
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
  };
}

function restoredProvisioning(reference: ProvisioningReference): SkillWorkbenchProvisioningTask {
  return {
    jobId: reference.jobId,
    operation: "create",
    intent: "Skill 任务",
    revision: 1,
    state: "provisioning",
    stage: "provisioning",
    createdAt: reference.reservedAt,
  };
}

export function useSkillWorkbenchTasks(enabled: boolean, identityKey: string) {
  const [tasks, setTasks] = useState<SkillWorkbenchTaskListItem[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksError, setTasksError] = useState("");
  const [activeJobId, setActiveJobId] = useState("");
  const [activeTask, setActiveTask] = useState<SkillWorkbenchTask | null>(null);
  const [activeTaskLoading, setActiveTaskLoading] = useState(false);
  const [activeTaskError, setActiveTaskError] = useState("");
  const [activeArtifact, setActiveArtifact] = useState<SkillWorkbenchArtifact | null>(null);
  const [activeArtifactLoading, setActiveArtifactLoading] = useState(false);
  const [activeArtifactError, setActiveArtifactError] = useState("");
  const [startingTask, setStartingTask] = useState(false);
  const [startError, setStartError] = useState("");
  const generationRef = useRef(0);
  const listRequestRef = useRef(0);
  const detailRequestRef = useRef(0);
  const artifactRequestRef = useRef(0);
  const referencesRef = useRef<ProvisioningReference[]>([]);

  const persistReferences = useCallback((next: ProvisioningReference[]) => {
    referencesRef.current = next;
    if (identityKey && typeof localStorage !== "undefined") {
      saveProvisioningReferences(localStorage, identityKey, next);
    }
  }, [identityKey]);

  const reconcileTasks = useCallback((durable: SkillWorkbenchTaskSummary[]) => {
    const durableIds = new Set(durable.map((task) => task.jobId));
    const now = Math.floor(Date.now() / 1_000);
    const remaining = referencesRef.current.filter((reference) =>
      !durableIds.has(reference.jobId) && now - reference.reservedAt <= PROVISIONING_TTL_SECONDS
    );
    if (remaining.length !== referencesRef.current.length) persistReferences(remaining);
    setTasks([
      ...remaining.filter((reference) => !reference.cancelRequested).map(restoredProvisioning),
      ...durable,
    ].sort((a, b) => b.createdAt - a.createdAt));

    for (const reference of referencesRef.current) {
      if (reference.cancelRequested && durableIds.has(reference.jobId)) {
        void deleteSkillWorkbenchTask(reference.jobId).finally(() => {
          persistReferences(referencesRef.current.filter((item) => item.jobId !== reference.jobId));
          setTasks((current) => current.filter((item) => item.jobId !== reference.jobId));
        });
      }
    }
  }, [persistReferences]);

  const refreshTasks = useCallback(async (signal?: AbortSignal) => {
    if (!enabled || !identityKey) return;
    const generation = generationRef.current;
    const request = ++listRequestRef.current;
    setTasksLoading(true);
    try {
      const next = await listSkillWorkbenchTasks(signal);
      if (generation !== generationRef.current || request !== listRequestRef.current) return;
      reconcileTasks(next);
      setTasksError("");
    } catch (cause) {
      if (signal?.aborted || generation !== generationRef.current || request !== listRequestRef.current) return;
      setTasksError(cause instanceof Error ? cause.message : String(cause));
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
      persistReferences(referencesRef.current.filter((item) => item.jobId !== requestedJobId));
      setActiveTask(next);
      setActiveTaskError("");
      setTasks((current) => {
        const existing = current.find((item) => item.jobId === next.jobId);
        const summary = { ...taskSummary(next), ...(existing ? { createdAt: existing.createdAt } : {}) };
        return [summary, ...current.filter((item) => item.jobId !== next.jobId)];
      });
    } catch (cause) {
      if (signal?.aborted || generation !== generationRef.current || request !== detailRequestRef.current || requestedJobId !== activeJobId) return;
      if (provisioning && cause instanceof SkillWorkbenchApiError && cause.status === 404) {
        setActiveTaskError("");
      } else {
        setActiveTaskError(cause instanceof Error ? cause.message : String(cause));
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
    setTasksError("");
    setActiveJobId("");
    setActiveTask(null);
    setActiveTaskError("");
    setActiveArtifact(null);
    setActiveArtifactError("");
    setStartError("");
    setStartingTask(false);
    if (!enabled || !identityKey) return;
    const controller = new AbortController();
    void refreshTasks(controller.signal);
    return () => controller.abort();
  }, [enabled, identityKey, refreshTasks]);

  const hasActiveTask = tasks.some((task) => task.state === "running" || task.state === "provisioning");
  useEffect(() => {
    if (!enabled || !identityKey || !hasActiveTask) return;
    let timer: number | undefined;
    let stopped = false;
    const poll = async () => {
      await refreshTasks();
      if (!stopped) timer = window.setTimeout(poll, LIST_POLL_INTERVAL_MS);
    };
    timer = window.setTimeout(poll, LIST_POLL_INTERVAL_MS);
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [enabled, hasActiveTask, identityKey, refreshTasks]);

  useEffect(() => {
    if (!activeJobId) {
      setActiveTask(null);
      setActiveTaskError("");
      return;
    }
    const controller = new AbortController();
    void refreshActiveTask(controller.signal);
    return () => controller.abort();
  }, [activeJobId, refreshActiveTask]);

  const activeIsProvisioning = tasks.some((task) => task.jobId === activeJobId && task.state === "provisioning");
  useEffect(() => {
    if (!activeJobId || (!activeIsProvisioning && (!activeTask || TERMINAL_STATES.has(activeTask.state)))) return;
    let timer: number | undefined;
    let stopped = false;
    const poll = async () => {
      await refreshActiveTask();
      if (!stopped) timer = window.setTimeout(poll, DETAIL_POLL_INTERVAL_MS);
    };
    timer = window.setTimeout(poll, DETAIL_POLL_INTERVAL_MS);
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [activeIsProvisioning, activeJobId, activeTask?.state, refreshActiveTask]);

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
    const request = ++artifactRequestRef.current;
    const controller = new AbortController();
    setActiveArtifactLoading(true);
    setActiveArtifactError("");
    void getSkillWorkbenchArtifact(activeJobId, controller.signal)
      .then((artifact) => {
        if (request === artifactRequestRef.current) setActiveArtifact(artifact);
      })
      .catch((cause) => {
        if (controller.signal.aborted || request !== artifactRequestRef.current) return;
        setActiveArtifactError(cause instanceof Error ? cause.message : String(cause));
      })
      .finally(() => {
        if (request === artifactRequestRef.current) setActiveArtifactLoading(false);
      });
    return () => controller.abort();
  }, [activeJobId, activeTask]);

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
    setActiveJobId(jobId);
    setActiveTask((current) => current?.jobId === jobId ? current : null);
    setActiveTaskError("");
  }, []);

  const upsertTask = useCallback((task: SkillWorkbenchTask) => {
    persistReferences(referencesRef.current.filter((item) => item.jobId !== task.jobId));
    setActiveJobId(task.jobId);
    setActiveTask(task);
    setActiveTaskError("");
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
        await deleteSkillWorkbenchTask(reference.jobId).catch(() => undefined);
        persistReferences(referencesRef.current.filter((item) => item.jobId !== reference.jobId));
        setTasks((current) => current.filter((item) => item.jobId !== reference.jobId));
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
  }, [persistReferences, upsertTask]);

  const cancelProvisioning = useCallback(async (jobId: string) => {
    const current = referencesRef.current.find((item) => item.jobId === jobId);
    if (!current) return;
    persistReferences(referencesRef.current.map((item) => item.jobId === jobId
      ? { ...item, cancelRequested: true }
      : item));
    setTasks((tasksNow) => tasksNow.filter((item) => item.jobId !== jobId));
    setActiveJobId((value) => value === jobId ? "" : value);
    await deleteSkillWorkbenchTask(jobId).catch(() => undefined);
  }, [persistReferences]);

  const removeTask = useCallback((jobId: string) => {
    persistReferences(referencesRef.current.filter((item) => item.jobId !== jobId));
    setTasks((current) => current.filter((item) => item.jobId !== jobId));
    setActiveJobId((current) => current === jobId ? "" : current);
    setActiveTask((current) => current?.jobId === jobId ? null : current);
  }, [persistReferences]);

  const deleteTask = useCallback(async (jobId: string) => {
    if (referencesRef.current.some((item) => item.jobId === jobId)) {
      await cancelProvisioning(jobId);
      return;
    }
    await deleteSkillWorkbenchTask(jobId);
    removeTask(jobId);
  }, [cancelProvisioning, removeTask]);

  return {
    tasks,
    tasksLoading,
    tasksError,
    activeJobId,
    activeTask,
    activeProvisioningTask: tasks.find(
      (task): task is SkillWorkbenchProvisioningTask =>
        task.jobId === activeJobId && task.state === "provisioning",
    ) ?? null,
    activeTaskLoading,
    activeTaskError,
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
    refreshTasks,
    refreshActiveTask,
  };
}
