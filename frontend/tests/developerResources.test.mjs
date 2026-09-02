import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const sidebarSource = source("../src/ui/Sidebar.tsx");
const appSource = source("../src/App.tsx");
const developerResourcesSource = source("../src/ui/DeveloperResources.tsx");
const developerResourcesStyles = source("../src/ui/DeveloperResources.css");

test("opens Developer Resources as a first-class Studio page", () => {
  assert.match(sidebarSource, /onDeveloperResources: \(\) => void/);
  assert.match(
    sidebarSource,
    /import \{ BookWrench \} from "@openai\/apps-sdk-ui\/components\/Icon";/,
  );
  const clickIndex = sidebarSource.indexOf("onClick={onDeveloperResources}");
  assert.ok(clickIndex >= 0, "developer resources should be clickable");
  assert.match(
    sidebarSource.slice(clickIndex, clickIndex + 500),
    /aria-label="开发者资源"[\s\S]*?<BookWrench className="icon" \/>/,
  );
  assert.match(
    appSource,
    /import \{ DeveloperResources \} from "\.\/ui\/DeveloperResources"/,
  );
  assert.match(appSource, /onDeveloperResources=\{/);
  assert.match(appSource, /<DeveloperResources\b/);
});

test("renders a page title and three resource sections with subtitles", () => {
  assert.ok(
    /<h1[^>]*>\s*开发者资源\s*<\/h1>/.test(developerResourcesSource) ||
      /<ResourcePageHeader\s+title="开发者资源"\s*\/>/.test(
        developerResourcesSource,
      ),
    "should render 开发者资源 as the page title",
  );

  for (const title of ["相关链接", "最佳实践", "Showcases"]) {
    const escapedTitle = title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const dataSection = new RegExp(
      `title:\\s*["']${escapedTitle}["'][\\s\\S]{0,180}?(?:subtitle|description):\\s*["'][^"']+["']`,
    );
    const semanticSection = new RegExp(
      `<h2[^>]*>\\s*${escapedTitle}\\s*</h2>[\\s\\S]{0,300}?<p[^>]*>\\s*[^<{][\\s\\S]*?</p>`,
    );
    assert.ok(
      dataSection.test(developerResourcesSource) ||
        semanticSection.test(developerResourcesSource),
      `${title} should be a section heading with a non-empty subtitle`,
    );
  }
});

test("renders related documentation and console destinations as Apps SDK links", () => {
  assert.match(
    developerResourcesSource,
    /import \{ TextLink \} from "@openai\/apps-sdk-ui\/components\/TextLink"/,
  );
  assert.match(
    developerResourcesSource,
    /import \{ ArrowUpRight \} from "@openai\/apps-sdk-ui\/components\/Icon"/,
  );
  for (const label of [
    "VeADK 文档",
    "AgentKit CLI 文档",
    "AgentKit 平台文档",
    "AgentKit 控制台",
  ]) {
    assert.match(developerResourcesSource, new RegExp(label));
  }
  assert.equal((developerResourcesSource.match(/<TextLink/g) ?? []).length, 4);
  assert.equal((developerResourcesSource.match(/<li>/g) ?? []).length, 4);
  assert.match(developerResourcesStyles, /padding-left:\s*20px/);
  assert.match(
    developerResourcesStyles,
    /developer-resources__link\s*\{[\s\S]*?font-size:\s*15px/,
  );
  assert.match(developerResourcesStyles, /scrollbar-width:\s*none/);
  assert.match(
    developerResourcesStyles,
    /developer-resources__content::\-webkit-scrollbar[\s\S]*?display:\s*none/,
  );
});

test("renders linked best-practice guides and responsive showcases", () => {
  for (const title of [
    "使用 VeADK 开发并部署智能体",
    "使用 AgentKit CLI 开发并部署智能体",
    "多智能体研究助手",
    "多模态内容分析",
    "智能客服工作台",
    "联网搜索 Agent",
    "A2UI 交互应用",
  ]) {
    assert.match(developerResourcesSource, new RegExp(title));
  }

  assert.match(
    developerResourcesSource,
    /https:\/\/docs\.volcengine\.com\/docs\/86681\/2155817\?lang=zh/,
  );
  assert.match(
    developerResourcesSource,
    /https:\/\/docs\.volcengine\.com\/docs\/86681\/1844871\?lang=zh/,
  );
  assert.doesNotMatch(developerResourcesSource, /article-agentkit-delivery/);

  assert.match(developerResourcesSource, /developer-resources__articles/);
  assert.match(developerResourcesSource, /developer-resources__showcases/);
  assert.match(
    developerResourcesStyles,
    /grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/,
  );
  assert.match(
    developerResourcesStyles,
    /developer-resources__showcases\s*\{[\s\S]*?grid-template-columns:\s*repeat\(5,\s*minmax\(0,\s*1fr\)\)/,
  );
  assert.match(
    developerResourcesStyles,
    /@media \(max-width:\s*1100px\)[\s\S]*?grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/,
  );
  assert.match(
    developerResourcesStyles,
    /@media \(max-width:\s*720px\)[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\)/,
  );
});
