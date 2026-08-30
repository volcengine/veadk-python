import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

test("uses the Apps SDK loading indicator in the session action slot", () => {
  assert.match(
    sidebarSource,
    /import \{ LoadingIndicator \} from "@openai\/apps-sdk-ui\/components\/Indicator"/,
  );
  assert.match(
    sidebarSource,
    /className="history-action-slot"[\s\S]*?className="history-streaming-indicator"[\s\S]*?size=\{12\}[\s\S]*?aria-label="正在生成"[\s\S]*?className="history-more"/,
  );
  assert.doesNotMatch(sidebarSource, /className="history-streaming"/);
  assert.doesNotMatch(stylesSource, /#22c55e|history-pulse/);
  assert.match(
    stylesSource,
    /\.history-item:hover \.history-streaming-indicator,[\s\S]*?opacity:\s*0;/,
  );
  assert.match(
    stylesSource,
    /\.history-action-slot:focus-within \.history-streaming-indicator/,
  );
  assert.doesNotMatch(
    stylesSource,
    /\.history-item:focus-within \.history-streaming-indicator/,
  );
});

test("fades overflowing session titles on both scroll edges", () => {
  assert.match(sidebarSource, /function ScrollableHistoryTitle/);
  assert.match(sidebarSource, /left:\s*element\.scrollLeft > 1/);
  assert.match(
    sidebarSource,
    /right:\s*element\.scrollLeft \+ element\.clientWidth < element\.scrollWidth - 1/,
  );
  assert.match(sidebarSource, /onScroll=\{updateFadeEdges\}/);
  assert.match(stylesSource, /\.history-title\.has-left-fade/);
  assert.match(stylesSource, /\.history-title\.has-right-fade/);
  assert.match(stylesSource, /mask-image:\s*linear-gradient/);
  assert.match(
    stylesSource,
    /\.history-item:hover \.history-title,[\s\S]*?overflow-x:\s*auto;/,
  );
  assert.doesNotMatch(stylesSource, /\.history-title\s*\{[^}]*text-overflow:\s*ellipsis/);
});
