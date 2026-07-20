import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(new URL("../src/adk/timeout.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const { requestSignal } = await import(moduleUrl);
const clientSource = readFileSync(new URL("../src/adk/client.ts", import.meta.url), "utf8");

function functionSource(start, end) {
  return clientSource.slice(clientSource.indexOf(start), clientSource.indexOf(end));
}

test("deadline aborts a normal request signal", async () => {
  const signal = requestSignal(undefined, 5);
  await new Promise((resolve) => setTimeout(resolve, 15));
  assert.equal(signal.aborted, true);
  assert.equal(signal.reason.name, "TimeoutError");
});

test("caller cancellation propagates through a deadline signal", () => {
  const controller = new AbortController();
  const signal = requestSignal(controller.signal, 10_000);
  controller.abort("cancelled by caller");
  assert.equal(signal.aborted, true);
  assert.equal(signal.reason, "cancelled by caller");
});

test("non-positive deadlines leave streaming signals unchanged", () => {
  const controller = new AbortController();
  assert.equal(requestSignal(controller.signal, 0), controller.signal);
  assert.equal(requestSignal(undefined, 0), undefined);
});

test("chat, deployment, and debug streams explicitly disable deadlines", () => {
  const chat = functionSource("export async function* runSSE", "const deploymentControllers");
  const deployment = functionSource(
    "export async function deployAgentkitProject",
    "export async function cancelAgentkitDeployment",
  );
  const debug = functionSource(
    "export async function* runGeneratedAgentTestSSE",
    "export async function deleteGeneratedAgentTestRun",
  );
  assert.match(chat, /ep,\s+0,/);
  assert.match(deployment, /\{\},\s+0,/);
  assert.match(debug, /\{\},\s+0,/);
});
