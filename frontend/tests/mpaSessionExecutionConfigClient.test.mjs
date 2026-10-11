import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);

test("MPA session execution-config helpers call BFF routes with CAS headers", () => {
  assert.match(clientSource, /export interface MpaSessionExecutionConfig/);
  assert.match(clientSource, /export interface MpaExecutionConfigChange/);
  assert.match(clientSource, /export interface MpaProfileStatus/);
  assert.match(clientSource, /export class MpaExecutionConfigRequestError extends Error/);
  assert.match(clientSource, /export async function getMpaSessionExecutionConfig/);
  assert.match(clientSource, /signal\?: AbortSignal/);
  assert.match(clientSource, /\/web\/mpa\/sessions\/\$\{encodeURIComponent\(params\.sessionId\)\}\/execution-config\?\$\{query\.toString\(\)\}/);
  assert.match(clientSource, /export async function patchMpaSessionExecutionConfig/);
  assert.match(clientSource, /"If-Match": params\.etag/);
  assert.match(clientSource, /changes: params\.changes/);
  assert.match(clientSource, /export async function upgradeMpaSessionProfile/);
  assert.match(clientSource, /export async function getMpaProfileStatus/);
  assert.match(clientSource, /\/web\/mpa\/agents\/\$\{encodeURIComponent\(params\.mpaInstanceId\)\}\/profile-status\?\$\{query\.toString\(\)\}/);
  assert.match(clientSource, /\{ cache: "no-store", signal: params\.signal \}/);
  assert.match(clientSource, /"Idempotency-Key": params\.idempotencyKey/);
  assert.match(clientSource, /targetProfileRevision: params\.targetProfileRevision/);
  assert.doesNotMatch(clientSource, /runtime-proxy\/.*execution-config/);
});

test("runSSE can forward MPA execution config version and idempotency metadata", () => {
  assert.match(clientSource, /idempotencyKey\?: string/);
  assert.match(clientSource, /executionConfigVersion\?: number/);
  assert.match(clientSource, /const normalizedIdempotencyKey = idempotencyKey\?\.trim\(\) \?\? ""/);
  assert.match(clientSource, /"Idempotency-Key": normalizedIdempotencyKey/);
  assert.match(clientSource, /const hasExecutionConfigVersion = typeof executionConfigVersion === "number"/);
  assert.match(
    clientSource,
    /\.\.\.\(hasExecutionConfigVersion \? \{ executionConfigVersion \} : \{\}\)/,
  );
  assert.match(clientSource, /veadkExecution:[\s\S]*?executionConfigVersion/);
  assert.match(clientSource, /veadkExecution:[\s\S]*?idempotencyKey: normalizedIdempotencyKey/);
});
