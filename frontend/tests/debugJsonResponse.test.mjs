import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

globalThis.localStorage = { getItem: () => "zh-CN" };
globalThis.window = { localStorage: globalThis.localStorage };

const result = await build({
  entryPoints: [fileURLToPath(new URL("../src/adk/jsonResponse.ts", import.meta.url))],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(result.outputFiles[0].contents).toString("base64")}`;
const { parseJsonResponse } = await import(moduleUrl);

function response({
  body,
  contentType = "application/json",
  redirected = false,
  status = 200,
  url = "",
}) {
  return {
    headers: new Headers({ "content-type": contentType }),
    redirected,
    status,
    text: async () => body,
    url,
  };
}

test("parses a normal JSON response", async () => {
  const result = await parseJsonResponse(
    response({ body: '{"runId":"run-1"}' }),
    "创建调试运行失败",
  );
  assert.deepEqual(result, { runId: "run-1" });
});

test("exposes a non-JSON gateway response", async () => {
  await assert.rejects(
    parseJsonResponse(
      response({
        body: "<!DOCTYPE html><title>upstream unavailable</title>",
        contentType: "text/html; charset=utf-8",
      }),
      "创建调试运行失败",
    ),
    (error) => {
      assert.match(error.message, /服务端返回非 JSON 响应/);
      assert.match(error.message, /HTTP 200/);
      assert.match(error.message, /text\/html/);
      assert.match(error.message, /upstream unavailable/);
      assert.doesNotMatch(error.message, /Unexpected token/);
      return true;
    },
  );
});
