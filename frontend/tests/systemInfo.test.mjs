import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

const read = (path) =>
  readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

const appSource = read("App.tsx");
const clientSource = read("adk/client.ts");
const sidebarSource = read("ui/Sidebar.tsx");
const systemInfoSource = read("ui/SystemInfo.tsx");
const systemInfoStylesSource = read("ui/SystemInfo.css");
const pageBackButtonSource = read("ui/PageBackButton.tsx");
const pageBackButtonStylesSource = read("ui/PageBackButton.css");

const linksBuild = await build({
  entryPoints: [
    fileURLToPath(
      new URL("../src/ui/systemInfoConsoleLinks.ts", import.meta.url),
    ),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
});
const linksModuleUrl = `data:text/javascript;base64,${Buffer.from(linksBuild.outputFiles[0].contents).toString("base64")}`;
const {
  identityUserPoolConsoleUrl,
  sandboxToolConsoleUrl,
  tosConsoleUrl,
} = await import(linksModuleUrl);

test("account menu navigates to the system information page", () => {
  assert.match(clientSource, /version: string;/);
  assert.match(appSource, /setVersion\(cfg\.version\)/);
  assert.match(
    appSource,
    /<SystemInfo[\s\S]*?version=\{version\}[\s\S]*?localMode=\{agentsSource === "local"\}[\s\S]*?role=\{access\?\.role \?\? "user"\}/,
  );
  assert.match(appSource, /provider=\{cloudProvider\}/);
  assert.match(
    appSource,
    /region=\{studioRegion \|\| defaultCloudRegion\(cloudProvider\)\}/,
  );
  assert.match(appSource, /const \[pageStack, setPageStack\] = useState<StudioPageStackEntry\[\]>\(\[\]\)/);
  assert.match(appSource, /page: "system-info"[\s\S]*?returnTo: currentStudioPage/);
  assert.match(appSource, /<SystemInfo[\s\S]*?onBack=\{closeSystemInfoPage\}/);
  assert.match(
    sidebarSource,
    /系统信息[\s\S]*?退出登录/,
    "system information should appear above logout",
  );
  assert.match(sidebarSource, /onSystemInfo\(\)/);
  assert.doesNotMatch(sidebarSource, /role="dialog"/);
  assert.doesNotMatch(sidebarSource, /createPortal/);
});

test("system information returns to the page recorded beneath it", () => {
  assert.match(systemInfoSource, /onBack: \(\) => void/);
  assert.match(
    systemInfoSource,
    /<PageBackButton[\s\S]*?label="返回上一页"[\s\S]*?onClick=\{onBack\}/,
  );
  assert.match(
    appSource,
    /onSystemInfo=\{\(\) => requestIntelligentNavigation\(\(\) => \{[\s\S]*?pushStudioPage\(\{[\s\S]*?page: "system-info"[\s\S]*?returnTo: currentStudioPage/,
  );
  assert.doesNotMatch(
    appSource,
    /onSystemInfo=\{\(\) => requestIntelligentNavigation\(\(\) => \{[\s\S]*?setSkillCenter\(false\)[\s\S]*?setSystemInfo\(true\)/,
  );
});

test("shared page back button is an accessible fixed-size icon control", () => {
  assert.match(pageBackButtonSource, /type="button"/);
  assert.match(pageBackButtonSource, /aria-label=\{label\}/);
  assert.match(pageBackButtonSource, /title=\{label\}/);
  assert.match(pageBackButtonSource, /aria-hidden="true"/);
  assert.match(
    pageBackButtonStylesSource,
    /\.page-back-button\s*\{[^}]*width:\s*32px;[^}]*height:\s*32px;[^}]*display:\s*grid;[^}]*place-items:\s*center;/s,
  );
  assert.match(pageBackButtonStylesSource, /\.page-back-button:focus-visible/);
});

test("builds direct console links for Volcengine and BytePlus resources", () => {
  assert.equal(
    tosConsoleUrl(
      "volcengine",
      "veadk-studio-2107625663.tos-cn-beijing.volces.com",
    ),
    "https://console.volcengine.com/tos/bucket/setting?id=veadk-studio-2107625663&region=cn-beijing&type=objects",
  );
  assert.equal(
    tosConsoleUrl(
      "byteplus",
      "veadk-studio-3001037806.tos-ap-southeast-1.bytepluses.com",
    ),
    "https://console.byteplus.com/tos/bucket/setting?id=veadk-studio-3001037806&region=ap-southeast-1&type=objects",
  );
  assert.equal(
    sandboxToolConsoleUrl("volcengine", "cn-beijing", "t-volc"),
    "https://console.volcengine.com/agentkit/region:agentkit+cn-beijing/builtintools/t-volc/detail",
  );
  assert.equal(
    sandboxToolConsoleUrl("byteplus", "ap-southeast-1", "t-byteplus"),
    "https://console.byteplus.com/agentkit/region:agentkit+ap-southeast-1/builtintools/t-byteplus/detail",
  );
  assert.equal(
    identityUserPoolConsoleUrl("volcengine", "cn-beijing", "pool-volc"),
    "https://console.volcengine.com/identity/region:identity+cn-beijing/user-pools/pool-volc/info",
  );
  assert.equal(
    identityUserPoolConsoleUrl(
      "byteplus",
      "ap-southeast-1",
      "pool-byteplus",
    ),
    "https://console.byteplus.com/identity/region:identity+ap-southeast-1/user-pools/pool-byteplus/info",
  );
  assert.equal(tosConsoleUrl("volcengine", ""), null);
  assert.equal(sandboxToolConsoleUrl("volcengine", "cn-beijing", ""), null);
  assert.equal(
    identityUserPoolConsoleUrl("byteplus", "ap-southeast-1", ""),
    null,
  );
});

test("resource text and its console icon form one compact external link", () => {
  assert.match(systemInfoSource, /className="system-info-resource-link"/);
  assert.match(systemInfoSource, /target="_blank"/);
  assert.match(systemInfoSource, /rel="noreferrer"/);
  assert.match(systemInfoSource, /aria-label=\{label\}/);
  assert.match(
    systemInfoStylesSource,
    /\.system-info-resource-link\s*\{[^}]*width:\s*fit-content;[^}]*display:\s*inline-flex;[^}]*cursor:\s*pointer;/s,
  );
  assert.match(systemInfoStylesSource, /text-decoration-style:\s*dashed/);
  assert.match(
    systemInfoStylesSource,
    /\.system-info-resource-link svg\s*\{[^}]*opacity:\s*0;/s,
  );
  assert.match(
    systemInfoStylesSource,
    /\.system-info-resource-link:hover svg,[\s\S]*?\.system-info-resource-link:focus-visible svg\s*\{[^}]*opacity:\s*1;/,
  );
  assert.doesNotMatch(systemInfoStylesSource, /margin-left:\s*auto/);
  assert.match(systemInfoStylesSource, /@media \(prefers-reduced-motion: reduce\)/);
});

test("system information page lists sandbox tools and the current identity user pool", () => {
  assert.match(clientSource, /\/web\/system-info/);
  assert.match(systemInfoSource, /当前版本/);
  assert.match(systemInfoSource, />通用</);
  assert.match(systemInfoSource, />存储</);
  assert.match(systemInfoSource, /TOS 地址/);
  assert.match(systemInfoSource, /tosAddress/);
  assert.match(systemInfoSource, />沙箱信息</);
  assert.match(systemInfoSource, /用户池/);
  assert.match(
    systemInfoSource,
    /<dl className="system-info-pool"[\s\S]*?<dt>名称<\/dt>[\s\S]*?<dt>ID<\/dt>[\s\S]*?<dt>域名<\/dt>[\s\S]*?<dt>区域<\/dt>[\s\S]*?<\/dl>/,
  );
  assert.match(
    systemInfoSource,
    /<dt>名称<\/dt>[\s\S]*?<ConsoleLink[\s\S]*?identityUserPoolConsoleUrl/,
  );
  assert.doesNotMatch(systemInfoSource, /<dt>UID<\/dt>/);
  assert.match(systemInfoSource, /listIdentityUserPools/);
  assert.match(systemInfoSource, /pools\.filter\(\(pool\) => pool\.isCurrent\)/);
  assert.doesNotMatch(systemInfoSource, /当前 Studio<\/span>/);
  assert.match(systemInfoSource, /重新加载/);
  assert.match(systemInfoSource, /setSandboxReloadKey/);
  assert.match(systemInfoSource, /setUserPoolsReloadKey/);
  assert.match(systemInfoSource, /role="alert"/);
  assert.match(systemInfoSource, /未配置/);
  assert.match(clientSource, /snapshot: boolean/);
  assert.match(clientSource, /"deepseek_harness"/);
  assert.match(clientSource, /"deepseek_harness_snapshot"/);
  assert.match(clientSource, /typeof \(item as SandboxToolInfo\)\.snapshot !== "boolean"/);
  assert.match(
    systemInfoSource,
    /tool\.snapshot \?\s*\(\s*<span className="system-info-tool-badge">快照版<\/span>\s*\)\s*: null/,
  );
  assert.match(systemInfoStylesSource, /\.system-info-tool-badge\s*\{/);
  assert.match(systemInfoSource, /本地模式未配置用户池/);
  assert.match(systemInfoSource, /当前 Studio 未配置用户池/);
  assert.match(systemInfoSource, /Volcengine credentials not found/);
  assert.match(systemInfoSource, /const isAdmin = role === "admin"/);
  assert.match(systemInfoSource, /if \(!isAdmin\)/);
  assert.match(systemInfoSource, /\{isAdmin \? \(/);
  assert.match(systemInfoStylesSource, /\.system-info-page\s*\{[^}]*padding:\s*32px 32px 0;/);
  assert.match(systemInfoStylesSource, /font-family:\s*inherit/);
  assert.doesNotMatch(
    systemInfoStylesSource,
    /\.system-info-tool,\s*\.system-info-pool\s*\{/,
  );
  assert.match(
    systemInfoStylesSource,
    /\.system-info-pool\s*\{[^}]*padding:\s*4px 0;[^}]*\}/,
  );
  assert.match(
    systemInfoStylesSource,
    /\.system-info-pool\s*\{[^}]*grid-template-columns:\s*1fr;[^}]*gap:\s*8px;/s,
  );
  assert.match(
    systemInfoStylesSource,
    /\.system-info-summary > div,\s*\.system-info-tool > div,\s*\.system-info-pool > div\s*\{[^}]*grid-template-columns:\s*minmax\(140px, 0\.36fr\)\s+minmax\(0, 1fr\);[^}]*align-items:\s*center;[^}]*gap:\s*16px;/s,
  );
  assert.match(
    systemInfoStylesSource,
    /@media \(max-width:\s*520px\)[\s\S]*?\.system-info-summary > div,\s*\.system-info-tool > div,\s*\.system-info-pool > div\s*\{[^}]*grid-template-columns:\s*1fr;[^}]*gap:\s*4px;/,
  );
  assert.doesNotMatch(
    systemInfoStylesSource,
    /\.system-info-pool\s*\{[^}]*(?:background|border):/,
  );
  assert.doesNotMatch(
    systemInfoStylesSource,
    /\.system-info-empty\s*\{[^}]*background:/,
  );
  assert.doesNotMatch(
    systemInfoStylesSource,
    /\.system-info-loading\s*\{[^}]*(?:background|border|border-radius):/,
  );
});
