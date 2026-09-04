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

test("automatically reveals overflowing session titles on hover and focus", () => {
  assert.match(sidebarSource, /function ScrollableHistoryTitle/);
  assert.match(
    sidebarSource,
    /content\.scrollWidth - viewport\.clientWidth/,
  );
  assert.match(sidebarSource, /className={`history-title\$\{overflowDistance > 0 \? " is-overflowing" : ""\}`}/);
  assert.match(sidebarSource, /"--history-title-translate": `-\$\{overflowDistance\}px`/);
  assert.match(stylesSource, /@keyframes history-title-marquee/);
  assert.match(
    stylesSource,
    /\.history-item:hover \.history-title\.is-overflowing \.history-title-text,[\s\S]*?\.history-item:focus-within \.history-title\.is-overflowing \.history-title-text[\s\S]*?animation:\s*history-title-marquee/,
  );
  assert.match(stylesSource, /mask-image:\s*linear-gradient/);
  assert.match(
    stylesSource,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.history-title-text[\s\S]*?animation:\s*none;/,
  );
  assert.doesNotMatch(stylesSource, /\.history-title\s*\{[^}]*text-overflow:\s*ellipsis/);
});
