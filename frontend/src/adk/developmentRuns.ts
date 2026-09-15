import type { Turn } from "../blocks";
import { studioFetch } from "./client";
import { createSandboxProjection, sandboxHeaders } from "./sandbox";
import { adkT } from "./i18n";

export type DevelopmentRunState =
  | "queued"
  | "running"
  | "recovering"
  | "waiting_user"
  | "stopping"
  | "succeeded"
  | "cancelled"
  | "failed";
export interface DevelopmentRun {
  runId: string;
  sessionId: string;
  requestId: string;
  message: string;
  state: DevelopmentRunState;
  phase: string;
  threadId: string;
  turnId: string;
  inputRevision: number;
  lastSeq: number;
  stopRequested: boolean;
  createdAt: number;
  statusMessage: string;
}
export interface DevelopmentEvent {
  seq: number;
  type: string;
  payload: Record<string, unknown>;
}
export const runEnded = (run: DevelopmentRun) =>
  ["succeeded", "cancelled", "failed"].includes(run.state);
const base = "/web/intelligent-development";
export class DevelopmentRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}
async function request(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<unknown> {
  const response = await studioFetch(
    `${base}${path}`,
    {
      method,
      signal,
      headers: sandboxHeaders(
        body === undefined ? undefined : { "Content-Type": "application/json" },
      ),
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    },
    30_000,
  );
  if (!response.ok) {
    const value = await response.json().catch(() => null);
    const detail = value?.detail;
    throw new DevelopmentRequestError(
      typeof detail === "string"
        ? detail
        : detail?.message || adkT("developmentRuns.requestFailed"),
      response.status,
    );
  }
  return response.json();
}
function parseRun(value: unknown): DevelopmentRun {
  const run = value as DevelopmentRun;
  if (
    !run ||
    typeof run.runId !== "string" ||
    typeof run.sessionId !== "string" ||
    ![
      "queued",
      "running",
      "recovering",
      "waiting_user",
      "stopping",
      "succeeded",
      "cancelled",
      "failed",
    ].includes(run.state)
  )
    throw new Error(adkT("developmentRuns.invalidResponse"));
  return run;
}
export const developmentRuns = {
  async active(signal?: AbortSignal): Promise<DevelopmentRun[]> {
    const result = (await request("/runs", "GET", undefined, signal)) as {
      runs: unknown[];
    };
    if (!Array.isArray(result.runs))
      throw new Error(adkT("developmentRuns.invalidResponse"));
    return result.runs.map(parseRun);
  },
  async get(runId: string, signal?: AbortSignal): Promise<DevelopmentRun> {
    return parseRun(
      await request(
        `/runs/${encodeURIComponent(runId)}`,
        "GET",
        undefined,
        signal,
      ),
    );
  },
  async list(
    sessionId: string,
    signal?: AbortSignal,
  ): Promise<DevelopmentRun[]> {
    const result = (await request(
      `/sessions/${encodeURIComponent(sessionId)}/runs`,
      "GET",
      undefined,
      signal,
    )) as { runs: unknown[] };
    if (!Array.isArray(result.runs))
      throw new Error(adkT("developmentRuns.invalidResponse"));
    return result.runs.map(parseRun);
  },
  async create(
    sessionId: string,
    message: string,
    requestId: string,
  ): Promise<DevelopmentRun> {
    return parseRun(
      await request(`/sessions/${encodeURIComponent(sessionId)}/runs`, "POST", {
        message,
        requestId,
      }),
    );
  },
  async steer(runId: string, message: string, clientId: string): Promise<void> {
    await request(`/runs/${encodeURIComponent(runId)}/inputs`, "POST", {
      message,
      clientId,
    });
  },
  async stop(runId: string): Promise<DevelopmentRun> {
    return parseRun(
      await request(`/runs/${encodeURIComponent(runId)}/stop`, "POST"),
    );
  },
  async resume(runId: string): Promise<DevelopmentRun> {
    return parseRun(
      await request(`/runs/${encodeURIComponent(runId)}/resume`, "POST"),
    );
  },
};

/** Run-local projection sharing Studio's existing rich block renderer. */
export class DevelopmentRunProjection {
  cursor = 0;
  turns: Turn[] = [];
  private activeInput: string;
  private inputOrder: string[] = [];
  private projections = new Map<
    string,
    ReturnType<typeof createSandboxProjection>
  >();
  private itemInputs = new Map<string, string>();
  constructor(public run: DevelopmentRun) {
    this.activeInput = run.requestId;
  }
  private projection(input: string) {
    let projection = this.projections.get(input);
    if (!projection) {
      const turn: Turn = {
        role: "assistant",
        blocks: [],
        meta: { localId: `${input}:assistant` },
      };
      const userIndex = this.turns.findIndex(
        (item) => item.meta?.localId === `${input}:user`,
      );
      this.turns.splice(
        userIndex < 0 ? this.turns.length : userIndex + 1,
        0,
        turn,
      );
      projection = createSandboxProjection({
        onBlocks: (blocks) => {
          turn.blocks = blocks;
        },
        onUsage: (usage) => {
          turn.meta = { ...turn.meta, sandboxUsage: usage.usage };
        },
      });
      this.projections.set(input, projection);
    }
    return projection;
  }
  apply(event: DevelopmentEvent): void {
    if (event.payload.runId !== this.run.runId)
      throw new Error(adkT("developmentRuns.invalidResponse"));
    if (event.seq <= this.cursor) return;
    if (event.seq !== this.cursor + 1)
      throw new Error(adkT("developmentRuns.eventGap"));
    const value = event.payload;
    if (
      event.type === "run.input" &&
      typeof value.clientId === "string" &&
      typeof value.message === "string"
    ) {
      this.turns.push({
        role: "user",
        blocks: [{ kind: "text", text: value.message }],
        meta: { localId: `${value.clientId}:user` },
        activity: {
          id: `${value.clientId}:delivery`,
          title: adkT(`developmentRuns.input.${String(value.status)}`),
        },
      });
      this.inputOrder.push(value.clientId);
      if (
        value.status === "delivered" &&
        this.inputOrder.indexOf(value.clientId) >=
          this.inputOrder.indexOf(this.activeInput)
      )
        this.activeInput = value.clientId;
    } else if (
      event.type === "run.input_status" &&
      typeof value.clientId === "string"
    ) {
      const turn = this.turns.find(
        (item) =>
          item.meta?.localId === `${value.clientId}:user`,
      );
      if (turn)
        turn.activity = {
          id: `${value.clientId}:delivery`,
          title: adkT(`developmentRuns.input.${String(value.status)}`),
        };
      if (
        value.status === "delivered" &&
        this.inputOrder.indexOf(value.clientId) >=
          this.inputOrder.indexOf(this.activeInput)
      )
        this.activeInput = value.clientId;
    } else if (event.type === "run.status") {
      this.run = { ...this.run, ...value } as DevelopmentRun;
      if (runEnded(this.run) || this.run.state === "waiting_user")
        for (const projection of this.projections.values())
          projection.consumeFrame("event: done\ndata: {}");
    } else if (!event.type.startsWith("run.")) {
      const nativeId = typeof value.id === "string" && value.id ? value.id
        : ["plan", "diff"].includes(event.type) ? event.type : "";
      const itemId = nativeId ? `${String(value.turnId || "")}:${nativeId}` : "";
      const input = (itemId && this.itemInputs.get(itemId)) || this.activeInput;
      if (itemId) this.itemInputs.set(itemId, input);
      const commentary =
        event.type === "activity" && value.kind === "commentary";
      this.projection(input).consumeFrame(
        `event: ${commentary ? "delta" : event.type}\ndata: ${JSON.stringify({ ...value, ...(itemId ? { id: itemId } : {}), ...(commentary ? { snapshot: true } : {}) })}`,
      );
    }
    this.cursor = event.seq;
  }
}
function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, ms);
    signal.addEventListener("abort", abort, { once: true });
  });
}
async function readEvents(
  view: DevelopmentRunProjection,
  signal: AbortSignal,
  update: () => void,
): Promise<void> {
  const response = await studioFetch(
    `${base}/runs/${encodeURIComponent(view.run.runId)}/events?after=${view.cursor}`,
    { signal, headers: sandboxHeaders({ Accept: "text/event-stream" }) },
    0,
  );
  if (!response.ok)
    throw new DevelopmentRequestError(
      adkT("developmentRuns.requestFailed"),
      response.status,
    );
  if (!response.body) throw new Error(adkT("developmentRuns.invalidResponse"));
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let ended = false;
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() || "";
      for (const frame of frames) {
        const lines = frame.split(/\r?\n/);
        const type = lines
          .find((line) => line.startsWith("event:"))
          ?.slice(6)
          .trim();
        if (type === "done") {
          ended = true;
          continue;
        }
        const data = lines
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (!type || !data) continue;
        const payload = JSON.parse(data) as Record<string, unknown>;
        if (!Number.isSafeInteger(payload.seq))
          throw new Error(adkT("developmentRuns.invalidResponse"));
        view.apply({ seq: payload.seq as number, type, payload });
      }
      update();
      if (done) break;
    }
    if (!ended) throw new Error(adkT("developmentRuns.reconnecting"));
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
/** No browser persistence: identity changes discard projections and subscriptions. */
export async function observeDevelopmentRuns(
  sessionId: string,
  signal: AbortSignal,
  onUpdate: (turns: Turn[], current: DevelopmentRun | null) => void,
  onConnection: (message: string) => void,
  onReady?: (seed: (run: DevelopmentRun) => void) => void,
): Promise<void> {
  const views = new Map<string, DevelopmentRunProjection>();
  let retry = 0;
  const seeds = new Map<string, DevelopmentRun>();
  let wake: (() => void) | undefined;
  onReady?.((run) => {
    if (signal.aborted || run.sessionId !== sessionId) return;
    seeds.set(run.runId, run);
    wake?.();
  });
  const pause = (ms: number) => new Promise<void>((resolve) => {
    const finish = () => { clearTimeout(timer); signal.removeEventListener("abort", finish); wake = undefined; resolve(); };
    const timer = setTimeout(finish, ms);
    wake = finish;
    signal.addEventListener("abort", finish, { once: true });
    if (signal.aborted || seeds.size) finish();
  });
  const snapshots = new Map<DevelopmentRunProjection, { cursor: number; turns: Turn[] }>();
  const update = () => {
    if (signal.aborted) return;
    const all = [...views.values()];
    onUpdate(
      all.flatMap((view) => {
        let snapshot = snapshots.get(view);
        if (!snapshot || snapshot.cursor !== view.cursor) {
          snapshot = { cursor: view.cursor, turns: view.turns.map((turn) => ({ ...turn })) };
          snapshots.set(view, snapshot);
        }
        return snapshot.turns;
      }),
      all[all.length - 1]?.run || null,
    );
  };
  while (!signal.aborted) {
    try {
      const listed = seeds.size ? [] : await developmentRuns.list(sessionId, signal);
      const runs = [...new Map([...listed, ...seeds.values()].map((run) => [run.runId, run])).values()];
      seeds.clear();
      for (const run of runs) {
        let view = views.get(run.runId);
        if (!view) {
          view = new DevelopmentRunProjection(run);
          views.set(run.runId, view);
        }
        if (view.cursor >= run.lastSeq) view.run = run;
        if (
          view.cursor < run.lastSeq ||
          (!runEnded(run) && run.state !== "waiting_user")
        ) {
          try {
            await readEvents(view, signal, () => {
              retry = 0;
              onConnection("");
              update();
            });
          } catch (error) {
            // A completed run can expire between list and replay. Keep any
            // already rendered output and continue observing the current task.
            if (
              !(
                error instanceof DevelopmentRequestError &&
                error.status === 404 &&
                runEnded(run)
              )
            )
              throw error;
          }
        }
      }
      retry = 0;
      onConnection("");
      update();
      await pause(1500);
    } catch (error) {
      if (signal.aborted) return;
      if (
        error instanceof DevelopmentRequestError &&
        [401, 403, 404].includes(error.status)
      )
        throw error;
      onConnection(adkT("developmentRuns.reconnecting"));
      await delay(Math.min(1000 * 2 ** retry++, 15_000), signal);
    }
  }
}
