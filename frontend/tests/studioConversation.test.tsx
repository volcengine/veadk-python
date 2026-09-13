// @vitest-environment jsdom
import { act, isValidElement, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import type { A2uiMessage, SurfaceState } from "../src/a2ui/types";
import type { Block, Turn } from "../src/blocks";
import { fromStudioTurns } from "../src/components/ai-app/ConversationFlow/StudioConversation";
import { ConversationSurface } from "../src/components/ai-app/ConversationFlow/ConversationSurface";
import { ConversationBlocks } from "../src/components/ai-app/ConversationFlow/ConversationBlocks";

beforeAll(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  window.matchMedia = vi.fn().mockImplementation(query => ({ matches: false, media: query, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }));
  Element.prototype.scrollIntoView = vi.fn();
});

let root: Root;
let host: HTMLDivElement;
beforeEach(() => { host = document.createElement("div"); document.body.append(host); root = createRoot(host); });
afterEach(async () => { await act(async () => root.unmount()); host.remove(); });
async function render(content: ReactNode) { await act(async () => root.render(content)); }
async function click(label: string) {
  const button = Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find(item => item.getAttribute("aria-label") === label || item.textContent === label);
  expect(button).toBeDefined();
  await act(async () => button!.click());
}
async function renderBlocks(blocks: Block[], options: Parameters<typeof fromStudioTurns>[1] = {}) {
  const messages = fromStudioTurns([{ role: "assistant", blocks }], options);
  await render(<ConversationBlocks blocks={messages[0].blocks ?? []} />);
}

const delivery: Extract<Block, { kind: "delivery" }>["value"] = {
  sessionId: "session", artifactSha256: "artifact", validationReportSha256: "report", agentName: "分析智能体", entryPoint: "agent.py", fileCount: 3, artifactSize: 2048, validatedAt: "2026-09-13", gateSummary: ["验证通过"], deployable: true, verified: true, validationSummary: "已验证",
};
const auth: Extract<Block, { kind: "auth" }> = { kind: "auth", callId: "auth", label: "数据源", authConfig: {}, done: false };

it("maps every Studio Block kind in order while retaining identities and state", () => {
  const all: Block[] = [
    { kind: "progress", text: "准备查询" },
    { kind: "thinking", text: "检查数据范围", done: true },
    { kind: "text", text: "正文" },
    { kind: "tool", name: "query", args: { q: 1 }, response: { rows: 2 }, done: false, status: "completed", defaultOpen: true },
    { kind: "plan", title: "执行计划", done: false, items: [{ text: "等待", status: "pending" }, { text: "正在执行", status: "in_progress" }, { text: "完成", status: "completed" }, { text: "失败", status: "failed" }] },
    { kind: "agent-transfer", agentName: "分析智能体", done: false },
    { kind: "a2ui", messages: [] },
    { kind: "attachment", files: [{ id: "attachment", name: "data.csv", uri: "/data.csv" }] },
    { kind: "artifact", files: [{ filename: "result.csv", version: 2 }] },
    { kind: "delivery", value: delivery },
    { kind: "invocation", value: { skills: [{ name: "search", description: "检索" }], targetAgent: { name: "分析智能体", description: "分析", type: "llm", path: ["root", "analyst"] } } },
    auth,
  ];
  const turn: Turn = { role: "assistant", blocks: all, meta: { localId: "local", eventId: "event", author: "主智能体", streaming: true, tokens: 123 } };
  const message = fromStudioTurns([turn])[0];
  expect(message).toMatchObject({ id: "local", role: "assistant", name: "主智能体", status: "running", tokens: 123 });
  expect(message.blocks?.map(block => block.type)).toEqual(["reasoning", "reasoning", "markdown", "tool", "plan", "handoff", "custom", "files", "files", "custom", "custom", "authorization"]);
  expect(message.blocks?.map(block => block.id)).toEqual(all.map((_, index) => `local:${index}`));
  expect(message.blocks?.[0]).toMatchObject({ status: "running" });
  expect(message.blocks?.[1]).toMatchObject({ status: "complete", content: "检查数据范围" });
  expect(message.blocks?.[3]).toMatchObject({ status: "complete", input: '{\n  "q": 1\n}', output: '{\n  "rows": 2\n}', defaultOpen: true });
  expect(message.blocks?.[4]).toMatchObject({ items: [{ status: "pending" }, { status: "running" }, { status: "complete" }, { status: "error" }] });
  expect(message.blocks?.[5]).toMatchObject({ fromAgent: "主智能体", toAgent: "分析智能体", status: "running" });
  expect(fromStudioTurns([{ role: "user", blocks: [{ kind: "text", text: "问题" }], meta: { eventId: "user" } }, { role: "system", blocks: [] }]).map(item => [item.id, item.role])).toEqual([["user", "user"], ["turn-1", "system"]]);
});

