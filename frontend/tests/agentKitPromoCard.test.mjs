import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const sidebarSource = read("../src/ui/Sidebar.tsx");
const promoSource = read("../src/ui/AgentKitPromoCard.tsx");
const promoStyles = read("../src/ui/AgentKitPromoCard.css");
const globalStyles = read("../src/styles.css");

const linksBuild = await build({
  entryPoints: [
    fileURLToPath(new URL("../src/ui/agentKitLinks.ts", import.meta.url)),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const linksModuleUrl = `data:text/javascript;base64,${Buffer.from(
  linksBuild.outputFiles[0].contents,
).toString("base64")}`;
const { agentKitLinks } = await import(linksModuleUrl);

test("account menu places issue feedback directly below system information", () => {
  assert.match(
    sidebarSource,
    /account\.systemInfo[\s\S]*?account\.language[\s\S]*?account\.issueFeedback[\s\S]*?account\.logout/,
  );
  assert.match(sidebarSource, /onSelect=\{onIssueFeedback\}/);
  assert.doesNotMatch(sidebarSource, /AgentKitPromoCard/);
  assert.doesNotMatch(sidebarSource, /className=\{`sidebar-feedback/);
});

test("promo links resolve to the matching cloud provider", () => {
  assert.deepEqual(agentKitLinks("volcengine"), {
    console: "https://console.volcengine.com/agentkit",
    docs: "https://www.volcengine.com/docs/86681/1844823",
  });
  assert.deepEqual(agentKitLinks("byteplus"), {
    console: "https://console.byteplus.com/agentkit",
    docs: "https://docs.byteplus.com/en/docs/AgentKit",
  });
});

test("promo renders one AgentKit welcome card with native actions", () => {
  assert.match(
    promoSource,
    /import \{ Button \} from "@openai\/apps-sdk-ui\/components\/Button"/,
  );
  assert.match(promoSource, /import \{ X \} from "@openai\/apps-sdk-ui\/components\/Icon"/);
  assert.match(promoSource, /className=\{`agentkit-promo-card/);
  assert.match(promoSource, /agentKitPromo\.title/);
  assert.match(
    promoSource,
    /agentKitPromo\.description/,
  );
  assert.match(
    promoSource,
    /<a[\s\S]*?href=\{links\.docs\}[\s\S]*?target="_blank"[\s\S]*?agentKitPromo\.docs/,
  );
  assert.match(
    promoSource,
    /<a[\s\S]*?href=\{links\.console\}[\s\S]*?target="_blank"[\s\S]*?agentKitPromo\.console/,
  );
  assert.equal((promoSource.match(/<a/g) ?? []).length, 2);
  assert.doesNotMatch(promoSource, /ButtonLink|ArrowRight/);
  assert.doesNotMatch(promoSource, /ExternalLink/);
  assert.doesNotMatch(promoSource, /AgentKitLogoIcon|agentkit-promo-leading-icon/);
});

test("promo dismissal lasts only for the mounted page session", () => {
  assert.match(promoSource, /const \[dismissed, setDismissed\] = useState\(false\)/);
  assert.match(promoSource, /if \(dismissed\) return null/);
  assert.match(promoSource, /onClick=\{\(\) => setDismissed\(true\)\}/);
  assert.doesNotMatch(promoSource, /localStorage|sessionStorage/);
});

test("promo card uses neutral hover and restrained control motion", () => {
  assert.doesNotMatch(promoStyles, /gradient/);
  assert.match(promoStyles, /font-size:\s*14px/);
  assert.match(promoStyles, /font-size:\s*12px/);
  assert.match(
    promoStyles,
    /\.agentkit-promo-card:hover:not\(\.is-hover-suppressed\)[\s\S]*?background:\s*hsl\(var\(--sidebar-item-hover\)\)/,
  );
  assert.match(
    promoStyles,
    /\.agentkit-promo-close\s*\{[^}]*opacity:\s*0;/s,
  );
  assert.match(
    promoStyles,
    /\.agentkit-promo-close\s*\{[^}]*top:\s*11px;/s,
  );
  assert.match(
    promoStyles,
    /\.agentkit-promo-card:hover:not\(\.is-hover-suppressed\) \.agentkit-promo-close[\s\S]*?\.agentkit-promo-card:focus-within \.agentkit-promo-close[\s\S]*?opacity:\s*1/,
  );
  assert.match(
    promoStyles,
    /\.agentkit-promo-action\s*\{[^}]*flex:\s*0 0 auto;[^}]*font-size:\s*12px;[^}]*text-decoration-line:\s*underline;/s,
  );
  assert.match(
    promoStyles,
    /\.agentkit-promo-action:hover\s*\{[^}]*color:\s*hsl\(var\(--sidebar-foreground\)\);/s,
  );
  assert.match(
    promoStyles,
    /\.agentkit-promo-action:focus-visible\s*\{[^}]*outline:\s*2px solid/s,
  );
  assert.doesNotMatch(promoStyles, /agentkit-promo-arrow-icon/);
  assert.match(
    promoStyles,
    /\.sidebar\.is-collapsed \.agentkit-promo-card\s*\{[^}]*display:\s*none;/s,
  );
  assert.match(promoStyles, /prefers-reduced-motion:\s*reduce/);
  assert.doesNotMatch(promoStyles, /@keyframes/);
  assert.doesNotMatch(globalStyles, /\.sidebar \.agentkit-promo/);
});

test("promo actions clear the current hover presentation after click", () => {
  assert.match(
    promoSource,
    /const \[hoverSuppressed, setHoverSuppressed\] = useState\(false\)/,
  );
  assert.match(
    promoSource,
    /handleActionClick[\s\S]*?currentTarget\.blur\(\)[\s\S]*?setHoverSuppressed\(true\)/,
  );
  assert.equal((promoSource.match(/onClick=\{handleActionClick\}/g) ?? []).length, 2);
  assert.match(promoSource, /onMouseLeave=\{\(\) => setHoverSuppressed\(false\)\}/);
});
