import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const blocksSource = readFileSync(
  new URL("../src/ui/Blocks.tsx", import.meta.url),
  "utf8",
);
const blockTypesSource = readFileSync(
  new URL("../src/blocks.ts", import.meta.url),
  "utf8",
);
const agentKitLogoSource = readFileSync(
  new URL("../src/ui/icons/AgentKitLogoIcon.tsx", import.meta.url),
  "utf8",
);
const registrySource = readFileSync(
  new URL("../src/ui/builtin-tools/registry.ts", import.meta.url),
  "utf8",
);
const conversationZhSource = readFileSync(
  new URL("../src/i18n/resources/zh-CN/conversation.json", import.meta.url),
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

test("maps supported built-in tools to localized running and done labels", () => {
  const expected = [
    ["web_search", "正在进行网络搜索", "已完成网络搜索"],
    ["link_reader", "正在读取网页", "已完成网页读取"],
    ["image_generate", "正在生成图片", "已完成图片生成"],
    ["video_generate", "正在生成视频", "已完成视频生成"],
    ["ppt_generate", "正在生成 PPT", "已完成 PPT 生成"],
    [
      "run_code",
      "正在 AgentKit 沙箱中执行代码",
      "已在 AgentKit 沙箱中完成代码执行",
    ],
    ["list_envs", "正在查看可用环境", "已读取可用环境"],
    ["get_env_manifest", "正在读取环境 Manifest", "已读取环境 Manifest"],
    ["execute_in_sandbox", "正在环境中执行命令", "已在环境中完成命令执行"],
    [
      "delegate_to_codex_sandbox",
      "Codex Sandbox 正在执行",
      "Codex Sandbox 已完成",
      "Codex Sandbox 执行失败",
    ],
    ["load_memory", "正在检索长期记忆", "已完成记忆检索"],
    ["load_knowledgebase", "正在检索知识库", "已完成知识库检索"],
    ["load_skill", "正在加载技能", "已加载技能"],
  ];

  for (const [name, running, done, failed] of expected) {
    assert.match(
      conversationZhSource,
      new RegExp(`"${name}"[\\s\\S]*?${running}[\\s\\S]*?${done}`),
    );
    if (failed) {
      assert.match(conversationZhSource, new RegExp(`"${name}"[\\s\\S]*?${failed}`));
    }
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
  assert.match(toolStylesSource, /data-tool-tone="skill"/);
  assert.match(blocksSource, /function loadSkillLabel/);
  assert.match(blocksSource, /loadSkillLabel\(name, args, t\)/);
  assert.match(blocksSource, /builtinTool\.failedLabel/);
  assert.match(blocksSource, /t\("blocks\.agentAdjusting"\)/);
  assert.match(blocksSource, /createdAgentsHaveFailure\(args, response\)/);
  assert.match(blocksSource, /streaming \|\| hasLaterCreateAgentAttempt/);
  assert.match(
    blocksSource,
    /label=\{[\s\S]*?isAdjustingAgent[\s\S]*?done=\{done\}/,
  );
  assert.match(blocksSource, /t\("blocks\.useSkill", \{ name: skillName\.trim\(\) \}\)/);
  assert.match(headerSource, /label\?: string/);
  assert.doesNotMatch(headerSource, /builtin-tool-state/);
  assert.doesNotMatch(
    toolStylesSource,
    /builtin-tool-state|builtin-tool-breathe/,
  );
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
  assert.match(toolStylesSource, /\.builtin-tool-icon\s*\{[^}]*color:[^}]+\}/);
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
  assert.match(sharedStylesSource, /\.tool-args\s*\{[^}]*font-size:\s*12px/);
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

test("additively supports tool outcomes and plans in the shared block renderer", () => {
  assert.match(
    blockTypesSource,
    /kind: "tool"[\s\S]*?status\?: "running" \| "completed" \| "failed"/,
  );
  assert.match(blockTypesSource, /defaultOpen\?: boolean/);
  assert.match(blockTypesSource, /kind: "plan"/);
  assert.match(
    blockTypesSource,
    /status: "pending" \| "in_progress" \| "completed" \| "failed"/,
  );
  assert.match(blocksSource, /function PlanBlock/);
  assert.match(blocksSource, /case "plan"/);
  assert.match(blocksSource, /data-status=\{toolStatus\}/);
  assert.match(
    blocksSource,
    /const\s+shouldDefaultOpen\s*=[\s\S]*?hideHeader[\s\S]*?defaultOpen[\s\S]*?Boolean\(DetailRenderer\)/,
  );
  assert.match(blocksSource, /useState\(shouldDefaultOpen\)/);
  assert.match(
    blocksSource,
    /if \(!touched\.current && shouldDefaultOpen\) setOpen\(true\)/,
  );
});

test("registers create-agent tools with dedicated detail renderers", () => {
  assert.match(
    registrySource,
    /collect_resources:[\s\S]*?detailRenderer: CollectResourcesCard/,
  );
  assert.match(
    registrySource,
    /create_agents:[\s\S]*?detailRenderer: CreateAgentsCard/,
  );
  assert.match(
    blocksSource,
    /<DetailRenderer[\s\S]*?args=\{args\}[\s\S]*?response=\{response\}[\s\S]*?status=\{toolStatus\}[\s\S]*?\/>/,
  );
  assert.match(blocksSource, /onBranchSelect=\{onBranchSelect\}/);
  assert.doesNotMatch(
    headerSource,
    /LoadingIndicator|aria-label="已完成"|builtin-tool-status/,
  );
  assert.match(toolStylesSource, /data-tool-tone="resources"/);
  assert.match(toolStylesSource, /data-tool-tone="agent"/);
});

test("uses repository-owned current-color SVG icons for every special tool", () => {
  for (const icon of [
    "WebSearchIcon",
    "ImageGenerateIcon",
    "VideoGenerateIcon",
    "PresentationGenerateIcon",
    "LoadMemoryIcon",
    "LoadKnowledgebaseIcon",
    "LoadSkillIcon",
    "RunCodeIcon",
    "CollectResourcesIcon",
    "CreateAgentsIcon",
    "ListEnvironmentsIcon",
    "EnvironmentManifestIcon",
    "ExecuteInSandboxIcon",
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

test("uses the monochrome AgentKit mark as the accessible thinking status indicator", () => {
  assert.match(
    blocksSource,
    /<AgentKitLogoIcon[\s\S]*?className=\{`thinking-logo/,
  );
  assert.doesNotMatch(blocksSource, /function SparkIcon/);
  assert.match(agentKitLogoSource, /viewBox="0 0 111 117"/);
  assert.match(agentKitLogoSource, /fill="currentColor"/);
  assert.match(agentKitLogoSource, /aria-hidden="true"/);
  assert.match(
    sharedStylesSource,
    /\.think-icon > svg\s*\{\s*width:\s*14px;\s*height:\s*15px;/,
  );
  assert.match(
    sharedStylesSource,
    /thinking-logo-breathe 1\.6s ease-in-out infinite/,
  );
  assert.match(
    sharedStylesSource,
    /opacity:\s*0\.42;\s*transform:\s*scale\(0\.97\)/,
  );
  assert.match(
    sharedStylesSource,
    /opacity:\s*0\.72;\s*transform:\s*scale\(1\.02\)/,
  );
  assert.match(
    sharedStylesSource,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.thinking-logo\.is-active\s*\{[^}]*animation:\s*none/,
  );
});

test("normalizes token-level line breaks in thinking text while retaining paragraphs", () => {
  assert.match(blocksSource, /\.replace\(\/\\r\\n\?\/g,\s*["']\\n["']\)/);
  assert.match(blocksSource, /\.split\(\/\\n\{2,\}\//);
  assert.match(
    blocksSource,
    /paragraph\.replace\(\/\[\^\\S\\n\]\*\\n\[\^\\S\\n\]\*\/g/,
  );
  assert.match(blocksSource, /\.join\(["']\\n\\n["']\)/);
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
    /\.think-label\s*\{[^}]*font-size:\s*14\.5px[^}]*font-weight:\s*400[^}]*line-height:\s*1\.35/,
  );
  assert.match(
    sharedStylesSource,
    /\.tool-name\s*\{[^}]*font-size:\s*14\.5px[^}]*font-weight:\s*400[^}]*line-height:\s*1\.35/,
  );
  assert.match(
    blocksSource,
    /<TextShimmer className="think-label" duration=\{2\.4\} spread=\{18\}>/,
  );
});
