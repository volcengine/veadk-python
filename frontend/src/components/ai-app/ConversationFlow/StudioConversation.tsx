import type { ReactNode } from "react";
import type { AttachmentView, Block, Turn } from "../../../blocks";
import type { A2uiAction, A2uiComponent, A2uiMessage } from "../../../a2ui/types";
import { buildSurfaces } from "../../../a2ui/Surface";
import { artifactTypeFor } from "../../../ui/artifactLibraryModel";
import { Button } from "../../primitives/Button";
import { CodeBlock } from "../../composites/CodeBlock";
import { InfoCard, InfoCardBody } from "../../composites/InfoCard";
import { FileExplorer } from "../../composites/FileExplorer";
import { ConversationSurface } from "./ConversationSurface";
import { ConversationBlocks } from "./ConversationBlocks";
import { safeConversationMediaSource } from "./ConversationMedia";
import type { ConversationBlock, ConversationFile, ConversationMediaBlock, ConversationMessage } from "./ConversationFlow.types";

type ArtifactFile = Extract<Block, { kind: "artifact" }>["files"][number];
type Delivery = Extract<Block, { kind: "delivery" }>["value"];
type AuthBlock = Extract<Block, { kind: "auth" }>;

export interface StudioConversationOptions {
  /** 覆盖领域专属内容，例如部署与版本比较；undefined 使用默认组件，null 隐藏 */
  renderBlock?: (block: Block, turn: Turn) => ReactNode | undefined;
  onSurfaceAction?: (action: A2uiAction | undefined, node: A2uiComponent) => void;
  onAuthorize?: (block: AuthBlock) => void;
  onCancelAuthorization?: (block: AuthBlock) => void;
  onArtifactPreview?: (file: ArtifactFile) => void;
  onArtifactDownload?: (file: ArtifactFile) => void;
  /** 将已取得的产物媒体地址交给组件直接展示；未提供地址时保留文件预览入口 */
  resolveArtifactMedia?: (file: ArtifactFile, turn: Turn) => {
    src: string;
    kind?: ConversationMediaBlock["kind"];
    mimeType?: string;
    alt?: string;
    poster?: string;
    caption?: string;
  } | undefined;
  onAttachmentPreview?: (file: AttachmentView) => void;
  onAttachmentDownload?: (file: AttachmentView) => void;
  onDeliveryDownload?: (delivery: Delivery) => void;
  onDeliveryDeploy?: (delivery: Delivery) => void;
}

function code(value: unknown): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value === "string") return value;
  const seen = new WeakSet<object>();
  return JSON.stringify(value, (_key, item: unknown) => {
    if (typeof item === "bigint") return String(item);
    if (item && typeof item === "object") {
      if (seen.has(item)) return "[循环引用]";
      seen.add(item);
    }
    return item;
  }, 2);
}

