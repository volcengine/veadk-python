import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { build, transform } from "esbuild";

const require = createRequire(import.meta.url);

async function importTypeScript(relativePath) {
  const source = readFileSync(new URL(relativePath, import.meta.url), "utf8");
  const { code } = await transform(source, {
    format: "esm",
    loader: "ts",
    target: "es2022",
  });
  return import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
}

async function importTsxBundle(relativePath) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(relativePath, import.meta.url))],
    bundle: true,
    external: ["react"],
    format: "cjs",
    platform: "node",
    write: false,
  });
  const module = { exports: {} };
  Function("require", "module", "exports", result.outputFiles[0].text)(
    require,
    module,
    module.exports,
  );
  return module.exports;
}

test("tracks current context separately from cumulative session usage", async () => {
  const {
    aggregateTokenUsage,
    addTokenUsage,
    buildContextGrid,
    contextComposition,
    estimateSystemContextTokens,
    EMPTY_SESSION_TOKEN_USAGE,
  } =
    await importTypeScript("../src/adk/tokenUsage.ts");

  const total = aggregateTokenUsage([
    {
      modelVersion: "deepseek-v4-pro-260425",
      usageMetadata: {
        totalTokenCount: 120,
        promptTokenCount: 80,
        candidatesTokenCount: 30,
        thoughtsTokenCount: 10,
        cachedContentTokenCount: 24,
      },
    },
    {
      model_version: "deepseek-v4-pro-271231",
      usage_metadata: {
        total_token_count: 60,
        prompt_token_count: 50,
        candidates_token_count: 10,
      },
    },
    { content: { parts: [{ text: "no usage" }] } },
  ]);

  assert.deepEqual(total, {
    modelName: "deepseek-v4-pro-271231",
    current: {
      totalTokenCount: 60,
      promptTokenCount: 50,
      candidatesTokenCount: 10,
      thoughtsTokenCount: 0,
      cachedContentTokenCount: 0,
    },
    cumulative: {
      totalTokenCount: 180,
      promptTokenCount: 130,
      candidatesTokenCount: 40,
      thoughtsTokenCount: 10,
      cachedContentTokenCount: 24,
    },
  });
  assert.deepEqual(
    addTokenUsage(EMPTY_SESSION_TOKEN_USAGE, undefined),
    EMPTY_SESSION_TOKEN_USAGE,
  );
  assert.deepEqual(
    addTokenUsage(EMPTY_SESSION_TOKEN_USAGE, {
      modelVersion: "   ",
      model_version: "deepseek-v4-pro-260425",
    }),
    { ...EMPTY_SESSION_TOKEN_USAGE, modelName: "deepseek-v4-pro-260425" },
  );
  assert.equal(
    addTokenUsage(
      { ...EMPTY_SESSION_TOKEN_USAGE, modelName: "deepseek-v4-pro-260425" },
      { content: { parts: [{ text: "no model" }] } },
    ).modelName,
    "deepseek-v4-pro-260425",
  );

  const estimatedSystemTokens = estimateSystemContextTokens({
    instruction: "回答用户问题，并在需要时调用工具。",
    tools: ["web_search", "execute_code"],
    skills: [{ name: "research", description: "检索并核对来源" }],
  });
  assert.ok(estimatedSystemTokens > 0);

  const composition = contextComposition({
    usage: {
      current: {
        totalTokenCount: 800,
        promptTokenCount: 700,
        candidatesTokenCount: 80,
        thoughtsTokenCount: 20,
        cachedContentTokenCount: 0,
      },
      cumulative: total.cumulative,
    },
    contextWindow: 1_000,
    estimatedSystemTokens: 120,
  });
  assert.deepEqual(composition, {
    systemTokens: 120,
    inputTokens: 580,
    outputTokens: 100,
    remainingTokens: 200,
    usedTokens: 800,
    contextWindow: 1_000,
  });

  const initialComposition = contextComposition({
    usage: EMPTY_SESSION_TOKEN_USAGE,
    contextWindow: 1_000,
    estimatedSystemTokens: 120,
  });
  assert.equal(initialComposition.usedTokens, 120);
  assert.equal(initialComposition.remainingTokens, 880);

  const cells = buildContextGrid(composition);
  assert.equal(cells.length, 100);
  assert.deepEqual(cells[0].slices, [{ kind: "system", share: 1 }]);
  assert.deepEqual(cells[12].slices, [{ kind: "input", share: 1 }]);
  assert.deepEqual(cells[70].slices, [{ kind: "output", share: 1 }]);
  assert.deepEqual(cells[80].slices, [{ kind: "remaining", share: 1 }]);
  for (const cell of cells) {
    const totalShare = cell.slices.reduce((sum, slice) => sum + slice.share, 0);
    assert.ok(Math.abs(totalShare - 1) < 1e-9);
  }

  const partialCells = buildContextGrid(
    contextComposition({
      usage: {
        ...EMPTY_SESSION_TOKEN_USAGE,
        current: {
          totalTokenCount: 800,
          promptTokenCount: 700,
          candidatesTokenCount: 100,
          thoughtsTokenCount: 0,
          cachedContentTokenCount: 0,
        },
      },
      contextWindow: 1_000,
      estimatedSystemTokens: 125,
    }),
  );
  assert.deepEqual(partialCells[12].slices, [
    { kind: "system", share: 0.5 },
    { kind: "input", share: 0.5 },
  ]);

  const clampedEstimate = contextComposition({
    usage: {
      ...EMPTY_SESSION_TOKEN_USAGE,
      current: {
        totalTokenCount: 60,
        promptTokenCount: 50,
        candidatesTokenCount: 10,
        thoughtsTokenCount: 0,
        cachedContentTokenCount: 0,
      },
    },
    contextWindow: 1_000,
    estimatedSystemTokens: 120,
  });
  assert.equal(clampedEstimate.systemTokens, 50);
  assert.equal(clampedEstimate.inputTokens, 0);
  assert.equal(clampedEstimate.outputTokens, 10);

  const unknownEstimate = contextComposition({
    usage: {
      ...EMPTY_SESSION_TOKEN_USAGE,
      current: {
        totalTokenCount: 120,
        promptTokenCount: 100,
        candidatesTokenCount: 20,
        thoughtsTokenCount: 0,
        cachedContentTokenCount: 0,
      },
    },
    contextWindow: 1_000,
    estimatedSystemTokens: null,
  });
  assert.equal(unknownEstimate.systemTokens, 0);
  assert.equal(unknownEstimate.inputTokens, 100);

  const overflow = contextComposition({
    usage: {
      ...EMPTY_SESSION_TOKEN_USAGE,
      current: {
        totalTokenCount: 1_100,
        promptTokenCount: 900,
        candidatesTokenCount: 200,
        thoughtsTokenCount: 0,
        cachedContentTokenCount: 0,
      },
    },
    contextWindow: 1_000,
    estimatedSystemTokens: 100,
  });
  assert.equal(overflow.usedTokens, 1_100);
  assert.equal(overflow.remainingTokens, 0);
  assert.equal(buildContextGrid(overflow).length, 100);
});

