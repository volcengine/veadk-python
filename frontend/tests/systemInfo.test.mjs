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
    /account\.systemInfo[\s\S]*?account\.language[\s\S]*?account\.logout/,
    "system information should appear above logout",
  );
  assert.match(sidebarSource, /onSelect=\{onSystemInfo\}/);
  assert.doesNotMatch(sidebarSource, /role="dialog"/);
  assert.doesNotMatch(sidebarSource, /createPortal/);
});

test("system information returns to the page recorded beneath it", () => {
  assert.match(systemInfoSource, /onBack: \(\) => void/);
  assert.match(
    systemInfoSource,
    /<PageBackButton[\s\S]*?label=\{t\("common\.back"\)\}[\s\S]*?onClick=\{onBack\}/,
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
  assert.match(systemInfoSource, /t\("systemInfo\.currentVersion"\)/);
  assert.match(systemInfoSource, /t\("systemInfo\.general"\)/);
  assert.match(systemInfoSource, /t\("systemInfo\.storage"\)/);
  assert.match(systemInfoSource, /t\("systemInfo\.tosAddress"\)/);
  assert.match(systemInfoSource, /tosAddress/);
  assert.match(systemInfoSource, /t\("systemInfo\.sandboxInfo"\)/);
  assert.match(systemInfoSource, /t\("systemInfo\.userPool"\)/);
  assert.match(
    systemInfoSource,
    /<dl className="system-info-pool"[\s\S]*?<dt>\{t\("common\.name"\)\}<\/dt>[\s\S]*?<dt>\{t\("systemInfo\.id"\)\}<\/dt>[\s\S]*?<dt>\{t\("systemInfo\.domain"\)\}<\/dt>[\s\S]*?<dt>\{t\("systemInfo\.region"\)\}<\/dt>[\s\S]*?<\/dl>/,
  );
  assert.match(
    systemInfoSource,
    /<dt>\{t\("common\.name"\)\}<\/dt>[\s\S]*?<ConsoleLink[\s\S]*?identityUserPoolConsoleUrl/,
  );
  assert.doesNotMatch(systemInfoSource, /<dt>UID<\/dt>/);
  assert.match(systemInfoSource, /listIdentityUserPools/);
  assert.match(systemInfoSource, /pools\.filter\(\(pool\) => pool\.isCurrent\)/);
  assert.doesNotMatch(systemInfoSource, /当前 Studio<\/span>/);
  assert.match(systemInfoSource, /t\("common\.reload"\)/);
  assert.match(systemInfoSource, /setSandboxReloadKey/);
  assert.match(systemInfoSource, /setUserPoolsReloadKey/);
  assert.match(systemInfoSource, /role="alert"/);
  assert.match(systemInfoSource, /t\("common\.notConfigured"\)/);
  assert.match(clientSource, /snapshot: boolean/);
  assert.match(clientSource, /"deepseek_harness"/);
  assert.match(clientSource, /"deepseek_harness_snapshot"/);
  assert.match(clientSource, /SANDBOX_TOOL_DISPLAY_ORDER/);
  assert.match(
    clientSource,
    /codex:\s*0[\s\S]*?codex_snapshot:\s*1[\s\S]*?deepseek_harness:\s*2[\s\S]*?deepseek_harness_snapshot:\s*3/,
  );
  assert.match(clientSource, /\.sort\(\(left, right\) =>/);
  assert.match(clientSource, /typeof \(item as SandboxToolInfo\)\.snapshot !== "boolean"/);
  assert.match(clientSource, /needsModelEnvUpdate: boolean/);
  assert.match(clientSource, /canUpdateModelEnv: boolean/);
  assert.match(clientSource, /modelEnvError: string/);
  assert.match(clientSource, /modelEnvErrorCode: string/);
  assert.match(
    clientSource,
    /typeof \(item as SandboxToolInfo\)\.needsModelEnvUpdate !== "boolean"/,
  );
  assert.match(
    clientSource,
    /typeof \(item as SandboxToolInfo\)\.canUpdateModelEnv !== "boolean"/,
  );
  assert.match(
    clientSource,
    /typeof \(item as SandboxToolInfo\)\.modelEnvError !== "string"/,
  );
  assert.match(
    clientSource,
    /typeof \(item as SandboxToolInfo\)\.modelEnvErrorCode !== "string"/,
  );
  assert.match(clientSource, /export type CodexSandboxToolKind = Extract/);
  assert.match(clientSource, /updateCodexSandboxToolModelEnv/);
  assert.match(
    clientSource,
    /\/web\/system-info\/sandbox-tools\/\$\{encodeURIComponent\(kind\)\}\/model-env/,
  );
  assert.match(clientSource, /method: "POST"/);
  assert.match(clientSource, /updated: boolean/);
  assert.match(
    systemInfoSource,
    /tool\.snapshot \?\s*\(\s*<span className="system-info-tool-badge">\{t\("systemInfo\.snapshot"\)\}<\/span>\s*\)\s*: null/,
  );
  assert.match(systemInfoSource, /function isCodexSandboxToolKind/);
  assert.match(systemInfoSource, /kind === "codex" \|\| kind === "codex_snapshot"/);
  assert.match(systemInfoSource, /const updateVisible =/);
  assert.match(systemInfoSource, /tool\.needsModelEnvUpdate/);
  assert.match(systemInfoSource, /tool\.canUpdateModelEnv/);
  assert.match(systemInfoSource, /tool\.modelEnvError/);
  assert.doesNotMatch(systemInfoSource, /tool\.modelEnvErrorCode/);
  assert.match(systemInfoSource, /setSandboxTools\(\(current\) =>/);
  assert.match(systemInfoSource, /needsModelEnvUpdate: false/);
  assert.match(systemInfoSource, /modelEnvErrorCode: ""/);
  assert.doesNotMatch(systemInfoSource, /has-action/);
  assert.doesNotMatch(systemInfoSource, /system-info-resource-actions/);
  assert.match(systemInfoSource, /className="system-info-resource-update"/);
  assert.match(systemInfoSource, /RefreshCw/);
  assert.match(systemInfoSource, /aria-label=\{t\("systemInfo\.updateModelEnv"/);
  assert.doesNotMatch(systemInfoSource, /<span>更新<\/span>/);
  assert.match(systemInfoSource, /updateSandboxToolModelEnv\(tool\)/);
  assert.match(systemInfoSource, /result\.updated[\s\S]*?t\("systemInfo\.modelEnvUpdated"\)[\s\S]*?t\("systemInfo\.modelEnvAlreadyCurrent"\)/);
  assert.match(systemInfoSource, /const inlineError =/);
  assert.match(systemInfoSource, /className="system-info-inline-error" role="alert"/);
  assert.match(systemInfoSource, /className="system-info-inline-status" role="status"/);
  assert.match(systemInfoStylesSource, /\.system-info-tool-badge\s*\{/);
  assert.doesNotMatch(systemInfoStylesSource, /\.system-info-resource-value\.has-action\s*\{/);
  assert.doesNotMatch(systemInfoStylesSource, /\.system-info-resource-actions\s*\{/);
  assert.doesNotMatch(systemInfoStylesSource, /flex-wrap:\s*wrap/);
  assert.doesNotMatch(
    systemInfoStylesSource,
    /\.system-info-resource-link > span\s*\{[^}]*text-overflow:/s,
  );
  assert.match(systemInfoStylesSource, /\.system-info-resource-update\s*\{/);
  assert.match(systemInfoStylesSource, /width:\s*30px/);
  assert.match(systemInfoStylesSource, /margin-left:\s*18px/);
  assert.match(systemInfoStylesSource, /\.system-info-resource-update svg\s*\{/);
  assert.match(systemInfoStylesSource, /system-info-spin/);
  assert.match(systemInfoStylesSource, /\.system-info-resource-update:disabled\s*\{/);
  assert.match(systemInfoStylesSource, /\.system-info-inline-error\s*\{/);
  assert.match(systemInfoSource, /t\("systemInfo\.noLocalUserPool"\)/);
  assert.match(systemInfoSource, /t\("systemInfo\.noUserPool"\)/);
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

test("system information shows environment CodePipeline and Container Registry resources", () => {
  assert.match(clientSource, /getEnvironmentResources/);
  assert.match(clientSource, /\/web\/v3\/environment-resources/);
  assert.match(systemInfoSource, /t\("systemInfo\.environmentBuild"\)/);
  assert.match(systemInfoSource, /t\("systemInfo\.codePipelineWorkspace"\)/);
  assert.match(systemInfoSource, /t\("systemInfo\.codePipelinePipeline"\)/);
  assert.match(systemInfoSource, /t\("systemInfo\.containerRegistryRepository"\)/);
  assert.match(systemInfoSource, /environmentResources\.codePipeline\.consoleUrl/);
  assert.match(systemInfoSource, /environmentResources\.containerRegistry\.consoleUrl/);
  assert.match(systemInfoSource, /environmentResourcesError/);
  assert.match(systemInfoSource, /t\("systemInfo\.environmentResourcesError"\)/);
});
