import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const app = fs.readFileSync(path.join(root, "src/App.tsx"), "utf8");
const blocks = fs.readFileSync(path.join(root, "src/blocks.ts"), "utf8");
const client = fs.readFileSync(path.join(root, "src/adk/client.ts"), "utf8");
const renderer = fs.readFileSync(path.join(root, "src/ui/Blocks.tsx"), "utf8");

test("mounts every selected generation task before its first run", () => {
  assert.match(app, /NEW_CHAT_TASK_TOOLS\[selectedTask\]/);
  assert.match(app, /sessionCapabilities: runWithSessionCapabilities/);
});

test("turns artifact deltas into previewable and downloadable PowerPoint cards", () => {
  assert.match(blocks, /kind: "artifact"/);
  assert.match(blocks, /artifactDelta \?\? ev\.actions\?\.artifact_delta/);
  assert.match(renderer, /预览/);
  assert.match(renderer, /下载/);
  assert.match(renderer, /\.preview\.webp/);
  assert.match(client, /export async function downloadArtifact/);
  assert.match(client, /export async function previewArtifact/);
});
