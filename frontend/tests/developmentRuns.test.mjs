import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import test from "node:test";

globalThis.window = {
  location: { search: "", pathname: "/", hash: "", origin: "http://localhost" },
};
globalThis.localStorage = globalThis.sessionStorage = { getItem: () => null };
const bundled = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/adk/developmentRuns.ts", import.meta.url)),
  ],
  bundle: true,
  platform: "node",
  format: "esm",
  write: false,
});
const { DevelopmentRunProjection, observeDevelopmentRuns } = await import(
  `data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].contents).toString("base64")}`
);

const run = {
  runId: "run-a",
  requestId: "input-a",
  sessionId: "session-a",
  message: "Build",
  state: "running",
  lastSeq: 0,
  inputRevision: 1,
};
const event = (seq, type, payload) => ({
  seq,
  type,
  payload: { ...payload, runId: "run-a", seq },
});

test("empty thinking starts immediately and keeps its native identity", () => {
  const view = new DevelopmentRunProjection(run);
  view.apply(event(1, "activity", { id: "reason-1", turnId: "turn-1", itemType: "reasoning", kind: "thinking", status: "running", text: "" }));
  assert.equal(view.turns[0].blocks.length, 1);
  assert.equal(view.turns[0].blocks[0].kind, "thinking");
  assert.equal(view.turns[0].blocks[0].done, false);
  assert.equal(view.turns[0].blocks[0].id, "turn-1:reason-1");
  view.apply(event(2, "activity", { id: "reason-1", turnId: "turn-1", itemType: "reasoning", kind: "thinking", status: "done", text: "Checked the constraints" }));
  assert.equal(view.turns[0].blocks.length, 1);
  assert.equal(view.turns[0].blocks[0].done, true);
});

test("tool output streams into its item and failure cannot become success", () => {
  const view = new DevelopmentRunProjection(run);
  const item = { id: "cmd-1", turnId: "turn-1", itemType: "commandExecution", kind: "tool", name: "运行命令", args: { command: "cat agent.py", commandActions: [{ type: "read", name: "agent.py", path: "agent.py" }] } };
  view.apply(event(1, "activity", { ...item, status: "running" }));
  view.apply(event(2, "tool_output", { id: "cmd-1", turnId: "turn-1", text: "file ", snapshot: false }));
  view.apply(event(3, "tool_output", { id: "cmd-1", turnId: "turn-1", text: "missing", snapshot: false }));
  assert.equal(view.turns[0].blocks[0].response.output, "file missing");
  view.apply(event(4, "activity", { ...item, status: "error", durationMs: 321, response: { output: "file missing", exitCode: 1 } }));
  view.apply(event(5, "run.status", { ...run, state: "succeeded" }));
  assert.equal(view.turns[0].blocks.length, 1);
  assert.equal(view.turns[0].blocks[0].status, "failed");
  assert.equal(view.turns[0].blocks[0].durationMs, 321);
});

test("plans and diffs update in place and assistant phases remain separate", () => {
  const view = new DevelopmentRunProjection(run);
  view.apply(event(1, "delta", { id: "intro", turnId: "turn-1", phase: "commentary", text: "Checking" }));
  view.apply(event(2, "plan", { id: "plan:turn-1", turnId: "turn-1", items: [{ text: "Check", status: "in_progress" }] }));
  view.apply(event(3, "plan", { id: "plan:turn-1", turnId: "turn-1", items: [{ text: "Check", status: "completed" }] }));
  view.apply(event(4, "diff", { id: "diff:turn-1", turnId: "turn-1", text: "diff --git a/a.py b/a.py\n+first" }));
  view.apply(event(5, "diff", { id: "diff:turn-1", turnId: "turn-1", text: "diff --git a/a.py b/a.py\n+second" }));
  view.apply(event(6, "delta", { id: "answer", turnId: "turn-1", phase: "final_answer", text: "Complete" }));
  const blocks = view.turns[0].blocks;
  assert.deepEqual(blocks.map(block => block.kind), ["text", "plan", "diff", "text"]);
  assert.equal(blocks[0].phase, "commentary");
  assert.equal(blocks[1].items[0].status, "completed");
  assert.match(blocks[2].text, /second/);
  assert.equal(blocks[3].phase, "final_answer");
});

