import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import test from "node:test";
import { JSDOM } from "jsdom";
const require = createRequire(import.meta.url);
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
};

test("task hook fences identity changes, retains retry IDs and honors stop during initial submission", async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: "http://localhost" });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const calls = [],
    observers = [], seeds = [];
  let list = async () => [],
    creation = deferred(),
    stopFailure = false;
  globalThis.taskMock = {
    runEnded: (r) => ["succeeded", "cancelled", "failed"].includes(r.state),
    observeDevelopmentRuns: (session, signal, onUpdate, onConnection, onReady) => {
      onReady?.((run) => seeds.push(run));
      observers.push({ session, signal, onUpdate, onConnection });
      return new Promise(() => {});
    },
    developmentRuns: {
      list: (...args) => list(...args),
      create: (...args) => {
        calls.push(["create", ...args]);
        return creation.promise;
      },
      stop: async (id) => {
        calls.push(["stop", id]);
        if (stopFailure) throw new Error("stop response lost");
        return { runId: id, state: "stopping" };
      },
      steer: async (...args) => calls.push(["steer", ...args]),
      get: async (id) => ({ runId: id, state: "running" }),
    },
  };
  const result = await build({
    entryPoints: [
      fileURLToPath(
        new URL("../src/create/useDevelopmentRun.ts", import.meta.url),
      ),
    ],
    bundle: true,
    platform: "node",
    format: "cjs",
    write: false,
    external: ["react"],
    plugins: [
      {
        name: "task-boundary",
        setup(b) {
          b.onLoad({ filter: /adk\/developmentRuns\.ts$/ }, () => ({
            contents:
              "export const {developmentRuns,observeDevelopmentRuns,runEnded}=globalThis.taskMock;",
            loader: "js",
          }));
        },
      },
    ],
  });
  const module = { exports: {} };
  Function(
    "require",
    "module",
    "exports",
    result.outputFiles[0].text,
  )(require, module, module.exports);
  const React = require("react"),
    { act } = React;
  const root = require("react-dom/client").createRoot(
    document.getElementById("root"),
  );
  let hook,
    turns = [],
    busy = false;
  function Harness({ session, owner }) {
    hook = module.exports.useDevelopmentRun({
      sessionId: session,
      ownerId: owner,
      onTurns: (t) => {
        turns = t;
      },
      onBusy: (v) => {
        busy = v;
      },
    });
    return null;
  }
  const render = async (session, owner = "alice") =>
    act(async () =>
      root.render(React.createElement(Harness, { session, owner })),
    );
  try {
    await render("");
    let submitted;
    const listing = deferred();
    list = () => listing.promise;
    await act(async () => {
      submitted = hook.submit("build", "new-session");
    });
    assert.equal(turns[0].blocks[0].text, "build", "request is visible before discovery");
    await render("new-session");
    const optimisticId = turns[0].meta.localId;
    await act(async () => observers.at(-1).onUpdate([], null));
    assert.equal(turns[0].meta.localId, optimisticId, "empty discovery must not clear preparation");
    assert.equal(
      hook.submitting,
      true,
      "activation must retain the in-flight submission",
    );
    assert.equal(
      await hook.submit("build", "new-session"),
      false,
      "double send must not dispatch",
    );
    await act(async () => listing.resolve([]));
    assert.equal(calls.filter((c) => c[0] === "create").length, 1);
    list = async () => [];
    await act(async () => hook.stop());
    await render("elsewhere");
    await act(async () => {
      creation.resolve({ runId: "accepted", state: "running" });
      await submitted;
    });
    assert.deepEqual(
      calls.filter((c) => c[0] === "stop"),
      [["stop", "accepted"]],
      "navigation must retain an explicit pending stop",
    );

    await render("session-a");
    creation = deferred();
    let failed;
    await act(async () => {
      failed = hook.submit("retry me");
    });
    const firstId = calls.at(-1)[3];
    await act(async () => {
      creation.reject(new Error("temporary"));
      await failed;
    });
    assert.equal(hook.error, "temporary");
    creation = deferred();
    let retried;
    await act(async () => {
      retried = hook.submit("retry me");
    });
    assert.equal(
      calls.at(-1)[3],
      firstId,
      "ambiguous request retries use the same identity",
    );
    await act(async () => {
      creation.resolve({ runId: "retried", state: "running" });
      await retried;
    });
    assert.equal(seeds.at(-1).runId, "retried", "accepted run seeds immediate subscription");
    const old = observers.at(-1);
    await act(async () =>
      old.onUpdate(
        [
          { role: "user", blocks: [{ kind: "text", text: "retry me" }], meta: { localId: `${firstId}:user` } },
          {
            role: "assistant",
            meta: { localId: `${firstId}:assistant` },
            blocks: [{ kind: "text", text: "alice private" }],
          },
        ],
        { runId: "retried", state: "running" },
      ),
    );
    assert.equal(turns.length, 2, "acknowledgment replaces optimistic rows without duplication");
    await render("session-a", "bob");
    assert.deepEqual(turns, []);
    await act(async () => {
      old.onUpdate([{ role: "assistant", blocks: [] }], {
        runId: "foreign",
        state: "running",
      });
      old.onConnection("stale");
    });
    assert.deepEqual(turns, []);
    assert.equal(hook.connection, "");
    assert.equal(old.signal.aborted, true);

    await render("stop-network", "alice");
    creation = deferred();
    let interruptedSubmission;
    await act(async () => {
      interruptedSubmission = hook.submit("stop before response");
    });
    const stoppedRequestId = calls.at(-1)[3];
    list = async () => {
      throw new Error("offline");
    };
    await act(async () => hook.stop());
    await act(async () => {
      creation.reject(new Error("response lost"));
      await interruptedSubmission;
    });
    list = async () => [];
    creation = deferred();
    const createsBeforeRetry = calls.filter(
      (call) => call[0] === "create",
    ).length;
    let stopRetry;
    await act(async () => {
      stopRetry = hook.submit("stop before response");
    });
    assert.equal(
      calls.filter((call) => call[0] === "create").length,
      createsBeforeRetry + 1,
      "a failed Stop request must not permanently lock the composer",
    );
    assert.equal(calls.at(-1)[3], stoppedRequestId);
    await act(async () => {
      creation.resolve({ runId: "confirmed-after-retry", state: "running" });
      await stopRetry;
    });
    assert.deepEqual(
      calls.at(-1),
      ["stop", "confirmed-after-retry"],
      "reconciling the submission must retain its original stop intent",
    );

    await render("stop-after-acceptance", "alice");
    creation = deferred();
    let acceptedThenStopFailed;
    await act(async () => {
      acceptedThenStopFailed = hook.submit("stop accepted build");
    });
    await act(async () => hook.stop());
    stopFailure = true;
    await act(async () => {
      creation.resolve({ runId: "accepted-stop-failed", state: "running" });
      await acceptedThenStopFailed;
    });
    assert.equal(
      hook.stopPending,
      false,
      "a failed deferred Stop must remain retryable",
    );
    assert.equal(hook.error, "stop response lost");
    stopFailure = false;
    list = async () => [{ runId: "accepted-stop-failed", state: "running" }];
    await act(async () => hook.stop());
    assert.equal(hook.run.state, "stopping");
  } finally {
    await act(async () => root.unmount());
    dom.window.close();
    delete globalThis.taskMock;
  }
});
