import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const result = await build({
  entryPoints: [fileURLToPath(new URL("../src/blocks.ts", import.meta.url))],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(
  result.outputFiles[0].contents,
).toString("base64")}`;
const {
  createAssistantEventProjector,
  eventsToTurns,
  upsertProjectedAssistantTurn,
} = await import(moduleUrl);

function event(author, text, options = {}) {
  return {
    author,
    invocationId: options.invocationId ?? "invocation-1",
    id: options.id,
    partial: options.partial ?? true,
    timestamp: options.timestamp ?? 1,
    content: {
      role: "model",
      parts: [{ text, thought: options.thought ?? false }],
    },
  };
}

function blockText(turn, kind) {
  return turn.blocks
    .filter((block) => block.kind === kind)
    .map((block) => block.text)
    .join("");
}

test("keeps interleaved parallel authors in one stable turn per active response", () => {
  const projector = createAssistantEventProjector("test");
  let turns = [];
  for (const item of [
    event("parallel_alpha", "符", { thought: true }),
    event("parallel_beta", "用", { thought: true }),
    event("parallel_alpha", "合", { thought: true }),
    event("parallel_beta", "户", { thought: true }),
  ]) {
    turns = upsertProjectedAssistantTurn(turns, projector.project(item).turn);
  }

  assert.equal(turns.length, 2);
  assert.equal(blockText(turns[0], "thinking"), "符合");
  assert.equal(blockText(turns[1], "thinking"), "用户");
  assert.equal(turns[0].meta.streaming, true);
  assert.equal(turns[1].meta.streaming, true);
  assert.equal(turns[0].meta.eventId, undefined);
  assert.equal(turns[1].meta.eventId, undefined);

  turns = upsertProjectedAssistantTurn(
    turns,
    projector.project(event("parallel_alpha", "完整事实", {
      partial: false,
      id: "final-alpha",
    })).turn,
  );
  turns = upsertProjectedAssistantTurn(
    turns,
    projector.project(event("parallel_beta", "完整风险", {
      partial: false,
      id: "final-beta",
    })).turn,
  );

  assert.equal(turns.length, 2);
  assert.equal(blockText(turns[0], "text"), "完整事实");
  assert.equal(blockText(turns[1], "text"), "完整风险");
  assert.equal(turns[0].meta.streaming, false);
  assert.equal(turns[1].meta.streaming, false);
  assert.equal(turns[0].meta.eventId, "final-alpha");
  assert.equal(turns[1].meta.eventId, "final-beta");
});

test("starts a new turn when the same loop author produces another final response", () => {
  const projector = createAssistantEventProjector("loop");
  let turns = [];
  for (const item of [
    event("loop_reviewer", "第一轮", { partial: false, id: "loop-1" }),
    event("loop_reviewer", "第二轮", { partial: false, id: "loop-2" }),
    event("loop_reviewer", "第三轮", { partial: false, id: "loop-3" }),
  ]) {
    turns = upsertProjectedAssistantTurn(turns, projector.project(item).turn);
  }

  assert.deepEqual(turns.map((turn) => blockText(turn, "text")), [
    "第一轮",
    "第二轮",
    "第三轮",
  ]);
  assert.deepEqual(turns.map((turn) => turn.meta.eventId), [
    "loop-1",
    "loop-2",
    "loop-3",
  ]);
});

test("replays interleaved history without token cards and binds feedback to final events", () => {
  const events = [
    event("parallel_alpha", "符", { thought: true }),
    event("parallel_beta", "用", { thought: true }),
    event("parallel_alpha", "合", { thought: true }),
    event("parallel_beta", "户", { thought: true }),
    event("parallel_alpha", "完整事实", { partial: false, id: "final-alpha" }),
    event("parallel_beta", "完整风险", { partial: false, id: "final-beta" }),
  ];
  const turns = eventsToTurns(events, {
    "veadk_feedback:final-alpha": { rating: "good" },
  });

  assert.equal(turns.length, 2);
  assert.deepEqual(turns.map((turn) => blockText(turn, "text")), [
    "完整事实",
    "完整风险",
  ]);
  assert.equal(turns[0].meta.feedback.rating, "good");
  assert.equal(turns[1].meta.feedback, undefined);
});

test("keeps an OAuth-resumed response on its seeded turn when invocation changes", () => {
  const initialTurn = {
    role: "assistant",
    blocks: [{ kind: "auth", callId: "auth-1", authConfig: {}, done: true }],
    meta: {
      author: "oauth_agent",
      invocationId: "before-resume",
      eventId: "before-resume-event",
      localId: "oauth-turn",
    },
  };
  const projector = createAssistantEventProjector("oauth", initialTurn);
  const projected = projector.project(event("oauth_agent", "授权后完整回答", {
    invocationId: "after-resume",
    partial: false,
    id: "after-resume-event",
  })).turn;

  assert.equal(projected.meta.localId, "oauth-turn");
  assert.equal(projected.meta.invocationId, "after-resume");
  assert.equal(projected.meta.eventId, "after-resume-event");
  assert.deepEqual(projected.blocks.map((block) => block.kind), ["auth", "text"]);
});

test("replaces the optimistic assistant placeholder instead of leaving an empty turn", () => {
  const placeholder = {
    role: "assistant",
    blocks: [],
    meta: { localId: "pending-turn", streaming: true },
  };
  const projector = createAssistantEventProjector("send", placeholder);
  let turns = [
    { role: "user", blocks: [{ kind: "text", text: "问题" }] },
    placeholder,
  ];
  const projection = projector.project(event("answer_agent", "完整回答", {
    partial: false,
    id: "answer-final",
  }));
  turns = upsertProjectedAssistantTurn(turns, projection.turn);

  assert.equal(turns.length, 2);
  assert.equal(turns[1].meta.localId, "pending-turn");
  assert.equal(blockText(turns[1], "text"), "完整回答");
});

test("completes A2UI-only and artifact-only replies with persisted Event IDs", () => {
  const a2uiProjector = createAssistantEventProjector("a2ui");
  const a2ui = a2uiProjector.project({
    author: "ui_agent",
    invocationId: "ui-invocation",
    id: "ui-final",
    partial: false,
    content: {
      role: "model",
      parts: [{
        functionResponse: {
          name: "send_a2ui_json_to_client",
          response: { validated_a2ui_json: [{ surfaceUpdate: { surfaceId: "main" } }] },
        },
      }],
    },
  });
  assert.equal(a2ui.completed, true);
  assert.equal(a2ui.turn.meta.eventId, "ui-final");
  assert.deepEqual(a2ui.turn.blocks.map((block) => block.kind), ["a2ui"]);

  const artifactProjector = createAssistantEventProjector("artifact");
  const artifact = artifactProjector.project({
    author: "artifact_agent",
    invocationId: "artifact-invocation",
    id: "artifact-final",
    partial: false,
    actions: { artifactDelta: { "report.md": 1 } },
  });
  assert.equal(artifact.completed, true);
  assert.equal(artifact.turn.meta.eventId, "artifact-final");
  assert.deepEqual(artifact.turn.blocks.map((block) => block.kind), ["artifact"]);
});

test("ignores control-only events after a completed response", () => {
  const projector = createAssistantEventProjector("control");
  projector.project(event("worker", "完成", { partial: false, id: "final" }));
  const signal = projector.project({
    author: "worker",
    invocationId: "invocation-1",
    id: "end-signal",
    partial: false,
    actions: { endOfAgent: true },
  });
  assert.equal(signal.ignored, true);
  assert.deepEqual(projector.finish(), []);
});
