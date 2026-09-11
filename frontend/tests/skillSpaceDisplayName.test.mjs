import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

const result = await build({
  entryPoints: [fileURLToPath(new URL("../src/create/skills/skillspace.ts", import.meta.url))],
  bundle: true, platform: "node", format: "cjs", write: false,
  plugins: [{ name: "display-name-test", setup(builder) {
    const mocks = {
      "../i18n": "export const createT = key => key;",
      "../../adk/skills": "export const skillApiErrorFromResponse = () => new Error('request failed');",
      "../../adk/i18n": "export const withLocaleHeaders = headers => headers;",
      "./i18n": "export const adkT = key => key; export const withLocaleHeaders = headers => headers;",
    };
    builder.onResolve({filter: /.*/}, ({path}) => path in mocks ? {path, namespace: "mock"} : undefined);
    builder.onLoad({filter: /.*/, namespace: "mock"}, ({path}) => ({contents: mocks[path]}));
  }}],
});
const module = {exports: {}};
Function("require", "module", "exports", result.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const {getSkillSpaceDisplayName, toHit} = module.exports;

test("SkillSpace lists and details send the current local identity and gateway parameters", async (t) => {
  const saved = new Map();
  const globals = ["window", "sessionStorage", "localStorage"];
  const previous = globals.map((key) => Object.getOwnPropertyDescriptor(globalThis, key));
  const storage = {getItem: key => saved.get(key) ?? null, setItem: (key, value) => saved.set(key, value)};
  globalThis.sessionStorage = storage;
  globalThis.localStorage = storage;
  globalThis.window = {location: new URL("http://localhost/?gateway=fake-test-value"), history: {replaceState() {}}};
  t.after(() => globals.forEach((key, index) => {
    if (previous[index]) Object.defineProperty(globalThis, key, previous[index]);
    else delete globalThis[key];
  }));
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, init) => {
    requests.push({url, headers: new Headers(init.headers)});
    return new Response(JSON.stringify({items: []}), {headers: {"Content-Type": "application/json"}});
  });
  for (const user of ["test", "developer", null]) {
    saved.delete("veadk_local_user");
    saved.delete("veadk_local_user_tab");
    if (user) saved.set("veadk_local_user_tab", user);
    for (const region of ["cn-beijing", "ap-southeast-1"]) {
      await module.exports.listSkillSpacesPage({region, page: 1, pageSize: 12});
      await module.exports.listSkillsInSpacePage("space-1", {region, page: 1, pageSize: 12});
      await module.exports.getSkillDetail("space-1", "skill-1", "v1", region);
      for (const request of requests.splice(0)) {
        assert.equal(request.headers.get("X-VeADK-Local-User"), user);
        assert.equal(request.headers.get("Accept"), "application/json");
        const url = new URL(request.url, "http://localhost");
        assert.equal(url.searchParams.get("region"), region);
        assert.equal(url.searchParams.get("gateway"), "fake-test-value");
      }
    }
  }
});

test("display labels prefer the user name and fall back for old spaces", () => {
  assert.equal(getSkillSpaceDisplayName({name: "studio_space_123", displayName: "中文名称"}), "中文名称");
  assert.equal(getSkillSpaceDisplayName({name: "legacy_space"}), "legacy_space");
  assert.equal(getSkillSpaceDisplayName({name: "legacy_space", displayName: "  "}), "legacy_space");
  assert.equal(getSkillSpaceDisplayName(null), "");
});

test("selecting a labelled SkillSpace preserves the cloud name for lookup and export", () => {
  const hit = toHit(
    {id: "space-1", name: "studio_space_123", displayName: "中文名称", region: "cn-beijing"},
    {skillId: "skill-1", skillName: "writer", version: "1.0.0", skillDescription: "Writing skills"},
  );
  assert.equal(hit.skillSpaceName, "studio_space_123");
  assert.equal(hit.skillSpaceId, "space-1");
  assert.equal(hit.skillSpaceRegion, "cn-beijing");
});