test("resolves Ark context windows and explicit model suffixes", async () => {
  const { contextWindowForModel } =
    await importTypeScript("../src/adk/modelContextWindows.ts");

  assert.equal(
    contextWindowForModel("doubao-seed-2-1-pro-260628", "volcengine"),
    256_000,
  );
  assert.equal(
    contextWindowForModel("seed-2-0-lite-260228", "byteplus"),
    256_000,
  );
  assert.equal(contextWindowForModel("glm-4-7", "volcengine"), 200_000);
  assert.equal(contextWindowForModel("glm-4-7", "byteplus"), 256_000);
  assert.equal(
    contextWindowForModel("deepseek-v4-pro-260425", "volcengine"),
    1_024_000,
  );
  assert.equal(
    contextWindowForModel("deepseek-v4-pro-271231", "volcengine"),
    1_024_000,
  );
  assert.equal(contextWindowForModel("custom-model-32k", "volcengine"), 32_000);
  assert.equal(contextWindowForModel("custom-model-1m", "byteplus"), 1_000_000);
  assert.equal(
    contextWindowForModel("unlisted-private-endpoint", "volcengine"),
    null,
  );
});

test("renders exactly one hundred accessible context cells", async () => {
  const React = require("react");
  const { renderToStaticMarkup } = require("react-dom/server");
  const { TokenUsageIndicator } = await importTsxBundle(
    "../src/ui/TokenUsageIndicator.tsx",
  );
  const html = renderToStaticMarkup(
    React.createElement(TokenUsageIndicator, {
      cloudProvider: "volcengine",
      modelName: "doubao-seed-2-1-pro-260628",
      systemTokenEstimate: 2_560,
      usage: {
        modelName: "deepseek-v4-pro-260425",
        current: {
          totalTokenCount: 12_800,
          promptTokenCount: 10_240,
          candidatesTokenCount: 2_560,
          thoughtsTokenCount: 0,
          cachedContentTokenCount: 0,
        },
        cumulative: {
          totalTokenCount: 12_800,
          promptTokenCount: 10_240,
          candidatesTokenCount: 2_560,
          thoughtsTokenCount: 0,
          cachedContentTokenCount: 0,
        },
      },
    }),
  );

  assert.equal((html.match(/class="token-context-cell"/g) ?? []).length, 100);
  assert.match(html, /role="meter"/);
  assert.match(html, /aria-valuemax="256000"/);
  assert.match(html, /aria-valuenow="12800"/);
  assert.match(html, /100 格上下文构成图/);
  assert.match(html, /系统与工具/);
  assert.match(html, /输入与历史/);
  assert.match(html, /输出与思考/);
});