test("replayed events and authoritative snapshots preserve one copy of output", () => {
  const view = new DevelopmentRunProjection(run);
  view.apply(
    event(1, "run.input", {
      clientId: "input-a",
      message: "Build",
      status: "pending",
    }),
  );
  view.apply(
    event(2, "run.input_status", { clientId: "input-a", status: "delivered" }),
  );
  const delta = event(3, "delta", { id: "item-a", text: "already " });
  view.apply(delta);
  view.apply(delta);
  view.apply(
    event(4, "delta", {
      id: "item-a",
      text: "already generated",
      snapshot: true,
    }),
  );
  view.apply(
    event(5, "delta", { id: "item-a", text: "already", snapshot: true }),
  );
  view.apply(event(6, "run.status", { ...run, state: "recovering" }));
  assert.equal(
    view.turns[1].blocks.find((block) => block.kind === "text").text,
    "already generated",
  );
  assert.equal(view.cursor, 6);
  view.apply(event(7, "run.status", { ...run, state: "failed" }));
  assert.equal(
    view.turns[1].blocks.find((block) => block.kind === "text").text,
    "already generated",
  );
});

test("steer keeps prior output and gives delivered input its own response", () => {
  const view = new DevelopmentRunProjection(run);
  view.apply(
    event(1, "run.input", {
      clientId: "input-a",
      message: "Build",
      status: "delivered",
    }),
  );
  view.apply(event(2, "delta", { id: "item-a", text: "first output" }));
  view.apply(
    event(3, "run.input", {
      clientId: "input-b",
      message: "Change direction",
      status: "pending",
    }),
  );
  view.apply(
    event(4, "run.input_status", { clientId: "input-b", status: "delivered" }),
  );
  view.apply(event(5, "delta", { id: "item-b", text: "new output" }));
  assert.deepEqual(
    view.turns.map((turn) => turn.role),
    ["user", "assistant", "user", "assistant"],
  );
  assert.equal(view.turns[1].blocks[0].text, "first output");
  assert.equal(view.turns[3].blocks[0].text, "new output");
});

test("events from a different run cannot change the current transcript", () => {
  const view = new DevelopmentRunProjection(run);
  assert.throws(() =>
    view.apply({
      seq: 1,
      type: "delta",
      payload: { runId: "someone-else", text: "private" },
    }),
  );
  assert.equal(view.turns.length, 0);
});

test("commentary and late delivery acknowledgments cannot duplicate or move output", () => {
  const view = new DevelopmentRunProjection(run);
  view.apply(
    event(1, "run.input", {
      clientId: "input-a",
      message: "Build",
      status: "delivered",
    }),
  );
  view.apply(event(2, "delta", { id: "item-a", text: "plan" }));
  view.apply(
    event(3, "activity", {
      id: "item-a",
      kind: "commentary",
      text: "plan",
      status: "done",
    }),
  );
  assert.equal(view.turns[1].blocks.filter((x) => x.kind === "text").length, 1);
  assert.equal(view.turns[1].blocks[0].text, "plan");
  view.apply(
    event(4, "run.input", {
      clientId: "input-b",
      message: "change",
      status: "pending",
    }),
  );
  view.apply(
    event(5, "run.input_status", { clientId: "input-b", status: "delivered" }),
  );
  view.apply(
    event(6, "run.input_status", { clientId: "input-a", status: "delivered" }),
  );
  view.apply(event(7, "delta", { id: "item-b", text: "updated" }));
  assert.equal(view.turns[3].blocks[0].text, "updated");
});


test("accepted run wakes discovery immediately and replay batches frame updates", async () => {
  const previousFetch = globalThis.fetch;
  const controller = new AbortController();
  let seed, updates = 0, streamed = false;
  const frames = [event(1, "run.input", { clientId: "input-a", message: "Build", status: "delivered" }),
    ...Array.from({ length: 100 }, (_, i) => event(i + 2, "delta", { id: "answer", text: "a" }))];
  globalThis.fetch = async (url) => {
    if (String(url).includes("/events?after=0")) {
      streamed = true;
      return new Response(frames.map(e => `event: ${e.type}\ndata: ${JSON.stringify(e.payload)}\n\n`).join("") + "event: done\ndata: {}\n\n");
    }
    return Response.json({ runs: [] });
  };
  let observed;
  try {
    observed = observeDevelopmentRuns("session-a", controller.signal, (turns) => {
      updates++;
      if (turns.length) assert.equal(turns[1].blocks[0].text, "a".repeat(100));
    }, () => {}, value => { seed = value; });
    await new Promise(resolve => setTimeout(resolve, 20));
    seed({ ...run, state: "succeeded", lastSeq: 101 });
    await new Promise(resolve => setTimeout(resolve, 100));
    assert.equal(streamed, true, "create response should not wait for the discovery interval");
    assert.ok(updates <= 4, "one packet of replay should not render for every token");
  } finally {
    controller.abort();
    await observed;
    globalThis.fetch = previousFetch;
  }
});

