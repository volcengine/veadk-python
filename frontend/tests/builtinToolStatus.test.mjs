import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const blocksSource = readFileSync(
  new URL("../src/ui/Blocks.tsx", import.meta.url),
  "utf8",
);
const registrySource = readFileSync(
  new URL("../src/ui/builtin-tools/registry.ts", import.meta.url),
  "utf8",
);
const headerSource = readFileSync(
  new URL("../src/ui/builtin-tools/BuiltinToolHeader.tsx", import.meta.url),
  "utf8",
);
const iconsSource = readFileSync(
  new URL("../src/ui/builtin-tools/icons.tsx", import.meta.url),
  "utf8",
);
const toolStylesSource = readFileSync(
  new URL("../src/ui/builtin-tools/builtin-tools.css", import.meta.url),
  "utf8",
);
const sharedStylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);
const shimmerSource = readFileSync(
  new URL("../src/ui/text-shimmer/TextShimmer.tsx", import.meta.url),
  "utf8",
);
const shimmerStylesSource = readFileSync(
  new URL("../src/ui/text-shimmer/text-shimmer.css", import.meta.url),
  "utf8",
);

test("maps supported built-in tools to dedicated Chinese running and done labels", () => {
  const expected = [
    ["web_search", "正在进行网络搜索", "已完成网络搜索"],
    ["image_generate", "正在生成图片", "已完成图片生成"],
    ["video_generate", "正在生成视频", "已完成视频生成"],
    ["load_memory", "正在检索长期记忆", "已完成记忆检索"],
    ["load_knowledgebase", "正在检索知识库", "已完成知识库检索"],
  ];

  for (const [name, running, done] of expected) {
    assert.match(registrySource, new RegExp(`${name}:[\\s\\S]*?${running}[\\s\\S]*?${done}`));
  }
});

test("renders built-in tool calls through the extensible dedicated header", () => {
  assert.match(blocksSource, /getBuiltinToolDefinition\(name\)/);
  assert.match(blocksSource, /<BuiltinToolHeader/);
  assert.match(headerSource, /<TextShimmer/);
  assert.match(headerSource, /definition\.runningLabel/);
  assert.match(headerSource, /definition\.doneLabel/);
  assert.match(headerSource, /aria-expanded=\{open\}/);
  assert.match(toolStylesSource, /data-tool-tone="search"/);
  assert.doesNotMatch(headerSource, /builtin-tool-state/);
  assert.doesNotMatch(toolStylesSource, /builtin-tool-state|builtin-tool-breathe/);
});

test("keeps tool rows minimal and aligns larger details with their icons", () => {
  assert.match(
    toolStylesSource,
    /\.builtin-tool-head:hover\s*\{\s*color:[^}]+\}/,
  );
  assert.doesNotMatch(
    toolStylesSource,
    /\.builtin-tool-head:hover\s*\{[^}]*background/,
  );
  assert.match(
    toolStylesSource,
    /\.builtin-tool-icon\s*\{[^}]*color:[^}]+\}/,
  );
  assert.match(
    toolStylesSource,
    /\.builtin-tool-icon > svg\s*\{[^}]*width:\s*18px[^}]*height:\s*18px/,
  );
  assert.doesNotMatch(
    toolStylesSource,
    /\.builtin-tool-icon\s*\{[^}]*(?:border|background):/,
  );
  assert.match(
    sharedStylesSource,
    /\.tool-detail\s*\{[^}]*padding-left:\s*3px/,
  );
  assert.match(
    sharedStylesSource,
    /\.tool-args\s*\{[^}]*font-size:\s*12px/,
  );
  assert.match(
    toolStylesSource,
    /\.builtin-tool-label\s*\{[^}]*font-weight:\s*400/,
  );
});

test("renders ordinary tools with a neutral drawn icon and shared geometry", () => {
  assert.match(blocksSource, /function GenericToolIcon/);
  assert.match(blocksSource, /className="tool-icon tool-icon--generic"/);
  assert.match(blocksSource, /className="tool-head tool-head--generic"/);
  assert.match(blocksSource, /<ToolDisclosureIcon/);
  assert.doesNotMatch(blocksSource, /tool-dot/);
  assert.match(
    sharedStylesSource,
    /\.tool-head--generic\s*\{[^}]*min-height:\s*32px[^}]*padding:\s*3px 7px 3px 3px/,
  );
  assert.match(
    sharedStylesSource,
    /\.tool-icon > svg\s*\{[^}]*width:\s*18px[^}]*height:\s*18px/,
  );
  assert.match(
    sharedStylesSource,
    /\.tool-icon--generic\s*\{\s*color:\s*hsl\(var\(--muted-foreground\)\)/,
  );
});

test("uses repository-owned current-color SVG icons for every special tool", () => {
  for (const icon of [
    "WebSearchIcon",
    "ImageGenerateIcon",
    "VideoGenerateIcon",
    "LoadMemoryIcon",
    "LoadKnowledgebaseIcon",
  ]) {
    assert.match(iconsSource, new RegExp(`export function ${icon}`));
  }
  assert.match(iconsSource, /viewBox="0 0 24 24"/);
  assert.match(iconsSource, /stroke="currentColor"/);
  assert.doesNotMatch(iconsSource, /lucide-react|<img|https?:\/\//);
});

test("centralizes all loading text shimmer behavior in TextShimmer", () => {
  assert.match(shimmerSource, /Math\.min\(Math\.max\(spread, 5\), 45\)/);
  assert.match(shimmerStylesSource, /@keyframes text-shimmer/);
  assert.match(shimmerStylesSource, /prefers-reduced-motion: reduce/);
  assert.match(blocksSource, /<TextShimmer className="think-label"/);
  assert.match(blocksSource, /<TextShimmer className="tool-name"/);
  assert.doesNotMatch(blocksSource, /className=\{`[^`]*shimmer/);
});

test("aligns thinking and special-tool headers on the same visual grid", () => {
  assert.match(blocksSource, /className="think-icon"/);
  assert.match(
    sharedStylesSource,
    /\.think-head\s*\{[^}]*gap:\s*8px[^}]*min-height:\s*32px[^}]*padding:\s*3px 7px 3px 3px/,
  );
  assert.match(
    sharedStylesSource,
    /\.think-icon\s*\{[^}]*width:\s*20px[^}]*height:\s*26px[^}]*flex:\s*0 0 20px/,
  );
  assert.match(
    sharedStylesSource,
    /\.think-label\s*\{[^}]*font-size:\s*13\.5px[^}]*font-weight:\s*400[^}]*line-height:\s*1\.35/,
  );
  assert.match(blocksSource, /<TextShimmer className="think-label" duration=\{2\.4\} spread=\{18\}>/);
});
