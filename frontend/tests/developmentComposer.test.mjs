import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import test from "node:test";
import { JSDOM } from "jsdom";
const require = createRequire(import.meta.url);

test("intelligent composer supports IME, steer, independent stop, error and resume", async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: "http://localhost" });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.localStorage = dom.window.localStorage;
  globalThis.sessionStorage = dom.window.sessionStorage;
  const result = await build({
    entryPoints: [
      fileURLToPath(new URL("../src/ui/SandboxComposer.tsx", import.meta.url)),
    ],
    bundle: true,
    platform: "node",
    format: "cjs",
    write: false,
    jsx: "automatic",
    external: ["react", "react-dom", "react-dom/*"],
    plugins: [
      {
        name: "translations",
        setup(b) {
          b.onResolve({ filter: /^react-i18next$/ }, () => ({
            path: "translations",
            namespace: "mock",
          }));
          b.onLoad({ filter: /.*/, namespace: "mock" }, () => ({
            contents:
              'export const useTranslation=()=>({t:key=>key,i18n:{language:"en-US"}}); export const initReactI18next={type:"3rdParty",init(){}};',
            loader: "js",
          }));
          b.onLoad({ filter: /\.css$/ }, () => ({
            contents: "",
            loader: "js",
          }));
        },
      },
    ],
  });
  const module = { exports: {} };
  Function(
    "require",
    "module",
    "exports",
    result.outputFiles[0].text,
  )(require, module, module.exports);
  const React = require("react"),
    { act } = React;
  const root = require("react-dom/client").createRoot(
    document.getElementById("root"),
  );
  const sent = [];
  let stopped = 0,
    resumed = 0;
  const noop = () => {};
  const props = {
    appName: "",
    value: "补充要求",
    onChange: noop,
    onSubmit: (v) => sent.push(v),
    onStop: () => stopped++,
    disabled: false,
    busy: true,
    attachments: [],
    onAddFiles: noop,
    onRemoveAttachment: noop,
    actions: {
      onOpenTerminal: noop,
      onOpenBrowser: noop,
      onOpenPermissions: noop,
      onOpenWorkspace: noop,
      workspaceLocked: true,
      settingsBusy: false,
      uploadBusy: false,
    },
    models: [],
    modelsLoading: false,
    modelsLoaded: true,
    onRequestModels: noop,
    skills: [],
    skillsLoading: false,
    skillsLoaded: true,
    selectedSkills: [],
    onRequestSkills: noop,
    onSelectedSkillsChange: noop,
    textOnly: true,
    allowSteer: true,
  };
  const render = (patch) =>
    act(async () =>
      root.render(
        React.createElement(module.exports.SandboxComposer, {
          ...props,
          ...patch,
        }),
      ),
    );
  const button = (name) =>
    document.querySelector(`button[aria-label="${name}"]`);
  try {
    await render({});
    const textarea = document.querySelector("textarea");
    assert.equal(textarea.disabled, false);
    assert.equal(button("composer.steer").disabled, false);
    await act(async () =>
      textarea.dispatchEvent(
        new dom.window.KeyboardEvent("keydown", {
          key: "Enter",
          isComposing: true,
          bubbles: true,
        }),
      ),
    );
    assert.deepEqual(sent, []);
    await act(async () =>
      textarea.dispatchEvent(
        new dom.window.KeyboardEvent("keydown", {
          key: "Enter",
          bubbles: true,
        }),
      ),
    );
    assert.deepEqual(sent, ["补充要求"]);
    await render({ sending: true });
    assert.equal(button("composer.steer").disabled, true);
    assert.equal(button("composer.stop").disabled, false);
    await act(async () => button("composer.stop").click());
    assert.equal(stopped, 1);
    await render({ stopping: true });
    assert.equal(button("composer.stopping").disabled, true);
    assert.equal(button("composer.steer").disabled, true);
    await render({
      busy: false,
      errorText: "temporary problem",
      onResume: () => resumed++,
    });
    assert.ok(document.body.textContent.includes("temporary problem"));
    await act(async () =>
      [...document.querySelectorAll("button")]
        .find((x) => x.textContent === "composer.resume")
        .click(),
    );
    assert.equal(resumed, 1);
  } finally {
    await act(async () => root.unmount());
    dom.window.close();
  }
});
