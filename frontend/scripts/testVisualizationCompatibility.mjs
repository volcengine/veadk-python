import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import * as echarts from "echarts";
import { JSDOM } from "jsdom";

const sessionUrl = process.argv[2];
if (!sessionUrl) {
  throw new Error(
    "Usage: npm run test:visualizations -- <Studio session JSON URL>",
  );
}

function finalModelText(event) {
  if (event?.content?.role !== "model" || event.partial !== false) return "";
  return (event.content.parts ?? [])
    .filter((part) => !part.thought && typeof part.text === "string")
    .map((part) => part.text)
    .join("");
}

function extractFences(markdown, language) {
  const fences = [];
  const pattern = new RegExp(
    "```" + language + "\\s*\\n([\\s\\S]*?)```",
    "gi",
  );
  let match;
  while ((match = pattern.exec(markdown))) {
    const prefix = markdown.slice(Math.max(0, match.index - 300), match.index);
    const headings = [...prefix.matchAll(/^###\s+(.+)$/gm)];
    fences.push({
      title: headings.at(-1)?.[1]?.trim() || `${language} ${fences.length + 1}`,
      source: match[1].trim(),
    });
  }
  return fences;
}

async function loadEChartsOptionParser() {
  const entryPoint = fileURLToPath(
    new URL("../src/ui/echartsOption.ts", import.meta.url),
  );
  const result = await build({
    entryPoints: [entryPoint],
    bundle: true,
    format: "esm",
    platform: "browser",
    write: false,
  });
  const encoded = Buffer.from(result.outputFiles[0].text).toString("base64");
  return import(`data:text/javascript;base64,${encoded}`);
}

function result(language, title, ok, type, issue = "") {
  return { language, title, ok, type, issue };
}

const response = await fetch(sessionUrl);
if (!response.ok) throw new Error(`Session fetch failed: ${response.status}`);
const session = await response.json();
const messages = (session.events ?? []).map(finalModelText).filter(Boolean);
const mermaidFences = messages.flatMap((text) => extractFences(text, "mermaid"));
const echartsFences = messages.flatMap((text) => extractFences(text, "echarts"));
const results = [];

const dom = new JSDOM("<!doctype html><html><body></body></html>");
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.navigator = dom.window.navigator;
globalThis.Element = dom.window.Element;
globalThis.HTMLElement = dom.window.HTMLElement;
globalThis.SVGElement = dom.window.SVGElement;
const { default: mermaid } = await import("mermaid");
mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
for (const fence of mermaidFences) {
  let type = "unknown";
  try {
    type = mermaid.detectType(fence.source, {});
    await mermaid.parse(fence.source);
    results.push(result("mermaid", fence.title, true, type));
  } catch (error) {
    results.push(result("mermaid", fence.title, false, type, error.message));
  }
}
dom.window.close();
delete globalThis.window;
delete globalThis.document;
delete globalThis.navigator;
delete globalThis.Element;
delete globalThis.HTMLElement;
delete globalThis.SVGElement;

const { parseEChartsOption } = await loadEChartsOptionParser();
for (const fence of echartsFences) {
  let type = "unknown";
  try {
    const option = parseEChartsOption(fence.source, true);
    const series = Array.isArray(option.series) ? option.series : [option.series];
    type = series.filter(Boolean).map((item) => item.type ?? "unknown").join("+");
    const chart = echarts.init(null, undefined, {
      renderer: "svg",
      ssr: true,
      width: 768,
      height: 360,
    });
    try {
      chart.setOption(option);
      const svg = chart.renderToSVGString();
      if (!svg.startsWith("<svg")) throw new Error("SSR did not return SVG");
    } finally {
      chart.dispose();
    }
    results.push(result("echarts", fence.title, true, type));
  } catch (error) {
    results.push(result("echarts", fence.title, false, type, error.message));
  }
}

for (const item of results) {
  const status = item.ok ? "PASS" : "FAIL";
  console.log(`${status}\t${item.language}\t${item.type}\t${item.title}${item.issue ? `\t${item.issue}` : ""}`);
}

const totals = Object.fromEntries(
  ["mermaid", "echarts"].map((language) => {
    const items = results.filter((item) => item.language === language);
    return [language, { total: items.length, passed: items.filter((item) => item.ok).length }];
  }),
);
console.log(`SUMMARY\t${JSON.stringify(totals)}`);

if (mermaidFences.length === 0 || echartsFences.length === 0) process.exitCode = 2;
else if (results.some((item) => !item.ok)) process.exitCode = 1;
