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

test("codex project upload installs the Studio plugin from the feature branch", () => {
  assert.match(
    dialogSource,
    /codex plugin marketplace add evanlowe\/veadk-python-fork/,
  );
  assert.match(dialogSource, /--ref feat\/codex-project-handoff-plugin/);
  assert.match(dialogSource, /--sparse \.agents\/plugins/);
  assert.match(dialogSource, /--sparse plugins\/agentkit-studio/);
  assert.match(dialogSource, /codex plugin add agentkit-studio@veadk-python/);
  assert.doesNotMatch(dialogSource, /codex skill install/);
});

test("codex project upload explains the bundled skill and GitHub credential handoff", () => {
  assert.match(dialogSource, /安装 AgentKit Studio Plugin/);
  assert.match(dialogSource, /Plugin 内置/);
  assert.match(dialogSource, /codex-sandbox-upload/);
  assert.match(dialogSource, /gh auth login/);
  assert.match(dialogSource, /GitHub CLI 凭据/);
  assert.match(dialogSource, /独立的临时载荷/);
});
