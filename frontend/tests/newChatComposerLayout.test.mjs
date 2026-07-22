import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const composerSource = readFileSync(
  new URL("../src/ui/Composer.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const selectorSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatModeSelector.tsx", import.meta.url),
  "utf8",
);
const modeStylesSource = readFileSync(
  new URL("../src/ui/new-chat-modes/new-chat-modes.css", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

test("expands only the new-chat composer into a multiline input", () => {
  assert.match(
    composerSource,
    /className=\{`composer\$\{newChatLayout \? " composer--new-chat" : ""\}`\}/,
  );
  assert.match(composerSource, /rows=\{newChatLayout \? 4 : 1\}/);
  assert.match(
    appSource,
    /newChatLayout=\{!sandboxSession && turns\.length === 0 && skillJob === null\}/,
  );
  assert.match(stylesSource, /\.composer--new-chat \.composer-box[\s\S]*?min-height:/);
  assert.match(stylesSource, /\.composer--new-chat \.comp-input[\s\S]*?min-height:/);
  assert.match(stylesSource, /\.composer--new-chat \.composer-menu-wrap[\s\S]*?bottom: 10px/);
  assert.match(stylesSource, /\.composer--new-chat \.comp-send[\s\S]*?bottom: 10px/);
  assert.match(stylesSource, /\.composer--new-chat \.comp-send \.icon[\s\S]*?width: 20px/);
});

test("places the mode selector beside send and labels Agent mode with the current Agent", () => {
  assert.match(composerSource, /<NewChatModeSelector[\s\S]*?agentName=\{agentName\}/);
  assert.match(selectorSource, /agentName: string/);
  assert.match(
    selectorSource,
    /current\.value === "agent" \? agentName : current\.label/,
  );
  assert.match(selectorSource, /value: "temporary"[\s\S]*?label: "临时会话"/);
  assert.match(selectorSource, /value: "skill-create"[\s\S]*?label: "创建 Skill"/);
  assert.match(
    stylesSource,
    /\.composer--new-chat \.new-chat-mode[\s\S]*?right: 52px[\s\S]*?bottom: 10px/,
  );
  assert.match(
    modeStylesSource,
    /\.composer--new-chat \.new-chat-mode__trigger[\s\S]*?font-size: 15px/,
  );
  assert.match(
    modeStylesSource,
    /\.new-chat-mode__menu\s*\{[\s\S]*?top:\s*calc\(100% \+ 7px\);[\s\S]*?right:\s*0;/,
  );
  assert.match(selectorSource, /<AgentIdentityIcon className="new-chat-mode__agent-icon"/);
  assert.match(selectorSource, /new-chat-mode__temporary-icon[\s\S]*?strokeDasharray/);
});
