import assert from "node:assert/strict";
import test from "node:test";

import { extractJavaScriptImports } from "../scripts/assetImports.mjs";

test("ignores bundled code examples, comments, regexes, and ordinary import methods", () => {
  const source = [
    `const prettierExample = 'from "./module"';`,
    `const quotedExample = "import('./string-only.js')";`,
    'const templateExample = `export * from "./template-only.js"`;',
    String.raw`const regexExample = /import\("\.\/regex-only.js"\)/;`,
    '// import "./line-comment.js";',
    '/* export { sample } from "./block-comment.js"; */',
    'loader.import("./method-call.js");',
    'const from = "./variable.js";',
    'export { from };',
  ].join("\n");

  assert.deepEqual(extractJavaScriptImports(source), []);
});

test("extracts static imports and re-exports, including side-effect imports", () => {
  assert.deepEqual(extractJavaScriptImports(`
    import "./side-effect.js";
    import value from "./default.js";
    import { named as other } from "./named.js";
    import * as namespace from "./namespace.js";
    export { value } from "./re-export.js";
    export * from "./all.js";
    export * as nested from "./namespace-export.js";
    import data from "./data.json" with { type: "json" };
  `), [
    "./side-effect.js", "./default.js", "./named.js", "./namespace.js",
    "./re-export.js", "./all.js", "./namespace-export.js", "./data.json",
  ]);
});

test("extracts literal dynamic imports inside callbacks with comments or options", () => {
  const source = [
    'const lazy = () => import(/* preload */ "../chunk.js?version=1#part");',
    'function load() { return import("./data.json", { with: { type: "json" } }); }',
    'const fixedTemplate = () => import(`./fixed.js`);',
    'const unknown = path => import(path);',
    'const interpolated = name => import(`./${name}.js`);',
    'const meta = import.meta.url;',
  ].join("\n");
  assert.deepEqual(extractJavaScriptImports(source), [
    "../chunk.js?version=1#part", "./data.json", "./fixed.js",
  ]);
});

test("decodes escaped specifiers and handles minified imports separated by comments", () => {
  const source = String.raw`import{a}from/* generated */".\u002fsource.js";export{a}from"./export.js";const load=()=>import(/* lazy */'./chunk.js');`;
  assert.deepEqual(extractJavaScriptImports(source), [
    "./source.js", "./export.js", "./chunk.js",
  ]);
});
