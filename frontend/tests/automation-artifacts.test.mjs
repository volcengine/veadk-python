import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

async function loadTypeScriptModule(relativePath) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(relativePath, import.meta.url))],
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node20",
    write: false,
  });
  const source = Buffer.from(result.outputFiles[0].contents).toString("base64");
  return import(`data:text/javascript;base64,${source}`);
}

function jsonResponse(status, payload = null) {
  return new Response(status === 204 ? null : JSON.stringify(payload), {
    status,
    headers: status === 204 ? undefined : { "Content-Type": "application/json" },
  });
}

test("generates the basic Studio project and Runtime delivery workflow in frontend", async () => {
  const [{ buildBasicTemplateFiles }, { buildRuntimeDeliveryWorkflow }] = await Promise.all([
    loadTypeScriptModule("../src/automations/templateProject.ts"),
    loadTypeScriptModule("../src/automations/runtimeDelivery.ts"),
  ]);
  const files = buildBasicTemplateFiles("basic-agent");
  assert.match(files["app.py"], /create_agentkit_app\(/);
  assert.match(files["app.py"], /enable_feishu=True/);
  assert.match(files["app.py"], /run_agentkit_app\(app\)/);
  assert.doesNotMatch(files["app.py"], /AgentkitAgentServerApp/);
  assert.match(files["assistant/agent.py"], /root_agent = Agent\(/);
  assert.match(files["requirements.txt"], /lark-channel-sdk/);
  assert.match(files["README.md"], /python app\.py/);

  const workflow = buildRuntimeDeliveryWorkflow({
    baseBranch: "main",
    projectPath: "examples/basic-agent",
    runtimeName: "basic-agent",
    runtimeId: "rt-basic-agent",
    region: "cn-beijing",
  });
  assert.match(workflow, /Publish to AgentKit Runtime/);
  assert.match(workflow, /\$\{\{ secrets\.VOLCENGINE_ACCESS_KEY \}\}/);
  assert.match(workflow, /AgentkitRuntimeClient/);
  assert.match(workflow, /"runtime_role_name": runtime_role_name/);
  assert.match(workflow, /"image_tag": f"veadk-v\{next_version\}"/);
  assert.match(workflow, /working-directory: "examples\/basic-agent"/);
  assert.match(workflow, /group: "agentkit-runtime-rt-basic-agent"/);
  assert.doesNotMatch(workflow, /__[A-Z_]+__/);
});

test("generates the isolated pull request review workflow in frontend", async () => {
  const { buildPullRequestReviewWorkflow } = await loadTypeScriptModule(
    "../src/automations/pullRequestReview.ts",
  );
  const workflow = buildPullRequestReviewWorkflow({
    sandboxToolId: "tool-code-review",
    modelName: "doubao-seed-code-preview",
    modelBaseUrl: "https://ark.cn-beijing.volces.com/api/coding/v3",
    region: "cn-beijing",
  });
  assert.doesNotMatch(workflow, /pull_request_target/);
  assert.match(workflow, /github\.event\.pull_request\.head\.repo\.full_name == github\.repository/);
  assert.match(workflow, /agentkit sandbox exec \\/);
  assert.match(workflow, /--copy \. \/workspace \\/);
  assert.match(workflow, /codex review --base \$\{\{ github\.event\.pull_request\.base\.sha \}\}/);
  assert.match(workflow, /agentkit sandbox delete \\/);
  assert.match(workflow, /\$\{\{ secrets\.CODEX_MODEL_API_KEY \}\}/);
  assert.match(workflow, /re\.sub\(r"\\x1b\\\[/);
  assert.doesNotMatch(workflow, /__GH__|__[A-Z_]+__/);
});

test("rejects invalid Runtime and review settings before generating workflows", async () => {
  const [{ buildRuntimeDeliveryWorkflow }, { buildPullRequestReviewWorkflow }] = await Promise.all([
    loadTypeScriptModule("../src/automations/runtimeDelivery.ts"),
    loadTypeScriptModule("../src/automations/pullRequestReview.ts"),
  ]);
  assert.throws(
    () => buildRuntimeDeliveryWorkflow({
      baseBranch: "main",
      projectPath: ".",
      runtimeName: "invalid runtime",
      runtimeId: "rt-agent",
      region: "cn-beijing",
    }),
    /Runtime 名称/,
  );
  assert.throws(
    () => buildPullRequestReviewWorkflow({
      sandboxToolId: "tool-code-review",
      modelName: "review-model",
      modelBaseUrl: "http://model.example.com/v1",
      region: "cn-beijing",
    }),
    /HTTPS URL/,
  );
});

test("normalizes supported GitHub repository forms and rejects unsafe paths", async () => {
  const { normalizeGitHubRepository, normalizeRepositoryPath } = await loadTypeScriptModule(
    "../src/adk/githubIntegration.ts",
  );
  assert.equal(normalizeGitHubRepository("https://www.github.com/acme/agent.git"), "acme/agent");
  assert.equal(normalizeGitHubRepository("git@github.com:acme/agent.git"), "acme/agent");
  assert.throws(() => normalizeGitHubRepository("https://example.com/acme/agent"), /github\.com/);
  assert.throws(() => normalizeRepositoryPath("../escape"), /安全相对路径/);
});

test("creates a GitHub pull request directly without persisting the token", async () => {
  const { createGitHubPullRequest } = await loadTypeScriptModule(
    "../src/adk/githubIntegration.ts",
  );
  const calls = [];
  const originalFetch = globalThis.fetch;
  const originalCrypto = globalThis.crypto;
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    const method = init.method || "GET";
    if (String(url).endsWith("/repos/acme/agent")) return jsonResponse(200, {});
    if (String(url).includes("/git/ref/heads/main")) {
      return jsonResponse(200, { object: { sha: "base-sha" } });
    }
    if (method === "POST" && String(url).endsWith("/git/refs")) {
      return jsonResponse(201, { ref: "refs/heads/feat/test" });
    }
    if (method === "GET" && String(url).includes("/contents/")) {
      return jsonResponse(404, { message: "Not Found" });
    }
    if (method === "PUT" && String(url).includes("/contents/")) {
      return jsonResponse(201, { content: { sha: "file-sha" } });
    }
    if (method === "POST" && String(url).endsWith("/pulls")) {
      return jsonResponse(201, {
        number: 42,
        html_url: "https://github.com/acme/agent/pull/42",
      });
    }
    throw new Error(`Unexpected request: ${method} ${url}`);
  };
  Object.defineProperty(globalThis, "crypto", {
    configurable: true,
    value: { randomUUID: () => "12345678-1234-1234-1234-123456789012" },
  });

  try {
    const result = await createGitHubPullRequest(
      {
        repository: "https://github.com/acme/agent.git",
        baseBranch: "main",
        token: "github-secret-token",
        files: [{
          path: ".github/workflows/test.yml",
          content: "hello 世界",
          commitMessage: "chore: add workflow",
        }],
        branchPrefix: "feat/test",
        title: "chore: test",
        description: "test",
      },
      new AbortController().signal,
    );
    assert.equal(result.number, 42);
    assert.equal(result.url, "https://github.com/acme/agent/pull/42");
    assert.match(result.branch, /^feat\/test-\d{14}-12345678$/);
    assert.equal(calls.every(({ url }) => url.startsWith("https://api.github.com/")), true);
    assert.equal(
      calls.every(({ init }) => init.headers.Authorization === "Bearer github-secret-token"),
      true,
    );
    const putCall = calls.find(({ init }) => init.method === "PUT");
    const putBody = JSON.parse(putCall.init.body);
    assert.equal(Buffer.from(putBody.content, "base64").toString("utf8"), "hello 世界");
    assert.equal(calls.every(({ init }) => !String(init.body).includes("github-secret-token")), true);
  } finally {
    globalThis.fetch = originalFetch;
    Object.defineProperty(globalThis, "crypto", {
      configurable: true,
      value: originalCrypto,
    });
  }
});

test("removes the temporary GitHub branch when file creation fails", async () => {
  const { createGitHubPullRequest } = await loadTypeScriptModule(
    "../src/adk/githubIntegration.ts",
  );
  const calls = [];
  const originalFetch = globalThis.fetch;
  const originalCrypto = globalThis.crypto;
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    const method = init.method || "GET";
    if (String(url).endsWith("/repos/acme/agent")) return jsonResponse(200, {});
    if (String(url).includes("/git/ref/heads/main")) {
      return jsonResponse(200, { object: { sha: "base-sha" } });
    }
    if (method === "POST" && String(url).endsWith("/git/refs")) return jsonResponse(201, {});
    if (method === "GET" && String(url).includes("/contents/")) return jsonResponse(404, {});
    if (method === "PUT") return jsonResponse(500, { message: "write failed" });
    if (method === "DELETE") return jsonResponse(204);
    throw new Error(`Unexpected request: ${method} ${url}`);
  };
  Object.defineProperty(globalThis, "crypto", {
    configurable: true,
    value: { randomUUID: () => "12345678-1234-1234-1234-123456789012" },
  });

  try {
    await assert.rejects(
      createGitHubPullRequest(
        {
          repository: "acme/agent",
          baseBranch: "main",
          token: "github-secret-token",
          files: [{ path: "test.txt", content: "test", commitMessage: "test" }],
          branchPrefix: "feat/test",
          title: "test",
          description: "test",
        },
        new AbortController().signal,
      ),
      /write failed/,
    );
    assert.equal(calls.some(({ init }) => init.method === "DELETE"), true);
  } finally {
    globalThis.fetch = originalFetch;
    Object.defineProperty(globalThis, "crypto", {
      configurable: true,
      value: originalCrypto,
    });
  }
});
