import { useCallback, useEffect, useRef, useState } from "react";
import {
  getSkillWorkbenchTask,
  listSkillWorkbenchTasks,
} from "./api";
import type {
  SkillWorkbenchTask,
  SkillWorkbenchTaskSummary,
} from "./types";

const LIST_POLL_INTERVAL_MS = 2_500;
const DETAIL_POLL_INTERVAL_MS = 1_200;
const TERMINAL_STATES = new Set(["ready", "failed", "cancelled", "expired", "published"]);

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

export function useSkillWorkbenchTasks(enabled: boolean, identityKey: string) {
  const [tasks, setTasks] = useState<SkillWorkbenchTaskSummary[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksError, setTasksError] = useState("");
  const [activeJobId, setActiveJobId] = useState("");
  const [activeTask, setActiveTask] = useState<SkillWorkbenchTask | null>(null);
  const [activeTaskLoading, setActiveTaskLoading] = useState(false);
  const [activeTaskError, setActiveTaskError] = useState("");
  const generationRef = useRef(0);
  const listRequestRef = useRef(0);
  const detailRequestRef = useRef(0);

  const refreshTasks = useCallback(async (signal?: AbortSignal) => {
    if (!enabled || !identityKey) return;
    const generation = generationRef.current;
    const request = ++listRequestRef.current;
    setTasksLoading(true);
    try {
      const next = await listSkillWorkbenchTasks(signal);
      if (generation !== generationRef.current || request !== listRequestRef.current) return;
      setTasks(next);
      setTasksError("");
    } catch (cause) {
      if (
        signal?.aborted ||
        generation !== generationRef.current ||
        request !== listRequestRef.current
      ) return;
      setTasksError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      if (generation === generationRef.current && request === listRequestRef.current) {
        setTasksLoading(false);
      }
    }
  }, [enabled, identityKey]);

  const refreshActiveTask = useCallback(async (signal?: AbortSignal) => {
    if (!enabled || !identityKey || !activeJobId) return;
    const generation = generationRef.current;
    const request = ++detailRequestRef.current;
    const requestedJobId = activeJobId;
    setActiveTaskLoading(true);
    try {
      const next = await getSkillWorkbenchTask(requestedJobId, signal);
      if (
        generation !== generationRef.current ||
        request !== detailRequestRef.current ||
        requestedJobId !== activeJobId
      ) return;
      setActiveTask(next);
      setActiveTaskError("");
      setTasks((current) => {
        const summary = taskSummary(next);
        const found = current.some((item) => item.jobId === next.jobId);
        return found
          ? current.map((item) => item.jobId === next.jobId
              ? { ...summary, createdAt: item.createdAt }
              : item)
          : [summary, ...current];
      });
    } catch (cause) {
      if (
        signal?.aborted ||
        generation !== generationRef.current ||
        request !== detailRequestRef.current ||
        requestedJobId !== activeJobId
      ) return;
      setActiveTaskError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      if (
        generation === generationRef.current &&
        request === detailRequestRef.current &&
        requestedJobId === activeJobId
      ) setActiveTaskLoading(false);
    }
  }, [activeJobId, enabled, identityKey]);

  useEffect(() => {
    generationRef.current += 1;
    setTasks([]);
    setTasksError("");
    setActiveJobId("");
    setActiveTask(null);
    setActiveTaskError("");
    if (!enabled || !identityKey) return;
    const controller = new AbortController();
    void refreshTasks(controller.signal);
    return () => controller.abort();
  }, [enabled, identityKey, refreshTasks]);

  const hasRunningTask = tasks.some((task) => task.state === "running");
  useEffect(() => {
    if (!enabled || !identityKey || !hasRunningTask) return;
    let timer: number | undefined;
    let stopped = false;
    const poll = async () => {
      const controller = new AbortController();
      await refreshTasks(controller.signal);
      if (!stopped) timer = window.setTimeout(poll, LIST_POLL_INTERVAL_MS);
    };
    timer = window.setTimeout(poll, LIST_POLL_INTERVAL_MS);
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [enabled, hasRunningTask, identityKey, refreshTasks]);

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

  useEffect(() => {
    if (!activeJobId || !activeTask || TERMINAL_STATES.has(activeTask.state)) return;
    let timer: number | undefined;
    let stopped = false;
    const poll = async () => {
      const controller = new AbortController();
      await refreshActiveTask(controller.signal);
      if (!stopped) timer = window.setTimeout(poll, DETAIL_POLL_INTERVAL_MS);
    };
    timer = window.setTimeout(poll, DETAIL_POLL_INTERVAL_MS);
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [activeJobId, activeTask?.state, refreshActiveTask]);

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
    setActiveJobId(task.jobId);
    setActiveTask(task);
    setActiveTaskError("");
    setTasks((current) => {
      const existing = current.find((item) => item.jobId === task.jobId);
      const summary = {
        ...taskSummary(task),
        ...(existing ? { createdAt: existing.createdAt } : {}),
      };
      return [summary, ...current.filter((item) => item.jobId !== task.jobId)];
    });
  }, []);

  const removeTask = useCallback((jobId: string) => {
    setTasks((current) => current.filter((item) => item.jobId !== jobId));
    setActiveJobId((current) => current === jobId ? "" : current);
    setActiveTask((current) => current?.jobId === jobId ? null : current);
  }, []);

  return {
    tasks,
    tasksLoading,
    tasksError,
    activeJobId,
    activeTask,
    activeTaskLoading,
    activeTaskError,
    selectTask,
    clearActiveTask: () => selectTask(""),
    upsertTask,
    removeTask,
    refreshTasks,
    refreshActiveTask,
  };
}
