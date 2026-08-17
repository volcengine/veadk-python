import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function source(path) {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

const appSource = source("../src/App.tsx");
const composerSource = source("../src/ui/Composer.tsx");
const sandboxComposerSource = source("../src/ui/SandboxComposer.tsx");
const composerIconsSource = source("../src/ui/icons/ComposerIcons.tsx");
const sandboxIconsSource = source("../src/ui/icons/SandboxControlIcons.tsx");
const stylesSource = source("../src/styles.css");
const readmeSource = source("../README.md");

function between(sourceText, start, end) {
  const startIndex = sourceText.indexOf(start);
  assert.notEqual(startIndex, -1, `missing start marker: ${start}`);
  const endIndex = sourceText.indexOf(end, startIndex + start.length);
  assert.notEqual(endIndex, -1, `missing end marker: ${end}`);
  return sourceText.slice(startIndex, endIndex);
}

test("aborts only the active standard conversation stream", () => {
  const sendSource = between(
    appSource,
    "  async function send(",
    "  function onAction(",
  );
  assert.match(
    appSource,
    /function stopCurrentGeneration\(\)[\s\S]*?streamAbortsRef\.current\.get\(sessionId\)\?\.abort\(\)/,
  );
  assert.match(
    appSource,
    /<Composer[\s\S]*?onStop=\{busy \? stopCurrentGeneration : undefined\}/,
  );
  assert.match(
    sendSource,
    /\(e as Error\)\?\.name !== "AbortError"[\s\S]*?!ctrl\.signal\.aborted/,
  );
  assert.match(
    sendSource,
    /if \(trackRuntimeMessage && ctrl\.signal\.aborted\) \{[\s\S]*?messageOperation\?\.fail\(\{[\s\S]*?errorKind: "abort"[\s\S]*?\}\);[\s\S]*?\} else if \(trackRuntimeMessage\) \{[\s\S]*?messageOperation\?\.succeed/,
  );
  assert.match(
    sendSource,
    /finally \{[\s\S]*?streamAbortsRef\.current\.get\(sid\) === ctrl[\s\S]*?setStreaming\(sid, false\)[\s\S]*?finishStreamPresentation\(sid\)/,
  );

  const finallyIndex = sendSource.lastIndexOf("    } finally {");
  const abortCatchIndex = sendSource.lastIndexOf(
    "    } catch (e) {",
    finallyIndex,
  );
  assert.notEqual(abortCatchIndex, -1);
  assert.notEqual(finallyIndex, -1);
  const abortCatch = sendSource.slice(abortCatchIndex, finallyIndex);
  assert.doesNotMatch(abortCatch, /setTurnsFor\(|filter\(|setInput\(/);
});

test("aborts only an active Sandbox agent response", () => {
  const sendSource = between(
    appSource,
    "  async function sendSandboxMessage(",
    "  async function submitSandboxInput(",
  );
  assert.match(
    appSource,
    /function stopSandboxGeneration\(\)[\s\S]*?sandboxMessageAbortRef\.current\?\.abort\(\)[\s\S]*?sandboxClient[\s\S]*?\.interruptSession\(activeSessionId\)/,
  );
  assert.match(
    appSource,
    /<SandboxComposer[\s\S]*?onStop=\{sandboxBusy \? stopSandboxGeneration : undefined\}/,
  );
  assert.match(
    appSource,
    /if \(\(messageError as Error\)\?\.name === "AbortError"\) \{\s*return;\s*\}/,
  );
  assert.ok(
    (sendSource.match(/controller\.signal\.aborted \|\|\s*sandboxMessageAbortRef\.current !== controller/g) ?? [])
      .length >= 5,
    "all Sandbox stream callbacks and the final response ignore work after abort",
  );
  assert.match(
    sendSource,
    /controller\.signal\.aborted \|\|[\s\S]*?sandboxMessageAbortRef\.current !== controller[\s\S]*?operation\.fail\(\{[\s\S]*?errorKind: "abort"[\s\S]*?\}\);\s*return;\s*\}[\s\S]*?operation\.succeed/,
  );
  assert.match(
    sendSource,
    /catch \(messageError\) \{[\s\S]*?operation\.fail\(\{[\s\S]*?classifyTelemetryError\(messageError\)[\s\S]*?\}\);[\s\S]*?if \(\(messageError as Error\)\?\.name === "AbortError"\) \{\s*return;\s*\}/,
  );
  assert.match(
    sendSource,
    /finally \{\s*if \(sandboxMessageAbortRef\.current === controller\) \{[\s\S]*?sandboxMessageAbortRef\.current = null[\s\S]*?setSandboxBusy\(false\)[\s\S]*?busy: false/,
  );

  const abortBranch = between(
    sendSource,
    '      if ((messageError as Error)?.name === "AbortError") {',
    "      if (sandboxMessageAbortRef.current !== controller) {",
  );
  assert.doesNotMatch(
    abortBranch,
    /setSandboxTurns\(|filter\(|setInput\(|operation\.succeed|setError\(/,
  );
});

test("standard Composer turns its enabled send control into an accessible stop control", () => {
  assert.match(composerSource, /onStop\?: \(\) => void/);
  assert.match(composerSource, /const canStop = busy && Boolean\(onStop\)/);
  assert.match(composerSource, /disabled=\{canStop \? false : !canSend\}/);
  assert.match(composerSource, /onClick=\{canStop \? onStop : submitComposer\}/);
  assert.match(composerSource, /aria-label=\{\s*canStop\s*\? "停止生成"/);
  assert.match(composerSource, /canStop \? \(\s*<ComposerStopIcon/);
  assert.match(composerSource, /<ComposerSendIcon/);
  const importSection = composerSource.slice(
    0,
    composerSource.indexOf("interface CompletionTrigger"),
  );
  assert.doesNotMatch(importSection, /\bArrowUp\b/);
});

test("Sandbox Composer exposes the same stop state without stopping unrelated commands", () => {
  assert.match(sandboxComposerSource, /onStop\?: \(\) => void/);
  assert.match(sandboxComposerSource, /const canStop = busy && Boolean\(onStop\)/);
  assert.match(sandboxComposerSource, /disabled=\{canStop \? false : !canSend\}/);
  assert.match(sandboxComposerSource, /onClick=\{canStop \? onStop/);
  assert.match(sandboxComposerSource, /aria-label=\{canStop \? "停止生成" : "发送"\}/);
  assert.match(sandboxComposerSource, /canStop \? \(\s*<SandboxStopIcon/);
  assert.match(sandboxComposerSource, /busy \? \(\s*<SandboxSpinnerIcon/);
});

test("composer stop icons are repository-owned decorative SVGs", () => {
  assert.match(composerIconsSource, /export function ComposerSendIcon/);
  assert.match(composerIconsSource, /export function ComposerStopIcon/);
  assert.match(composerIconsSource, /aria-hidden="true"/);
  assert.match(composerIconsSource, /<rect[^>]*x="6"[^>]*y="6"[^>]*width="12"[^>]*height="12"/);
  assert.match(sandboxIconsSource, /export function SandboxStopIcon/);
  assert.match(
    stylesSource,
    /\.comp-send \.icon\s*\{[^}]*width:\s*20px;[^}]*height:\s*20px;/,
  );
  assert.match(stylesSource, /\.comp-send:focus-visible\s*\{[^}]*outline:\s*2px solid/);
  assert.match(readmeSource, /stop control that cancels only the active\s*response/);
});
