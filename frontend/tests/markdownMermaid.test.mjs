import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const markdownSource = readFileSync(
  new URL("../src/ui/Markdown.tsx", import.meta.url),
  "utf8",
);
const mermaidSource = readFileSync(
  new URL("../src/ui/MermaidDiagram.tsx", import.meta.url),
  "utf8",
);
const echartsSource = readFileSync(
  new URL("../src/ui/EChartsDiagram.tsx", import.meta.url),
  "utf8",
);
const echartsOptionUrl = new URL("../src/ui/echartsOption.ts", import.meta.url);
const echartsOptionSource = readFileSync(echartsOptionUrl, "utf8");
const visualizationPanelSource = readFileSync(
  new URL("../src/ui/VisualizationPanel.tsx", import.meta.url),
  "utf8",
);
const blocksSource = readFileSync(
  new URL("../src/ui/Blocks.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

const diagrams = {
  flowchart: `flowchart LR
    A[Start] --> B[Done]`,
  lineChart: `xychart-beta
    title "Requests"
    x-axis [Jan, Feb, Mar]
    y-axis "Count" 0 --> 100
    line [24, 58, 91]`,
  pieChart: `pie showData
    title Traffic sources
    "Direct" : 42
    "Search" : 58`,
};

test("official Mermaid bundle recognizes the Studio diagram contract", async () => {
  const { default: mermaid } = await import("mermaid");
  mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });

  const registeredTypes = new Set(
    mermaid.getRegisteredDiagramsMetadata().map(({ id }) => id),
  );
  assert.ok(registeredTypes.size > 20, "the complete Mermaid registry should be available");
  for (const type of ["flowchart-v2", "xychart", "pie", "sequence", "gantt", "sankey"]) {
    assert.ok(registeredTypes.has(type), `${type} should be registered`);
  }

  const expectedTypes = {
    flowchart: "flowchart-v2",
    lineChart: "xychart",
    pieChart: "pie",
  };
  for (const [name, definition] of Object.entries(diagrams)) {
    assert.equal(
      mermaid.detectType(definition, {}),
      expectedTypes[name],
      `${name} should be registered`,
    );
  }

  await assert.rejects(
    mermaid.parse("not a diagram"),
    "invalid Mermaid should reach Studio's source fallback",
  );
});

test("Markdown lazily renders Mermaid code fences with a safe fallback", () => {
  assert.match(mermaidSource, /import\("mermaid"\)/);
  assert.match(markdownSource, /language === "mermaid"/);
  assert.match(mermaidSource, /securityLevel:\s*"strict"/);
  assert.match(markdownSource, /<MermaidDiagram/);
  assert.match(mermaidSource, /role="alert"/);
  assert.match(visualizationPanelSource, /@openai\/apps-sdk-ui\/components\/SegmentedControl/);
  assert.match(visualizationPanelSource, /value="preview"/);
  assert.match(visualizationPanelSource, /value="code"/);
  assert.match(visualizationPanelSource, /size="sm"/);
  assert.match(visualizationPanelSource, /gutterSize="sm"/);
  assert.match(markdownSource, /streaming\?: boolean/);
  assert.match(blocksSource, /<Markdown text=\{displayedText\} streaming=\{streaming\}/);
});

test("Mermaid diagrams stay responsive inside conversation messages", () => {
  assert.match(
    stylesSource,
    /\.turn--assistant \.bubble:has\(\.visualization-card\)\s*\{[^}]*width:\s*100%/s,
  );
  assert.match(stylesSource, /\.visualization-card\s*\{[^}]*background:\s*hsl\(var\(--muted\)/s);
  assert.match(
    stylesSource,
    /\.visualization-card__toolbar\s*\{[^}]*padding:\s*8px 10px;[^}]*border-bottom:/s,
  );
  assert.match(
    stylesSource,
    /\.visualization-card__tabs\s*\{[^}]*font-size:\s*inherit;[^}]*font-weight:\s*inherit/s,
  );
  assert.match(stylesSource, /\.mermaid-diagram\s*\{[^}]*overflow-x:\s*auto/s);
  assert.match(stylesSource, /\.mermaid-diagram svg\s*\{[^}]*max-width:\s*100%/s);
});

