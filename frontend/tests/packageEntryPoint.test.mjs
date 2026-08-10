import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";

const result = await build({
  entryPoints: [
    fileURLToPath(
      new URL("../src/create/packageEntryPoint.ts", import.meta.url),
    ),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(result.outputFiles[0].contents).toString("base64")}`;
const { listPackageEntryPoints, resolvePackageEntryPoint } = await import(moduleUrl);

function files(...paths) {
  return paths.map((path) => ({ path, content: "" }));
}

test("resolves supported code package entry points in compatibility order", () => {
  assert.deepEqual(resolvePackageEntryPoint(files("app.py")), {
    entryPoint: "app.py",
    source: "convention",
  });
  assert.deepEqual(
    resolvePackageEntryPoint(files("agentkit_app.py")),
    { entryPoint: "agentkit_app.py", source: "convention" },
  );
  assert.deepEqual(resolvePackageEntryPoint(files("main.py")), {
    entryPoint: "main.py",
    source: "convention",
  });
  assert.deepEqual(
    resolvePackageEntryPoint(files("main.py", "agentkit_app.py", "app.py")),
    { entryPoint: "app.py", source: "convention" },
  );
});

test("uses a migration manifest before filename conventions", () => {
  const project = files("app.py", "agentkit_app.py");
  project.push({
    path: "migration-result.json",
    content: JSON.stringify({ entrypoint: "agentkit_app.py" }),
  });

  assert.deepEqual(resolvePackageEntryPoint(project), {
    entryPoint: "agentkit_app.py",
    source: "manifest",
  });
});

test("normalizes manifest whitespace without changing the selected file path", () => {
  const project = files("nested/serve.py");
  project.push({
    path: "migration-result.json",
    content: JSON.stringify({ entrypoint: "  nested/serve.py  " }),
  });

  assert.deepEqual(resolvePackageEntryPoint(project), {
    entryPoint: "nested/serve.py",
    source: "manifest",
  });
});

test("auto-selects one custom Python entry and requires input for ambiguity", () => {
  assert.deepEqual(resolvePackageEntryPoint(files("src/serve.py", "README.md")), {
    entryPoint: "src/serve.py",
    source: "single",
  });
  assert.deepEqual(
    resolvePackageEntryPoint(files("src/serve.py", "worker.py")),
    { entryPoint: null, source: "ambiguous" },
  );
  assert.deepEqual(
    listPackageEntryPoints(
      files(
        "worker.py",
        "src/serve.py",
        "app.py",
        "nested folder/agent entry.py",
        "src/__init__.py",
      ),
    ),
    ["app.py", "nested folder/agent entry.py", "src/serve.py", "worker.py"],
  );
});

test("rejects missing Python files and invalid manifest entry points", () => {
  assert.throws(
    () => resolvePackageEntryPoint(files("README.md")),
    /至少包含一个可执行的 Python 文件/,
  );
  assert.throws(
    () =>
      resolvePackageEntryPoint([
        ...files("app.py"),
        {
          path: "migration-result.json",
          content: JSON.stringify({ entrypoint: "../app.py" }),
        },
      ]),
    /manifest 中的 entrypoint 不是安全的 Python 相对路径/,
  );
  assert.throws(
    () =>
      resolvePackageEntryPoint([
        ...files("app.py"),
        {
          path: "migration-result.json",
          content: JSON.stringify({ entrypoint: "missing.py" }),
        },
      ]),
    /manifest 指定的启动入口不存在/,
  );
  assert.throws(
    () =>
      resolvePackageEntryPoint([
        ...files("app.py"),
        {
          path: "migration-result.json",
          content: JSON.stringify({ entrypoint: "unsafe\nname.py" }),
        },
      ]),
    /manifest 中的 entrypoint 不是安全的 Python 相对路径/,
  );
  assert.throws(
    () =>
      resolvePackageEntryPoint([
        ...files("app.py"),
        {
          path: "migration-result.json",
          content: JSON.stringify({ entrypoint: 1 }),
        },
      ]),
    /必须声明字符串类型的 entrypoint/,
  );
});