it("keeps nested tool activity and custom override semantics", () => {
  const tool: Block = { kind: "tool", name: "sandbox", done: true, status: "failed", codexActivity: { title: "操作记录", items: [{ id: "one", block: { kind: "text", text: "保留的输出" } }] } };
  const converted = fromStudioTurns([{ role: "assistant", blocks: [tool] }])[0].blocks?.[0];
  expect(converted).toMatchObject({ type: "tool", status: "error" });
  if (converted?.type !== "tool") throw new Error("Expected tool");
  expect(isValidElement<{ blocks: { type: string; text: string; id: string }[] }>(converted.result) && converted.result.props.blocks).toEqual([{ type: "markdown", text: "保留的输出", id: "turn-0:0:one" }]);
  const override = vi.fn((block: Block) => block.kind === "text" ? null : <span>自定义</span>);
  const result = fromStudioTurns([{ role: "assistant", blocks: [{ kind: "text", text: "隐藏" }, tool] }], { renderBlock: override });
  expect(result[0].blocks?.[0]).toMatchObject({ type: "custom", content: null });
  expect(override).toHaveBeenCalledTimes(2);
});

it("preserves stored feedback without inventing missing timing metrics", () => {
  const turns: Turn[] = (["good", "bad", null] as const).map(rating => ({ role: "assistant", blocks: [], meta: { feedback: { rating, syncStatus: "synced", updatedAt: 1 } } }));
  const messages = fromStudioTurns(turns);
  expect(messages.map(message => message.role === "assistant" ? message.feedback : undefined)).toEqual(["like", "dislike", null]);
  messages.forEach(message => {
    expect(message).not.toHaveProperty("durationMs");
    expect(message).not.toHaveProperty("ttftMs");
  });
});

it("connects authorization, attachment, artifact, and delivery buttons to their original objects", async () => {
  const attachment = { id: "f1", name: "上传.csv", uri: "/upload.csv" };
  const artifact = { filename: "生成.csv", version: 1 };
  const callbacks = {
    onAuthorize: vi.fn(), onCancelAuthorization: vi.fn(), onAttachmentPreview: vi.fn(), onAttachmentDownload: vi.fn(), onArtifactPreview: vi.fn(), onArtifactDownload: vi.fn(), onDeliveryDownload: vi.fn(), onDeliveryDeploy: vi.fn(),
  };
  await renderBlocks([auth, { kind: "attachment", files: [attachment] }, { kind: "artifact", files: [artifact] }, { kind: "delivery", value: delivery }], callbacks);
  for (const label of ["授权并继续", "取消", "预览 上传.csv", "下载 上传.csv", "预览 生成.csv", "下载 生成.csv", "下载项目", "部署"]) await click(label);
  expect(callbacks.onAuthorize).toHaveBeenCalledWith(auth);
  expect(callbacks.onCancelAuthorization).toHaveBeenCalledWith(auth);
  expect(callbacks.onAttachmentPreview).toHaveBeenCalledWith(attachment);
  expect(callbacks.onAttachmentDownload).toHaveBeenCalledWith(attachment);
  expect(callbacks.onArtifactPreview).toHaveBeenCalledWith(artifact);
  expect(callbacks.onArtifactDownload).toHaveBeenCalledWith(artifact);
  expect(callbacks.onDeliveryDownload).toHaveBeenCalledWith(delivery);
  expect(callbacks.onDeliveryDeploy).toHaveBeenCalledWith(delivery);
});