test('steer keeps an active assistant before any new item, including replay', () => {
  const view = new DevelopmentRunProjection(run);
  view.apply(event(1, 'run.input', {clientId:'input-a',message:'Build',status:'delivered'}));
  view.apply(event(2, 'delta', {id:'answer',turnId:'turn-1',text:'working'}));
  view.apply(event(3, 'run.input', {clientId:'input-b',message:'Update',status:'delivered'}));
  assert.equal(view.turns.at(-1).role, 'assistant');
  assert.equal(view.turns.at(-1).meta.streaming, true);
  assert.equal(view.turns[1].meta.streaming, false);
  view.apply(event(4, 'delta', {id:'answer',turnId:'turn-1',text:' continues'}));
  assert.equal(view.turns.at(-1).meta.streaming, true);
});

test('one native turn summary counts unique tools across steer and replay, including failures', () => {
  const view = new DevelopmentRunProjection(run);
  view.apply(event(1, 'run.input', {clientId:'input-a',message:'Build',status:'delivered'}));
  const tool={id:'command',turnId:'turn-1',itemType:'commandExecution',kind:'tool',name:'command',status:'running'};
  view.apply(event(2,'activity',tool));
  view.apply(event(3,'run.input',{clientId:'input-b',message:'Update',status:'delivered'}));
  view.apply(event(4,'activity',{...tool,status:'error',durationMs:321}));
  view.apply(event(5,'activity',{...tool,id:'other',status:'done',durationMs:200}));
  view.apply(event(6,'activity',{id:'reasoning',turnId:'turn-1',kind:'thinking',status:'done',text:'checked'}));
  const end=event(7,'run.turn',{turnId:'turn-1',status:'interrupted',durationMs:4321,model:'test-model',usage:{totalTokens:120,inputTokens:100,cachedInputTokens:40,outputTokens:20,reasoningOutputTokens:5}});
  view.apply(end); view.apply(end);
  const summaries=view.turns.flatMap(t=>t.blocks).filter(b=>b.kind==='turn-summary');
  assert.equal(summaries.length,1);
  assert.equal(summaries[0].value.toolCalls,2);
  assert.equal(summaries[0].value.toolDurationMs,521);
  assert.equal(summaries[0].value.durationMs,4321);
  assert.equal(summaries[0].value.usage.totalTokens,120);
  assert.equal(view.turns[1].blocks.find(b=>b.kind==='tool').status,'failed');
});

test('native continuation summaries remain in order and missing terminal facts stay unknown', () => {
  const view=new DevelopmentRunProjection(run);
  view.apply(event(1,'run.input',{clientId:'input-a',message:'Build',status:'delivered'}));
  view.apply(event(2,'delta',{id:'answer-a',turnId:'first',text:'first answer'}));
  view.apply(event(3,'run.turn',{turnId:'first',status:'completed',durationMs:100}));
  view.apply(event(4,'delta',{id:'answer-b',turnId:'second',text:'second answer'}));
  view.apply(event(5,'run.turn',{turnId:'second',status:'inProgress',model:'model-b'}));
  view.apply(event(6,'run.status',{...run,state:'failed'}));
  const blocks=view.turns[1].blocks;
  assert.deepEqual(blocks.map(b=>b.kind),['text','turn-summary','text','turn-summary']);
  assert.equal(blocks[1].value.toolCalls,0);
  assert.equal(blocks[3].value.status,'unavailable');
  assert.equal(blocks[3].value.durationMs,undefined);
  assert.equal(blocks[3].value.usage,undefined);
  assert.equal(view.turns[1].meta.streaming,false);
});
