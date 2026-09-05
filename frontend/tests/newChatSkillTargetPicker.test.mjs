import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const controlsSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatSkillControls.tsx", import.meta.url),
  "utf8",
);
const pickerSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatSkillTargetPicker.tsx", import.meta.url),
  "utf8",
);
const pickerStyles = readFileSync(
  new URL("../src/ui/new-chat-modes/new-chat-skill-target-picker.css", import.meta.url),
  "utf8",
);
const sharedPickerStyles = readFileSync(
  new URL("../src/ui/new-chat-modes/new-chat-agent-picker.css", import.meta.url),
  "utf8",
);

test("renders Skill Space and Skill as one two-level picker", () => {
  assert.match(controlsSource, /<NewChatSkillTargetPicker/);
  assert.doesNotMatch(
    controlsSource,
    /action === "create"[\s\S]*?: \([\s\S]*?label="空间"[\s\S]*?label="Skill"/,
  );
  assert.match(pickerSource, /aria-label=\{t\("skill\.spaceAria"\)\}/);
  assert.match(pickerSource, /aria-label=\{t\("skill\.skillList", \{ space: activeSpaceLabel \}\)\}/);
  assert.match(pickerSource, /aria-haspopup="menu"/);
  assert.match(pickerSource, /role="menuitem"/);
  assert.match(pickerSource, /role="option"/);
  assert.match(pickerSource, /new-chat-skill-target-picker__submenu/);
  assert.match(sharedPickerStyles, /\.new-chat-agent-picker__submenu/);
});

test("loads spaces first and Skills for the active Space without stale updates", () => {
  assert.match(controlsSource, /listSkillSpaces\(\)/);
  assert.match(
    controlsSource,
    /listSkillsInSpace\(activeSpace\.id, activeSpace\.region\)/,
  );
  assert.match(controlsSource, /let cancelled = false/);
  assert.match(controlsSource, /if \(!cancelled\) setSkills\(items\)/);
  assert.match(pickerSource, /onActivateSpace\(nextSpace\.id\)/);
  assert.match(pickerSource, /onSelect\(activeSpace, skill\)/);
  assert.match(pickerSource, /selectedSkillLabel \|\| t\("skill\.select"\)/);
});

test("supports hover, click, keyboard navigation, and focus return", () => {
  assert.match(pickerSource, /HOVER_OPEN_DELAY_MS = 120/);
  assert.match(pickerSource, /HOVER_CLOSE_DELAY_MS = 180/);
  assert.match(pickerSource, /onPointerEnter/);
  assert.match(pickerSource, /onPointerLeave/);
  assert.match(pickerSource, /event\.key === "ArrowDown"/);
  assert.match(pickerSource, /event\.key === "ArrowUp"/);
  assert.match(pickerSource, /event\.key === "ArrowRight"/);
  assert.match(pickerSource, /event\.key === "ArrowLeft"/);
  assert.match(pickerSource, /event\.key === "Enter"/);
  assert.match(pickerSource, /event\.key === "Escape"/);
  assert.match(pickerSource, /triggerRef\.current\?\.focus\(\)/);
  assert.match(sharedPickerStyles, /:focus-visible/);
});

test("keeps loading, empty, error, retry, and reduced-motion states local", () => {
  assert.match(pickerSource, /new-chat-skill-target-picker__spinner/);
  assert.match(pickerSource, /role="status"/);
  assert.match(pickerSource, /role="alert"/);
  assert.match(pickerSource, /t\("skill\.reload"\)/);
  assert.match(pickerSource, /t\("skill\.emptySpaces"\)/);
  assert.match(pickerSource, /t\("skill\.emptySkills"\)/);
  assert.match(
    pickerStyles,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?animation:\s*none/,
  );
});

test("fits both picker levels inside the available viewport height", () => {
  assert.match(pickerSource, /getBoundingClientRect\(\)/);
  assert.match(pickerSource, /window\.innerHeight/);
  assert.match(pickerSource, /availableBelow/);
  assert.match(pickerSource, /availableAbove/);
  assert.match(pickerSource, /new-chat-skill-menu-max-height/);
  assert.match(pickerStyles, /\.new-chat-skill-target-picker__menus\.is-above/);
  assert.match(
    pickerStyles,
    /max-height:\s*var\(--new-chat-skill-menu-max-height, 286px\)/,
  );
  assert.match(pickerStyles, /overflow-y:\s*auto/);
});
