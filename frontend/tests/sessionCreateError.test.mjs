import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);

test("session creation surfaces the backend error detail with its status", () => {
  assert.match(clientSource, /const fallback = `创建会话失败 \(\$\{res\.status\}\)`/);
  assert.match(
    clientSource,
    /const detail = await httpErrorMessage\(res, "创建会话失败"\)/,
  );
  assert.match(
    clientSource,
    /detail === fallback \? fallback : `\$\{fallback\}：\$\{detail\}`/,
  );
});
