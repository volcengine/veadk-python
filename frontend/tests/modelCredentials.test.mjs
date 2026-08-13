import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

async function loadTypeScriptModule(relativePath) {
  const source = readFileSync(new URL(relativePath, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  });
  return import(
    `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
  );
}

const credentials = await loadTypeScriptModule(
  "../src/create/comparison/modelCredentials.ts",
);

test("requires a temporary key for a custom API Base and reports its host", () => {
  assert.deepEqual(
    credentials.validateModelConnection({
      modelName: "model-a",
      modelProvider: "custom",
      modelApiBase: "https://gateway.example.com/v1",
      apiKey: "",
      studioApiBase: "https://ark.example.com/api/v3",
    }),
    {
      ok: false,
      reason:
        "自定义 API Base gateway.example.com 不能使用 Studio 服务端凭据，请输入临时 API Key。",
    },
  );
});

test("requires HTTPS for both remote and loopback API bases", () => {
  assert.equal(
    credentials.validateModelConnection({
      modelName: "model-a",
      modelProvider: "custom",
      modelApiBase: "http://gateway.example.com/v1",
      apiKey: "key",
      studioApiBase: "",
    }).ok,
    false,
  );
  assert.equal(
    credentials.validateModelConnection({
      modelName: "model-a",
      modelProvider: "custom",
      modelApiBase: "http://127.0.0.1:8000/v1",
      apiKey: "key",
      studioApiBase: "",
    }).ok,
    false,
  );
  assert.equal(
    credentials.validateModelConnection({
      modelName: "model-a",
      modelProvider: "custom",
      modelApiBase: "https://gateway.example.com/v1",
      apiKey: "key",
      studioApiBase: "",
    }).ok,
    true,
  );
});

test("rejects API Base values that could embed credentials in generated source", () => {
  for (const modelApiBase of [
    "https://user:secret@gateway.example.com/v1",
    "https://gateway.example.com/v1?api_key=secret",
    "https://gateway.example.com/v1#credential",
  ]) {
    const result = credentials.validateModelConnection({
      modelName: "model-a",
      modelProvider: "custom",
      modelApiBase,
      apiKey: "temporary-key",
      studioApiBase: "https://ark.example.com/api/v3/",
    });
    assert.equal(result.ok, false);
    assert.match(result.reason, /不能包含账号、查询参数或片段/);
  }
});

test("inherits a temporary key only when Provider and API Base are unchanged", () => {
  const baseline = {
    modelProvider: "openai",
    modelApiBase: "https://gateway.example.com/v1",
  };
  assert.equal(
    credentials.inheritTemporaryApiKey(
      baseline,
      { ...baseline, modelName: "model-b" },
      "temporary-key",
    ),
    "temporary-key",
  );
  assert.equal(
    credentials.inheritTemporaryApiKey(
      baseline,
      { ...baseline, modelProvider: "ark" },
      "temporary-key",
    ),
    "",
  );
  assert.equal(
    credentials.inheritTemporaryApiKey(
      baseline,
      { ...baseline, modelApiBase: "https://other.example.com/v1" },
      "temporary-key",
    ),
    "",
  );
});
