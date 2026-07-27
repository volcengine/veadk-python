import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = readFileSync(
  new URL("../src/adk/jsonResponse.ts", import.meta.url),
  "utf8",
);
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
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