const unsafeKeys = new Set(["__proto__", "constructor", "prototype"]);
function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** Validate before passing wire data to the legacy mutable JSON Pointer setter */
function safeSurfaceData(value: unknown, ancestors = new Set<object>(), depth = 0): boolean {
  if (depth > 30) return false;
  if (value === null || typeof value === "string" || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value !== "object") return false;
  if (ancestors.has(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  if (!Array.isArray(value) && prototype !== Object.prototype && prototype !== null) return false;
  const next = new Set(ancestors).add(value);
  return Object.entries(value).every(([key, child]) => !unsafeKeys.has(key) && safeSurfaceData(child, next, depth + 1));
}

function safeSurfaceMessage(message: A2uiMessage): boolean {
  if (!record(message) || !safeSurfaceData(message)) return false;
  const kinds = ["createSurface", "updateComponents", "updateDataModel", "deleteSurface"].filter(key => Object.prototype.hasOwnProperty.call(message, key));
  if (kinds.length !== 1) return false;
  const kind = kinds[0];
  const payload = message[kind];
  if (!record(payload) || typeof payload.surfaceId !== "string" || !payload.surfaceId) return false;
  if (kind === "updateComponents") {
    return Array.isArray(payload.components) && payload.components.every(component => record(component)
      && typeof component.id === "string" && !!component.id && !unsafeKeys.has(component.id)
      && typeof component.component === "string" && !!component.component);
  }
  if (kind === "updateDataModel") {
    return typeof payload.path === "string"
      && (payload.path === "" || payload.path.startsWith("/"))
      && payload.path.split("/").length <= 32
      && !payload.path.split("/").some(token => unsafeKeys.has(token.replace(/~1/g, "/").replace(/~0/g, "~")))
      && Object.prototype.hasOwnProperty.call(payload, "value");
  }
  return true;
}

function SurfaceContent({ messages, onAction }: { messages: A2uiMessage[]; onAction: StudioConversationOptions["onSurfaceAction"] }) {
  const accepted: A2uiMessage[] = [];
  const rejected: A2uiMessage[] = [];
  messages.forEach(message => (safeSurfaceMessage(message) ? accepted : rejected).push(message));
  // buildSurfaces mutates nested model values; clone validated JSON to preserve the event projection
  const surfaces = buildSurfaces(JSON.parse(JSON.stringify(accepted)) as A2uiMessage[]);
  return <>
    {surfaces.map(surface => <ConversationSurface key={surface.surfaceId} surface={surface} onAction={onAction} />)}
    {rejected.length > 0 && <InfoCard title="部分交互内容无法显示">
      <InfoCardBody description={<span role="alert">{rejected.length} 条消息包含无效结构或不安全的数据路径，原始内容保留在下方</span>}>
        <CodeBlock title="未渲染的交互消息" language="json" lines={[code(rejected) ?? ""]} wordWrap scrollAreaProps={{ maxHeight: 240 }} />
      </InfoCardBody>
    </InfoCard>}
  </>;
}

function mediaSource(file: AttachmentView): string | undefined {
  const uri = file.previewUrl ?? file.uri;
  if (uri && /^(?:https?:\/\/|blob:|\/(?!\/))/.test(uri)) return uri;
  if (file.data && /^(?:image\/(?:png|jpeg|gif|webp|avif)|audio\/[\w.+-]+|video\/[\w.+-]+)$/.test(file.mimeType ?? "")) {
    return `data:${file.mimeType};base64,${file.data}`;
  }
  return undefined;
}

function attachmentBlocks(files: AttachmentView[], id: string, options: StudioConversationOptions): ConversationBlock[] {
  const result: ConversationBlock[] = [];
  let pendingFiles: ConversationFile[] = [];
  function flushFiles() {
    if (!pendingFiles.length) return;
    result.push({ id: result.length ? `${id}:files:${pendingFiles[0].id}` : id, type: "files", files: pendingFiles });
    pendingFiles = [];
  }
  for (const file of files) {
    const mimeKind = file.mimeType?.toLowerCase().split("/")[0];
    const kind: ConversationMediaBlock["kind"] | undefined = mimeKind === "image" || mimeKind === "video" || mimeKind === "audio" ? mimeKind : undefined;
    const source = mediaSource(file);
    const onPreview = options.onAttachmentPreview ? () => options.onAttachmentPreview?.(file) : undefined;
    const onDownload = options.onAttachmentDownload ? () => options.onAttachmentDownload?.(file) : undefined;
    if (kind) {
      flushFiles();
      result.push({ id: `${id}:${file.id}`, type: "media", kind, src: safeConversationMediaSource(source, kind) ?? "", name: file.name, onPreview, onDownload });
    } else {
      pendingFiles.push({ id: file.id, name: file.name ?? "附件", description: file.mimeType, href: source, onPreview, onDownload });
    }
  }
  flushFiles();
  return result;
}

function artifactBlocks(files: ArtifactFile[], turn: Turn, id: string, options: StudioConversationOptions): ConversationBlock[] {
  const result: ConversationBlock[] = [];
  let pendingFiles: ConversationFile[] = [];
  function flushFiles() {
    if (!pendingFiles.length) return;
    result.push({ id: result.length ? `${id}:files:${pendingFiles[0].id}` : id, type: "files", title: "生成的文件", files: pendingFiles });
    pendingFiles = [];
  }
  for (const file of files) {
    const media = options.resolveArtifactMedia?.(file, turn);
    const mimeKind = media?.mimeType?.toLowerCase().split("/")[0];
    const inferredType = artifactTypeFor(file.filename);
    const extensionKind = inferredType === "image" || inferredType === "video" ? inferredType
      : /\.(?:mp3|m4a|aac|wav|ogg|oga|flac|opus)$/i.test(file.filename) ? "audio" : undefined;
    const kind = media?.kind ?? (mimeKind === "image" || mimeKind === "video" || mimeKind === "audio" ? mimeKind : extensionKind);
    const onPreview = options.onArtifactPreview ? () => options.onArtifactPreview?.(file) : undefined;
    const onDownload = options.onArtifactDownload ? () => options.onArtifactDownload?.(file) : undefined;
    if (media && kind) {
      flushFiles();
      result.push({
        id: `${id}:${file.filename}:${file.version}`, type: "media", kind,
        src: safeConversationMediaSource(media.src, kind) ?? "", name: file.filename,
        alt: media.alt, poster: media.poster, caption: media.caption, onPreview, onDownload,
      });
    } else {
      pendingFiles.push({ id: `${file.filename}:${file.version}`, name: file.filename, description: `版本 ${file.version}`, onPreview, onDownload });
    }
  }
  flushFiles();
  return result;
}

function DeliveryContent({ delivery, options }: { delivery: Delivery; options: StudioConversationOptions }) {
  return <InfoCard title={delivery.agentName} className="studio-conversation-delivery">
    <InfoCardBody description={`${delivery.fileCount} 个文件 · ${delivery.entryPoint}`}>
      {delivery.files?.length ? <FileExplorer entries={delivery.files.map(file => ({ id: file.path, name: file.path, type: "file" as const, content: file.content }))} defaultSelectedId={delivery.files[0]?.path} style={{ height: 320 }} /> : null}
      <div className="studio-conversation-delivery__actions">
        {options.onDeliveryDownload && <Button variant="secondary" onClick={() => options.onDeliveryDownload?.(delivery)}>下载项目</Button>}
        {options.onDeliveryDeploy && <Button onClick={() => options.onDeliveryDeploy?.(delivery)}>部署</Button>}
      </div>
    </InfoCardBody>
  </InfoCard>;
}

/** Convert the existing Studio event projection without rearranging or dropping block kinds */
export function fromStudioTurns(turns: readonly Turn[], options: StudioConversationOptions = {}): ConversationMessage[] {
  function convert(block: Block, turn: Turn, id: string): ConversationBlock | ConversationBlock[] {
    const custom = options.renderBlock?.(block, turn);
    if (custom !== undefined) return { id, type: "custom", content: custom };
    switch (block.kind) {
      case "text": return { id, type: "markdown", text: block.text };
      case "thinking": return { id, type: "reasoning", title: "思考过程", status: block.done ? "complete" : "running", content: block.text };
      case "progress": return { id, type: "reasoning", title: block.text, status: turn.meta?.streaming ? "running" : "complete", content: block.text };
      case "tool": return {
        id, type: "tool", title: block.name,
        status: block.status === "failed" ? "error" : block.status === "running" ? "running" : block.status === "completed" || block.done ? "complete" : "running",
        input: code(block.args), output: code(block.response), defaultOpen: block.defaultOpen,
        result: block.codexActivity ? <ConversationBlocks blocks={block.codexActivity.items.flatMap(item => convert(item.block, turn, `${id}:${item.id}`))} streaming={turn.meta?.streaming} /> : undefined,
      };
      case "plan": return { id, type: "plan", title: block.title, items: block.items.map((item, index) => ({ id: `${id}:${index}`, title: item.text, status: item.status === "in_progress" ? "running" : item.status === "completed" ? "complete" : item.status === "failed" ? "error" : "pending" })) };
      case "agent-transfer": return { id, type: "handoff", title: "移交子智能体", fromAgent: turn.meta?.author, toAgent: block.agentName, status: block.done ? "complete" : "running" };
      case "attachment": return attachmentBlocks(block.files, id, options);
      case "artifact": return artifactBlocks(block.files, turn, id, options);
      case "delivery": return { id, type: "custom", content: <DeliveryContent delivery={block.value} options={options} /> };
      case "invocation": return { id, type: "custom", content: <div className="studio-conversation-invocation">
        {block.value.targetAgent && <span title={block.value.targetAgent.description}>@{block.value.targetAgent.name}</span>}
        {block.value.skills.map(skill => <span key={skill.name} title={skill.description}>/{skill.name}</span>)}
      </div> };
      case "auth": return { id, type: "authorization", title: block.label ? `连接 ${block.label}` : "工具授权", description: "授权后继续执行当前工具", status: block.done ? "complete" : "pending", onAuthorize: options.onAuthorize ? () => options.onAuthorize?.(block) : undefined, onCancel: options.onCancelAuthorization ? () => options.onCancelAuthorization?.(block) : undefined };
      case "a2ui": return { id, type: "custom", content: <SurfaceContent messages={block.messages} onAction={options.onSurfaceAction} /> };
      default: {
        const exhaustive: never = block;
        return { id, type: "custom", content: <CodeBlock title="未识别的消息" lines={[code(exhaustive) ?? ""]} language="json" /> };
      }
    }
  }

  return turns.map((turn, index) => {
    const id = turn.meta?.localId ?? turn.meta?.eventId ?? `turn-${index}`;
    const blocks = turn.blocks.flatMap((block, blockIndex) => convert(block, turn, `${id}:${blockIndex}`));
    if (turn.role !== "assistant") return { id, role: turn.role, blocks, name: turn.meta?.author };
    const rating = turn.meta?.feedback?.rating;
    return { id, role: "assistant", name: turn.meta?.author, blocks, status: turn.meta?.streaming ? "running" : "complete", tokens: turn.meta?.tokens, feedback: rating === "good" ? "like" : rating === "bad" ? "dislike" : null };
  });
}
