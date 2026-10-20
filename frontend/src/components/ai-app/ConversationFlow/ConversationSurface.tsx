import { useMemo, type ReactNode } from "react";
import type { A2uiAction, A2uiComponent, SurfaceState } from "../../../a2ui/types";
import { resolveString } from "../../../a2ui/bind";
import { Button } from "../../primitives/Button";
import { Divider } from "../../primitives/Divider";
import { Dropdown } from "../../primitives/Dropdown";
import { CodeBlock } from "../../composites/CodeBlock";
import { InfoCard, InfoCardBody } from "../../composites/InfoCard";
import "./ConversationSurface.css";

export interface ConversationSurfaceProps {
  /** 使用 Studio buildSurfaces 生成的 A2UI surface，当前支持七种基础节点 */
  surface: SurfaceState;
  /** 将点击事件交回业务；未传时禁用交互按钮 */
  onAction?: (action: A2uiAction | undefined, node: A2uiComponent) => void;
}

const unsafeKeys = new Set(["__proto__", "constructor", "prototype"]);
function safeBinding(value: unknown, depth = 0): boolean {
  if (depth > 20) return false;
  if (!value || typeof value !== "object") return true;
  const object = value as Record<string, unknown>;
  if (typeof object.path === "string" && object.path.split("/").some(part => unsafeKeys.has(part.replace(/~1/g, "/").replace(/~0/g, "~")))) return false;
  if (object.call !== undefined && object.call !== "formatDate") return false;
  return Object.entries(object).every(([key, child]) => !unsafeKeys.has(key) && safeBinding(child, depth + 1));
}

function SurfaceIcon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    check: <path d="m3 8 3 3 7-7" />,
    close: <path d="m4 4 8 8m0-8-8 8" />,
    send: <path d="m2 2 12 6-12 6 2-6-2-6Zm2 6h10" />,
    info: <><circle cx="8" cy="8" r="6" /><path d="M8 7v4m0-7v.5" /></>,
    error: <><circle cx="8" cy="8" r="6" /><path d="M8 4v5m0 2v.5" /></>,
    help: <><circle cx="8" cy="8" r="6" /><path d="M6 6a2 2 0 1 1 3 1.7C8 8.3 8 8.5 8 9m0 2v.5" /></>,
    schedule: <><circle cx="8" cy="8" r="6" /><path d="M8 4v4l3 2" /></>,
    calendarToday: <><rect x="2" y="3" width="12" height="11" rx="2" /><path d="M5 1v4m6-4v4M2 7h12" /></>,
    accountCircle: <><circle cx="8" cy="8" r="6" /><circle cx="8" cy="6" r="2" /><path d="M4 12c.5-3 7.5-3 8 0" /></>,
    mail: <><rect x="2" y="3" width="12" height="10" rx="2" /><path d="m2 4 6 5 6-5" /></>,
    search: <><circle cx="7" cy="7" r="4.5" /><path d="m10.5 10.5 3 3" /></>,
    home: <path d="m1 7 7-6 7 6M3 6v8h4v-4h2v4h4V6" />,
    locationOn: <><path d="M13 6c0 4-5 8-5 8S3 10 3 6a5 5 0 0 1 10 0Z" /><circle cx="8" cy="6" r="1.5" /></>,
    favorite: <path d="M8 14 2 8C-2 3 5-1 8 4c3-5 10-1 6 4Z" />,
    star: <path d="m8 1 2 4.5 5 .5-3.8 3.4 1.1 5L8 12l-4.3 2.4 1.1-5L1 6l5-.5Z" />,
    call: <path d="m4 1 3 4-2 2c1 2 2 3 4 4l2-2 4 3-1 3C7 16 0 9 1 2Z" />,
    settings: <><circle cx="8" cy="8" r="2.5" /><path d="m6 1-.5 2-2 .8L2 3 1 5l1.5 1.5v3L1 11l1 2 1.5-.8 2 .8.5 2h4l.5-2 2-.8 1.5.8 1-2-1.5-1.5v-3L15 5l-1-2-1.5.8-2-.8L10 1Z" /></>,
  };
  const key = name === "event" ? "calendarToday" : name;
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{Object.prototype.hasOwnProperty.call(paths, key) ? paths[key] : <circle cx="8" cy="8" r="2" />}</svg>;
}

