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
    /aria-label=\{t\("sidebar:account\.developerResources"\)\}[\s\S]*?<BookWrench className="icon" \/>/,
  );
  assert.match(
    appSource,
    /import \{ DeveloperResources \} from "\.\/ui\/DeveloperResources"/,
  );
  assert.match(appSource, /onDeveloperResources=\{/);
  assert.match(appSource, /<DeveloperResources\b/);
});

test("renders a page title and three resource sections with subtitles", () => {
  assert.match(
    developerResourcesSource,
    /<ResourcePageHeader title=\{t\("developerResources\.title"\)\} \/>/,
  );

  for (const section of ["documentation", "bestPractices", "showcases"]) {
    assert.match(
      developerResourcesSource,
      new RegExp(`developerResources\\.sections\\.${section}\\.title`),
    );
    assert.match(
      developerResourcesSource,
      new RegExp(`developerResources\\.sections\\.${section}\\.description`),
    );
  }
  assert.match(developerResourcesSource, /\{t\(section\.titleKey\)\}/);
  assert.match(developerResourcesSource, /<p>\{t\(section\.descriptionKey\)\}<\/p>/);
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
  for (const key of [
    "veadkDocs",
    "cliDocs",
    "platformDocs",
    "console",
  ]) {
    assert.match(developerResourcesSource, new RegExp(`t\\("developerResources\\.links\\.${key}"\\)`));
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
  for (const key of [
    "developerResources.articles.veadkDevelopment.title",
    "developerResources.articles.cliDevelopment.title",
    "developerResources.showcases.researchAssistant.title",
    "developerResources.showcases.multimodalAnalysis.title",
    "developerResources.showcases.customerService.title",
    "developerResources.showcases.webSearch.title",
    "developerResources.showcases.a2uiApp.title",
  ]) {
    assert.match(developerResourcesSource, new RegExp(key.replaceAll(".", "\\.")));
  }
  assert.match(developerResourcesSource, /<strong>\{t\(article\.titleKey\)\}<\/strong>/);
  assert.match(developerResourcesSource, /<strong>\{t\(showcase\.titleKey\)\}<\/strong>/);

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