it("shows resolved assistant media artifacts inline while preserving ordinary files and callbacks", async () => {
  const files = [
    { filename: "结果.PNG", version: 1 },
    { filename: "说明.txt", version: 1 },
    { filename: "演示.mp4", version: 2 },
    { filename: "录音.wav", version: 1 },
    { filename: "generated-image", version: 3 },
  ];
  const turn: Turn = { role: "assistant", blocks: [{ kind: "artifact", files }] };
  const resolveArtifactMedia = vi.fn((file: typeof files[number]) => file.filename === "说明.txt" ? undefined : {
    src: `/artifacts/${encodeURIComponent(file.filename)}`,
    mimeType: file.filename === "generated-image" ? "image/webp" : undefined,
    poster: file.filename === "演示.mp4" ? "/poster.png" : undefined,
  });
  const onArtifactPreview = vi.fn();
  const onArtifactDownload = vi.fn();
  const messages = fromStudioTurns([turn], { resolveArtifactMedia, onArtifactPreview, onArtifactDownload });
  expect(messages[0].role).toBe("assistant");
  expect(messages[0].blocks?.map(block => block.type)).toEqual(["media", "files", "media", "media", "media"]);
  expect(resolveArtifactMedia).toHaveBeenCalledWith(files[0], turn);
  await render(<ConversationBlocks blocks={messages[0].blocks ?? []} />);
  expect(host.querySelectorAll(".studio-conversation-media-block__image")).toHaveLength(2);
  expect(host.querySelector("video")?.getAttribute("poster")).toBe("/poster.png");
  expect(host.querySelector("video")?.autoplay).toBe(false);
  expect(host.querySelector("audio")?.controls).toBe(true);
  expect(host.textContent).toContain("说明.txt");
  await click("预览 演示.mp4");
  await click("下载 结果.PNG");
  expect(onArtifactPreview).toHaveBeenCalledWith(files[2]);
  expect(onArtifactDownload).toHaveBeenCalledWith(files[0]);
});

it("retains unresolved artifact entries without inventing sources and rejects unsafe resolved media", async () => {
  const files = [{ filename: "result.png", version: 1 }, { filename: "movie.mp4", version: 2 }];
  const turns: Turn[] = [{ role: "assistant", blocks: [{ kind: "artifact", files }] }];
  expect(fromStudioTurns(turns)[0].blocks?.[0]).toMatchObject({ type: "files", files: [{ name: "result.png" }, { name: "movie.mp4" }] });
  const messages = fromStudioTurns(turns, { resolveArtifactMedia: () => ({ src: "javascript:alert(1)" }) });
  await render(<ConversationBlocks blocks={messages[0].blocks ?? []} />);
  expect(host.querySelectorAll(".studio-error-state")).toHaveLength(2);
  expect(host.querySelector("img, video")).toBeNull();
});

const action = { event: { name: "confirm", context: { key: "value" } } };
function surface(): SurfaceState {
  return {
    surfaceId: "surface", rootId: "root", dataModel: { title: "确认信息" }, components: {
      root: { id: "root", component: "Card", title: "交互结果", child: "column" },
      column: { id: "column", component: "Column", children: ["text", "divider", "row"] },
      text: { id: "text", component: "Text", text: { path: "/title" } },
      divider: { id: "divider", component: "Divider" },
      row: { id: "row", component: "Row", children: ["icon", "button"] },
      icon: { id: "icon", component: "Icon", name: "check" },
      button: { id: "button", component: "Button", label: "确认操作", action, variant: "primary" },
    },
  };
}

it("renders all seven A2UI node types and dispatches real button actions", async () => {
  const original = surface();
  const onAction = vi.fn();
  await render(<ConversationSurface surface={original} onAction={onAction} />);
  expect(host.querySelector(".studio-info-card")).not.toBeNull();
  expect(host.querySelector(".studio-conversation-surface__column")).not.toBeNull();
  expect(host.querySelector(".studio-conversation-surface__row")).not.toBeNull();
  expect(host.querySelector(".studio-conversation-surface__text")?.textContent).toBe("确认信息");
  expect(host.querySelector('[role="separator"]')).not.toBeNull();
  expect(host.querySelector(".studio-conversation-surface__icon svg")).not.toBeNull();
  await click("确认操作");
  expect(onAction).toHaveBeenCalledWith(action, original.components.button);
  await render(<ConversationSurface surface={original} />);
  expect(host.querySelector<HTMLButtonElement>(".studio-button")?.disabled).toBe(true);
});

it("passes Studio surface actions through the adapter", async () => {
  const original = surface();
  const onSurfaceAction = vi.fn();
  await renderBlocks([{ kind: "a2ui", messages: [
    { createSurface: { surfaceId: "surface" } },
    { updateComponents: { surfaceId: "surface", components: Object.values(original.components) } },
    { updateDataModel: { surfaceId: "surface", path: "/title", value: "确认信息" } },
  ] }], { onSurfaceAction });
  await click("确认操作");
  expect(onSurfaceAction).toHaveBeenCalledWith(action, original.components.button);
});