test("ECharts fences use a lazy, interactive, data-only renderer", () => {
  const packageJson = JSON.parse(readFileSync(new URL("../package.json", import.meta.url)));
  const echartsPackage = JSON.parse(
    readFileSync(new URL("../node_modules/echarts/package.json", import.meta.url)),
  );

  assert.equal(packageJson.dependencies.echarts, "6.1.0");
  assert.equal(packageJson.dependencies.json5, "2.2.3");
  assert.equal(echartsPackage.license, "Apache-2.0");
  assert.match(markdownSource, /language === "echarts"/);
  assert.match(echartsSource, /import\("echarts"\)/);
  assert.match(echartsSource, /parseEChartsOption/);
  assert.match(echartsOptionSource, /JSON5\.parse/);
  assert.match(echartsOptionSource, /LinearGradient\|RadialGradient/);
  assert.match(echartsOptionSource, /renderMode:\s*"richText"/);
  assert.match(echartsSource, /new ResizeObserver/);
  assert.doesNotMatch(`${echartsSource}\n${echartsOptionSource}`, /\beval\s*\(|new Function/);
});

test("JSON5 accepts common ECharts examples without enabling JavaScript", async () => {
  const { build } = await import("esbuild");
  const result = await build({
    entryPoints: [fileURLToPath(echartsOptionUrl)],
    bundle: true,
    format: "esm",
    platform: "browser",
    write: false,
  });
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString("base64")}`;
  const { parseEChartsOption } = await import(moduleUrl);
  const source = `option = {
    // ECharts documentation commonly uses JavaScript object syntax.
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ['Mon', 'Tue', 'Wed'], },
    yAxis: { type: 'value' },
    series: [{
      type: 'bar',
      itemStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#5470c6' },
          { offset: 1, color: '#91cc75' },
        ]),
      },
      data: [120, 200, 150],
    }],
  };`;

  assert.throws(() => JSON.parse(source));
  const option = parseEChartsOption(source);
  assert.deepEqual(option.series[0].data, [120, 200, 150]);
  assert.deepEqual(option.series[0].itemStyle.color, {
    type: "linear",
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: "#5470c6" },
      { offset: 1, color: "#91cc75" },
    ],
    global: false,
  });
  assert.equal(option.tooltip.renderMode, "richText");
  assert.throws(
    () => parseEChartsOption("{ formatter: (value) => value }"),
    /function callbacks are not supported/,
  );
  assert.throws(() => parseEChartsOption("{ constructor: {} }"));
  assert.throws(() => parseEChartsOption("{ value: Infinity }"));
  assert.throws(() => parseEChartsOption("{ symbol: 'image://https://example.com/a.png' }"));
  assert.deepEqual(
    parseEChartsOption("{ title: { text: 'echarts.graphic.LinearGradient(0,0,0,1,[])' } }").title,
    { text: "echarts.graphic.LinearGradient(0,0,0,1,[])" },
  );
});

test("official ECharts renders representative line and pie options", async () => {
  const echarts = await import("echarts");
  const options = [
    {
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: ["Jan", "Feb", "Mar"] },
      yAxis: { type: "value" },
      series: [{ type: "line", data: [24, 58, 91] }],
    },
    {
      tooltip: { trigger: "item" },
      series: [{
        type: "pie",
        data: [{ name: "Direct", value: 42 }, { name: "Search", value: 58 }],
      }],
    },
  ];

  for (const option of options) {
    const chart = echarts.init(null, undefined, {
      renderer: "svg",
      ssr: true,
      width: 640,
      height: 360,
    });
    chart.setOption(option);
    assert.match(chart.renderToSVGString(), /^<svg/);
    chart.dispose();
  }
});