test("explains inseparable prompt tokens for legacy runtimes", async () => {
  const React = require("react");
  const { renderToStaticMarkup } = require("react-dom/server");
  const { TokenUsageIndicator } = await importTsxBundle(
    "../src/ui/TokenUsageIndicator.tsx",
  );
  const html = renderToStaticMarkup(
    React.createElement(TokenUsageIndicator, {
      cloudProvider: "volcengine",
      modelName: "deepseek-v4-pro-260425",
      systemTokenEstimate: null,
      usage: {
        modelName: "deepseek-v4-pro-260425",
        current: {
          totalTokenCount: 6_461,
          promptTokenCount: 6_204,
          candidatesTokenCount: 257,
          thoughtsTokenCount: 0,
          cachedContentTokenCount: 0,
        },
        cumulative: {
          totalTokenCount: 6_461,
          promptTokenCount: 6_204,
          candidatesTokenCount: 257,
          thoughtsTokenCount: 0,
          cachedContentTokenCount: 0,
        },
      },
    }),
  );

  assert.match(html, /系统与工具<\/dt><dd>未知<\/dd>/);
  assert.match(html, /提示词（含系统）/);
  assert.doesNotMatch(html, /系统与工具<em>未知<\/em>/);
  assert.match(html, /0\.63%<\/strong> 已用，剩余/);
  assert.match(html, /99\.37%/);
  assert.match(html, /6\.5K<\/strong> 已用，剩余/);
  assert.match(html, /1017\.5K<\/strong>，总计/);
  assert.match(html, /1024K/);
  assert.doesNotMatch(html, /\d(?:\.\d+)?M/);
});

test("renders an accessible context meter immediately left of send", () => {
  const composerSource = readFileSync(
    new URL("../src/ui/Composer.tsx", import.meta.url),
    "utf8",
  );
  const indicatorSource = readFileSync(
    new URL("../src/ui/TokenUsageIndicator.tsx", import.meta.url),
    "utf8",
  );
  const appSource = readFileSync(
    new URL("../src/App.tsx", import.meta.url),
    "utf8",
  );
  const stylesSource = readFileSync(
    new URL("../src/styles.css", import.meta.url),
    "utf8",
  );

  assert.match(
    composerSource,
    /<TokenUsageIndicator[\s\S]*?<motion\.button[\s\S]*?className="comp-send"/,
  );
  assert.match(indicatorSource, /role=\{contextWindow === null \? "status" : "meter"\}/);
  assert.match(indicatorSource, /role="tooltip"/);
  assert.match(indicatorSource, /aria-describedby=\{tooltipId\}/);
  assert.match(indicatorSource, /token-context-grid/);
  assert.match(indicatorSource, /token-context-breakdown/);
  assert.match(indicatorSource, /token-context-summary/);
  assert.match(indicatorSource, /cell\.slices\.map/);
  assert.match(indicatorSource, /系统与工具/);
  assert.match(indicatorSource, /输入与历史/);
  assert.match(indicatorSource, /输出与思考/);
  assert.match(indicatorSource, /剩余/);
  assert.match(indicatorSource, /估算/);
  assert.match(indicatorSource, /当前 Runtime 未提供模型信息/);
  assert.match(indicatorSource, /rawPercentage > 0 && rawPercentage < 1/);
  assert.match(
    appSource,
    /aggregateTokenUsage\(\s*session\.events \?\? \[\],?\s*\)/,
  );
  assert.match(appSource, /addTokenUsage\(previous, event\)/);
  assert.match(
    appSource,
    /modelName=\{agentInfo\?\.model\?\.trim\(\) \|\| activeTokenUsage\.modelName\}/,
  );
  assert.match(appSource, /estimateSystemContextTokens/);
  assert.match(composerSource, /systemTokenEstimate=\{systemTokenEstimate\}/);
  assert.match(
    composerSource,
    /sessionId && appName && newChatWorkspaceMode === "agent"/,
  );
  assert.match(
    stylesSource,
    /\.token-usage-indicator\s*\{[\s\S]*?width:\s*28px;/,
  );
  assert.match(
    stylesSource,
    /\.token-usage-ring\s*\{[\s\S]*?width:\s*16px;[\s\S]*?height:\s*16px;/,
  );
  assert.doesNotMatch(stylesSource, /\.token-usage-ring__value\s*\{[^}]*stroke-linecap:\s*round;/);
  assert.doesNotMatch(stylesSource, /\.token-usage-indicator\.is-unknown[^{]*\{[^}]*stroke-dasharray/);
  assert.match(
    composerSource,
    /className="composer-submit-actions"[\s\S]*?<TokenUsageIndicator[\s\S]*?<motion\.button/,
  );
  assert.match(
    stylesSource,
    /\.composer-submit-actions\s*\{[\s\S]*?align-items:\s*center;[\s\S]*?height:\s*36px;/,
  );
  assert.match(stylesSource, /\.token-usage-indicator:hover \.token-usage-tooltip/);
  assert.match(
    stylesSource,
    /\.token-context-breakdown\s*\{[\s\S]*?grid-template-columns:\s*max-content minmax\(0, 1fr\);/,
  );
  assert.match(stylesSource, /\.token-usage-indicator:focus-visible \.token-usage-tooltip/);
  assert.match(stylesSource, /@media \(prefers-reduced-motion: reduce\)/);
});