it("keeps unsupported and invalid bindings visible, catches cycles, and prevents nested buttons", async () => {
  const original = surface();
  original.components.column.children = ["unknown", "cycle", "unsafe", "button", "proto-icon"];
  original.components.unknown = { id: "unknown", component: "FutureWidget", value: "原始内容" };
  original.components.cycle = { id: "cycle", component: "Row", children: ["cycle"] };
  original.components.unsafe = { id: "unsafe", component: "Text", text: { path: "/constructor" } };
  original.components["proto-icon"] = { id: "proto-icon", component: "Icon", name: "constructor" };
  original.components.button.child = "nested";
  original.components.nested = { id: "nested", component: "Button", child: "nested-content", action };
  original.components["nested-content"] = { id: "nested-content", component: "FutureWidget" };
  await render(<ConversationSurface surface={original} onAction={vi.fn()} />);
  expect(host.textContent).toContain("暂不支持 FutureWidget");
  expect(host.textContent).toContain("原始内容");
  expect(host.textContent).toContain("文本绑定无法解析");
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("卡片结构过于复杂");
  expect(host.querySelector("button button")).toBeNull();
  expect(host.querySelector(".studio-conversation-surface__icon svg circle")).not.toBeNull();
});

it("rejects prototype paths and unsafe component IDs before building surfaces without losing safe output", async () => {
  const pollutionKey = "conversationPrototypePollution";
  const safeMessage: A2uiMessage = { updateComponents: { surfaceId: "surface", components: [{ id: "root", component: "Text", text: "安全内容" }] } };
  const unsafe: A2uiMessage[] = [
    { updateDataModel: { surfaceId: "surface", path: `/__proto__/${pollutionKey}`, value: "polluted" } },
    { updateDataModel: { surfaceId: "surface", path: `/constructor/prototype/${pollutionKey}`, value: "polluted" } },
    { updateComponents: { surfaceId: "surface", components: [{ id: "__proto__", component: "Text", text: "不应应用" }] } },
    JSON.parse('{"updateDataModel":{"surfaceId":"surface","path":"/safe","value":{"__proto__":{"polluted":true}}}}'),
    { updateDataModel: { surfaceId: "surface", value: "缺少路径" } },
  ];
  try {
    await renderBlocks([{ kind: "a2ui", messages: [safeMessage, ...unsafe] }]);
    expect(Object.prototype).not.toHaveProperty(pollutionKey);
    expect(host.textContent).toContain("安全内容");
    expect(host.querySelector('[role="alert"]')?.textContent).toContain("5 条消息");
    expect(host.querySelector(".studio-code-block")?.textContent).toContain(pollutionKey);
    expect(host.querySelector(".studio-code-block")?.textContent).toContain("缺少路径");
  } finally {
    Reflect.deleteProperty(Object.prototype, pollutionKey);
  }
});

it("does not mutate prior event values while applying later data model updates", async () => {
  const value = { name: "原始" };
  await renderBlocks([{ kind: "a2ui", messages: [
    { createSurface: { surfaceId: "surface" } },
    { updateComponents: { surfaceId: "surface", components: [{ id: "root", component: "Text", text: { path: "/object/name" } }] } },
    { updateDataModel: { surfaceId: "surface", path: "/object", value } },
    { updateDataModel: { surfaceId: "surface", path: "/object/name", value: "更新" } },
  ] }]);
  expect(value.name).toBe("原始");
  expect(host.textContent).toContain("更新");
});

it("never renders executable attachment and authorization URLs", async () => {
  await renderBlocks([
    { kind: "attachment", files: [{ id: "bad", name: "危险图片", mimeType: "image/svg+xml", uri: "javascript:alert(1)", data: "PHN2Zz4=" }, { id: "safe", name: "安全图片", mimeType: "image/png", uri: "https://example.com/image.png" }] },
    { ...auth, authUri: "javascript:alert(1)" },
    { kind: "text", text: "[危险链接](javascript:alert(1))" },
  ]);
  expect(host.querySelector('[href^="javascript:"], [src^="javascript:"], [src^="data:image/svg"]')).toBeNull();
  expect(host.querySelector('[aria-label="预览 危险图片"]')).toBeNull();
  expect(host.querySelector(".studio-conversation-media-block__image")?.getAttribute("src")).toBe("https://example.com/image.png");
  expect(host.querySelector(".studio-conversation-media-block__error")?.textContent).toContain("图片无法加载");
});

