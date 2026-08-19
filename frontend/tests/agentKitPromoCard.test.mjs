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
    /系统信息[\s\S]*?问题反馈[\s\S]*?退出登录/,
  );
  assert.match(sidebarSource, /onIssueFeedback\(\)/);
  assert.match(sidebarSource, /<AgentKitPromoCard cloudProvider=\{cloudProvider\}/);
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

test("promo renders two direct external links", () => {
  assert.match(promoSource, /className="agentkit-promo-stack"/);
  assert.match(promoSource, /前往 AgentKit 控制台/);
  assert.match(promoSource, /查看 AgentKit 官方文档/);
  assert.match(promoSource, /target="_blank"/);
  assert.match(promoSource, /rel="noreferrer"/);
  assert.match(promoSource, /在新窗口打开/);
  assert.doesNotMatch(promoSource, /AgentKitLogoIcon/);
  assert.equal((promoSource.match(/<PromoLink/g) ?? []).length, 2);
  assert.equal((promoSource.match(/viewBox="0 0 20 20"/g) ?? []).length, 1);
});

test("promo card uses a flat static gradient treatment and collapsed layout", () => {
  assert.ok((promoStyles.match(/linear-gradient/g) ?? []).length >= 6);
  assert.doesNotMatch(promoStyles, /radial-gradient/);
  assert.match(promoStyles, /height:\s*38px/);
  assert.match(promoStyles, /height:\s*46px/);
  assert.match(
    promoStyles,
    /\.agentkit-promo-stack:hover[\s\S]*?height:\s*82px/,
  );
  assert.match(
    promoStyles,
    /\.agentkit-promo-stack:hover \.agentkit-promo-link\.is-docs[\s\S]*?bottom:\s*44px/,
  );
  assert.match(promoStyles, /border:\s*0/);
  assert.match(
    promoStyles,
    /\.agentkit-promo-link:hover \.agentkit-promo-external-icon/,
  );
  assert.match(
    promoStyles,
    /\.sidebar\.is-collapsed \.agentkit-promo-stack\s*\{[^}]*display:\s*none;/s,
  );
  assert.match(promoStyles, /prefers-reduced-motion:\s*reduce/);
  assert.doesNotMatch(promoStyles, /translateY/);
  assert.doesNotMatch(promoStyles, /@keyframes/);
});
