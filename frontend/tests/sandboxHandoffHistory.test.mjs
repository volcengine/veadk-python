import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const result = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/ui/sandboxCommands.ts", import.meta.url)),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(
  result.outputFiles[0].contents,
).toString("base64")}`;
const { sandboxSnapshotTurns } = await import(moduleUrl);

test("maps imported image history to a visible attachment before its text", () => {
  const turns = sandboxSnapshotTurns({
    thread: {
      id: "thread-1",
      preview: "请看图片",
      cwd: "/workspace",
      modelProvider: "openai",
      createdAt: 1,
      updatedAt: 2,
      status: "idle",
    },
    threadId: "thread-1",
    messages: [
      {
        id: "message-1",
        role: "user",
        content: "请看图片",
        timestamp: 2_000,
        images: [
          {
            mimeType: "image/png",
            data: "iVBORw0KGgppbWFnZQ==",
            name: "handoff.png",
            alt: "端云接力界面",
          },
        ],
      },
    ],
    workspaceLocked: false,
    permissions: {
      approvalPolicy: "never",
      approvalsReviewer: "user",
      sandboxMode: "workspace-write",
      networkAccess: true,
    },
  });

  assert.deepEqual(turns[0].blocks, [
    {
      kind: "attachment",
      files: [
        {
          id: "message-1-image-0",
          mimeType: "image/png",
          data: "iVBORw0KGgppbWFnZQ==",
          name: "端云接力界面",
        },
      ],
    },
    { kind: "text", text: "请看图片" },
  ]);
});