it("keeps mixed attachments inline and in order with their original callbacks", async () => {
  const image = { id: "image", name: "设计参考.png", mimeType: "image/png", uri: "/reference.png" };
  const video = { id: "video", name: "操作演示.mp4", mimeType: "video/mp4", uri: "/walkthrough.mp4" };
  const audio = { id: "audio", name: "需求录音.wav", mimeType: "audio/wav", data: "UklGRg==" };
  const firstFile = { id: "first", name: "说明.txt", uri: "/notes.txt" };
  const lastFile = { id: "last", name: "补充.csv", uri: "/data.csv" };
  const onAttachmentPreview = vi.fn();
  const onAttachmentDownload = vi.fn();
  const messages = fromStudioTurns([{ role: "user", blocks: [
    { kind: "text", text: "结合附件整理需求" },
    { kind: "attachment", files: [firstFile, image, video, lastFile, audio] },
  ] }], { onAttachmentPreview, onAttachmentDownload });
  expect(messages[0].blocks?.map(block => block.type)).toEqual(["markdown", "files", "media", "media", "files", "media"]);
  expect(new Set(messages[0].blocks?.map(block => block.id)).size).toBe(6);
  await render(<ConversationBlocks blocks={messages[0].blocks ?? []} />);
  expect(host.querySelector("img")?.getAttribute("src")).toBe("/reference.png");
  const videoElement = host.querySelector("video");
  expect(videoElement?.controls).toBe(true);
  expect(videoElement?.autoplay).toBe(false);
  expect(videoElement?.preload).toBe("metadata");
  expect(host.querySelector("audio")?.getAttribute("src")).toBe("data:audio/wav;base64,UklGRg==");
  expect(host.querySelector("audio")?.controls).toBe(true);
  await click("预览 操作演示.mp4");
  await click("下载 设计参考.png");
  expect(onAttachmentPreview).toHaveBeenCalledWith(video);
  expect(onAttachmentDownload).toHaveBeenCalledWith(image);
});

it("opens image attachments in the shared modal and preserves their theme", async () => {
  const image = { id: "image", name: "设计参考.png", mimeType: "image/png", uri: "/reference.png" };
  const onAttachmentPreview = vi.fn();
  host.dataset.theme = "light";
  await renderBlocks([{ kind: "attachment", files: [image] }], { onAttachmentPreview });
  await click("放大 设计参考.png");
  expect(onAttachmentPreview).toHaveBeenCalledWith(image);
  expect(document.querySelector('.studio-conversation-media-block__modal[data-theme="light"]')).not.toBeNull();
  expect(document.querySelector(".studio-conversation-media-block__expanded-image")?.getAttribute("src")).toBe("/reference.png");
  const close = document.querySelector<HTMLButtonElement>('[aria-label="关闭图片"]');
  expect(close).not.toBeNull();
  await act(async () => close!.click());
  expect(document.querySelector('.studio-conversation-media-block__modal[data-open]')).toBeNull();
});

it("renders failed media through ErrorState and recovers when the source changes", async () => {
  await render(<ConversationBlocks blocks={[{ id: "video", type: "media", kind: "video", src: "/broken.mp4", poster: "javascript:alert(1)" }]} />);
  expect(host.querySelector("video")?.hasAttribute("poster")).toBe(false);
  await act(async () => host.querySelector("video")!.dispatchEvent(new Event("error")));
  expect(host.querySelector(".studio-error-state")?.textContent).toContain("视频无法加载");
  await render(<ConversationBlocks blocks={[{ id: "video", type: "media", kind: "video", src: "/fixed.mp4", poster: "/poster.png" }]} />);
  expect(host.querySelector("video")?.getAttribute("src")).toBe("/fixed.mp4");
  expect(host.querySelector("video")?.getAttribute("poster")).toBe("/poster.png");
  expect(host.querySelector(".studio-error-state")).toBeNull();
});

it("rejects mismatched data media and executable URLs in direct media blocks", async () => {
  await render(<ConversationBlocks blocks={[
    { id: "script", type: "media", kind: "image", src: "javascript:alert(1)" },
    { id: "svg", type: "media", kind: "image", src: "data:image/svg+xml;base64,PHN2Zz4=" },
    { id: "wrong", type: "media", kind: "video", src: "data:text/html;base64,PHN2Zz4=" },
    { id: "protocol", type: "media", kind: "video", src: "//example.com/video.mp4" },
    { id: "safe", type: "media", kind: "image", src: "data:image/png;base64,iVBORw0KGgo=" },
  ]} />);
  expect(host.querySelectorAll(".studio-error-state")).toHaveLength(4);
  expect(host.querySelectorAll("img")).toHaveLength(1);
  expect(host.querySelector("img")?.getAttribute("src")).toBe("data:image/png;base64,iVBORw0KGgo=");
  expect(host.querySelector("video")).toBeNull();
});