export function ConversationSurface({ surface, onAction }: ConversationSurfaceProps) {
  const content = useMemo(() => {
    let count = 0;
    function text(value: unknown): string | undefined {
      if (!safeBinding(value)) return undefined;
      try { return resolveString(value, surface.dataModel); } catch { return undefined; }
    }
    function fallback(node: A2uiComponent, message: string, insideButton = false) {
      if (insideButton) return <span key={node.id} role="status">{message}</span>;
      const seen = new WeakSet<object>();
      const source = JSON.stringify(node, (_key, item: unknown) => {
        if (item && typeof item === "object") {
          if (seen.has(item)) return "[循环引用]";
          seen.add(item);
        }
        return typeof item === "bigint" ? String(item) : item;
      }, 2);
      return <Dropdown key={node.id} className="studio-conversation-surface__fallback" label={message}>
        <CodeBlock title="JSON" language="json" lines={[source]} wordWrap scrollAreaProps={{ maxHeight: 200 }} />
      </Dropdown>;
    }
    function render(id: unknown, ancestors: readonly string[] = [], insideButton = false): ReactNode {
      if (id === undefined || id === null) return null;
      if (typeof id !== "string" || unsafeKeys.has(id) || !Object.prototype.hasOwnProperty.call(surface.components, id)) return <span key={String(id)} role="alert">卡片节点不存在，无法显示</span>;
      const node = surface.components[id];
      if (ancestors.includes(id) || ancestors.length > 24 || ++count > 500) return <span key={id} role="alert">卡片结构过于复杂，无法显示</span>;
      const next = [...ancestors, id];
      const child = () => render(node.child, next, insideButton);
      const children = () => Array.isArray(node.children) ? node.children.map(item => render(item, next, insideButton)) : null;
      switch (node.component) {
        case "Text": {
          const heading = typeof node.variant === "string" && /^h[1-5]$/.test(node.variant);
          const value = text(node.text);
          return value === undefined ? fallback(node, "文本绑定无法解析", insideButton) : <span key={id} className={`studio-conversation-surface__text${heading ? " studio-conversation-surface__heading" : ""}`}>{value}</span>;
        }
        case "Row":
        case "Column": {
          const Tag = insideButton ? "span" : "div";
          return <Tag key={id} className={`studio-conversation-surface__${node.component.toLowerCase()}`} data-align={String(node.align ?? "stretch")} data-justify={String(node.justify ?? "start")}>{children()}</Tag>;
        }
        case "Card":
          if (insideButton) return <span key={id}>{child()}</span>;
          return <InfoCard key={id} className="studio-conversation-surface__card" title={text(node.title) || "交互卡片"}><InfoCardBody>{child()}</InfoCardBody></InfoCard>;
        case "Divider":
          return insideButton ? null : <Divider key={id} />;
        case "Icon":
          return text(node.name) === undefined ? fallback(node, "图标绑定无法解析", insideButton) : <span key={id} className="studio-conversation-surface__icon"><SurfaceIcon name={text(node.name) ?? ""} /></span>;
        case "Button":
          if (insideButton) return <span key={id}>{child()}</span>;
          return <Button key={id} variant={node.variant === "primary" ? "primary" : node.variant === "borderless" ? "ghost" : "secondary"} disabled={!onAction || node.disabled === true} onClick={() => onAction?.(node.action as A2uiAction | undefined, node)}>{render(node.child, next, true) ?? (text(node.label) || "确认")}</Button>;
        default: return fallback(node, `暂不支持 ${node.component}`, insideButton);
      }
    }
    return render(surface.rootId);
  }, [surface, onAction]);
  return <div className="studio-conversation-surface" data-surface-id={surface.surfaceId}>{content}</div>;
}
