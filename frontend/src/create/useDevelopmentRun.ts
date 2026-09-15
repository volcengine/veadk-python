import { useEffect, useRef, useState } from "react";
import type { Turn } from "../blocks";
import { adkT } from "../adk/i18n";
import {
  developmentRuns,
  observeDevelopmentRuns,
  runEnded,
  type DevelopmentRun,
} from "../adk/developmentRuns";

export function useDevelopmentRun({
  sessionId,
  ownerId,
  onTurns,
  onBusy,
}: {
  sessionId: string;
  ownerId: string;
  onTurns: (turns: Turn[]) => void;
  onBusy: (busy: boolean) => void;
}) {
  const [run, setRun] = useState<DevelopmentRun | null>(null);
  const [connection, setConnection] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [stopPending, setStopPending] = useState(false);
  const callbacks = useRef({ onTurns, onBusy });
  callbacks.current = { onTurns, onBusy };
  const generation = useRef(0);
  const serverTurns = useRef<Turn[]>([]);
  const optimisticTurns = useRef<Turn[]>([]);
  const seedRun = useRef<((run: DevelopmentRun) => void) | null>(null);
  const publish = () => {
    const confirmed = new Set(serverTurns.current.map((turn) => turn.meta?.localId));
    optimisticTurns.current = optimisticTurns.current.filter((turn) => !confirmed.has(turn.meta?.localId));
    callbacks.current.onTurns([...serverTurns.current, ...optimisticTurns.current]);
  };
  const sending = useRef(false);
  const stopIntent = useRef(false);
  const retryInput = useRef<{
    session: string;
    owner: string;
    text: string;
    id: string;
    runId?: string;
    stopRequested?: boolean;
  } | null>(null);
  const currentIdentity = useRef({ sessionId, ownerId });
  currentIdentity.current = { sessionId, ownerId };

  useEffect(() => {
    generation.current += 1;
    setRun(null);
    setError("");
    setConnection("");
    serverTurns.current = [];
    seedRun.current = null;
    const pending = retryInput.current;
    if (pending?.session !== sessionId || pending.owner !== ownerId) {
      optimisticTurns.current = [];
      setStopPending(false);
      stopIntent.current = false;
      retryInput.current = null;
      sending.current = false;
      setSubmitting(false);
    }
    if (sessionId) publish();
    if (!sessionId || !ownerId) return;
    const controller = new AbortController();
    const isCurrent = () =>
      !controller.signal.aborted &&
      currentIdentity.current.sessionId === sessionId &&
      currentIdentity.current.ownerId === ownerId;
    void observeDevelopmentRuns(
      sessionId,
      controller.signal,
      (turns, current) => {
        if (!isCurrent()) return;
        serverTurns.current = turns;
        publish();
        setRun(current);
        callbacks.current.onBusy(sending.current || Boolean(current && !runEnded(current)));
        if (current && runEnded(current)) {
          setStopPending(false);
          stopIntent.current = false;
        }
      },
      (message) => {
        if (isCurrent()) setConnection(message);
      },
      (seed) => { if (isCurrent()) seedRun.current = seed; },
    ).catch((cause) => {
      if (isCurrent())
        setError(cause instanceof Error ? cause.message : String(cause));
    });
    return () => controller.abort();
  }, [sessionId, ownerId]);

  function prepare(text: string, targetSession = sessionId): Turn[] {
    const owner = currentIdentity.current.ownerId;
    let input = retryInput.current;
    if (!input || input.session !== targetSession || input.owner !== owner || input.text !== text) {
      input = { session: targetSession, owner, text, id: crypto.randomUUID() };
      retryInput.current = input;
    }
    if (!optimisticTurns.current.some((turn) => turn.meta?.localId === `${input.id}:user`)) {
      optimisticTurns.current.push(
        { role: "user", blocks: [{ kind: "text", text }], meta: { localId: `${input.id}:user` } },
        { role: "assistant", blocks: [{ kind: "progress", text: adkT("developmentRuns.preparing") }], meta: { localId: `${input.id}:assistant` } },
      );
    }
    return [...optimisticTurns.current];
  }

  async function submit(
    text: string,
    targetSession = sessionId,
  ): Promise<boolean> {
    if (!text.trim() || sending.current || stopIntent.current) return false;
    sending.current = true;
    setSubmitting(true);
    setError("");
    const owner = currentIdentity.current.ownerId;
    const active = () =>
      currentIdentity.current.ownerId === owner &&
      currentIdentity.current.sessionId === targetSession;
    prepare(text, targetSession);
    publish();
    callbacks.current.onBusy(true);
    const previous = retryInput.current;
    const input =
      previous?.session === targetSession &&
      previous.owner === owner &&
      previous.text === text
        ? previous
        : {
            session: targetSession,
            owner,
            text,
            id: crypto.randomUUID(),
            runId: undefined as string | undefined,
            stopRequested: false,
          };
    retryInput.current = input;
    try {
      const runs = await developmentRuns.list(targetSession);
      const current = runs[runs.length - 1];
      if (!active()) return false;
      if (
        !input.runId &&
        current &&
        !runEnded(current) &&
        current.requestId !== input.id
      )
        input.runId = current.runId;
      let accepted: DevelopmentRun;
      if (input.runId) {
        await developmentRuns.steer(input.runId, text, input.id);
        accepted = await developmentRuns.get(input.runId);
      } else {
        accepted = await developmentRuns.create(targetSession, text, input.id);
      }
      if (input.stopRequested || (active() && stopIntent.current))
        accepted = await developmentRuns.stop(accepted.runId);
      if (active()) {
        setRun(accepted);
        seedRun.current?.(accepted);
        callbacks.current.onBusy(!runEnded(accepted));
        retryInput.current = null;
      }
      return true;
    } catch (cause) {
      if (active()) {
        callbacks.current.onBusy(Boolean(run && !runEnded(run)));
        setError(cause instanceof Error ? cause.message : String(cause));
        if (input.stopRequested) {
          stopIntent.current = false;
          setStopPending(false);
        }
      }
      return false;
    } finally {
      if (active()) {
        sending.current = false;
        setSubmitting(false);
      }
    }
  }
  async function stop() {
    stopIntent.current = true;
    setStopPending(true);
    setError("");
    if (retryInput.current) retryInput.current.stopRequested = true;
    const epoch = generation.current;
    try {
      const runs = await developmentRuns.list(sessionId);
      const active = runs.find((item) => !runEnded(item));
      if (active) {
        const stopped = await developmentRuns.stop(active.runId);
        if (epoch === generation.current) setRun(stopped);
      } else if (!sending.current && epoch === generation.current) {
        stopIntent.current = false;
        setStopPending(false);
      }
    } catch (cause) {
      if (epoch === generation.current) {
        setError(cause instanceof Error ? cause.message : String(cause));
        setStopPending(false);
        // The request was not confirmed. Allow a retry even when the initial
        // submission also lost its response and no active run is known yet.
        // retryInput.stopRequested still stops that submission if it is found.
        stopIntent.current = false;
      }
    }
  }
  async function resume() {
    if (!run) return;
    const epoch = generation.current;
    try {
      const resumed = await developmentRuns.resume(run.runId);
      if (epoch === generation.current) {
        setRun(resumed);
        setError("");
      }
    } catch (cause) {
      if (epoch === generation.current)
        setError(cause instanceof Error ? cause.message : String(cause));
    }
  }
  return {
    run,
    connection,
    error,
    submitting,
    stopPending,
    prepare,
    submit,
    stop,
    resume,
  };
}
