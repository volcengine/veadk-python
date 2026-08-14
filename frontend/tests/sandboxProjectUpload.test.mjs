import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const sandboxClientSource = readFileSync(
  new URL("../src/adk/sandbox.ts", import.meta.url),
  "utf8",
);
const dialogSource = readFileSync(
  new URL("../src/ui/SandboxProjectUploadDialog.tsx", import.meta.url),
  "utf8",
);

test("codex project upload authorization is requested and shown as a one-hour TTL", () => {
  assert.match(
    sandboxClientSource,
    /CODEX_PROJECT_UPLOAD_AUTHORIZATION_TTL_SECONDS = 60 \* 60/,
  );
  assert.match(
    sandboxClientSource,
    /body: JSON\.stringify\(\{[\s\S]*?ttlSeconds: CODEX_PROJECT_UPLOAD_AUTHORIZATION_TTL_SECONDS/,
  );
  assert.match(dialogSource, /授权有效期/);
  assert.match(dialogSource, /\$\{hours\} 小时/);
  assert.doesNotMatch(dialogSource, /<dd>\{authorization\.expireAt\}<\/dd>/);
});
