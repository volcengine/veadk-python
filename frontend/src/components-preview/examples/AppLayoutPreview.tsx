import { useRef, useState } from "react";
import { AppLayout } from "../../components/layouts/AppLayout";
import { IndexLayout } from "../../components/layouts/IndexLayout";
import { GlassTabs } from "../../components/primitives/GlassTabs";
import { Menu } from "../../components/primitives/Menu";
import { Button } from "../../components/primitives/Button";
import { EmptyState } from "../../components/primitives/EmptyState";
import { ToastProvider, useToast } from "../../components/primitives/Toast";
import { Drawer } from "../../components/composites/Drawer";
import { ModalButton } from "../../components/composites/ModalButton";
import { Item } from "../../components/composites/Item";
import { PromptInput } from "../../components/ai-app/PromptInput";
import blocksIcon from "../../components/layouts/IndexLayout/assets/blocks.svg";
import codepenIcon from "../../components/layouts/IndexLayout/assets/codepen.svg";

import { promptPlaceholders } from "./promptInputExamples";
import { useSidebarPreviewState } from "./sidebarPreviewState";
import "./AppLayoutPreview.css";
import "./IndexLayoutPreview.css";

function AppLayoutExample({ fullscreen = false }: { fullscreen?: boolean }) {
  const { sidebar, heading, provider, setProvider, state, setState, reset, notifications, setNotifications } = useSidebarPreviewState();
  const [mode, setMode] = useState("development");
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const toast = useToast();
  const showNotice = (title: string) => toast.add({ title });

  return <section className="app-layout-preview" data-fullscreen={fullscreen || undefined} aria-label="完整侧栏预览">
    <div className="app-layout-preview__toolbar">
      {fullscreen ? <h1>App Layout</h1> : <h2 data-preview-heading tabIndex={-1} id="app-layout-default-title">Default</h2>}
      <div className="app-layout-preview__controls">
        <Menu label={provider === "volcengine" ? "火山引擎" : "BytePlus"} items={[{ type: "radio-group", id: "provider", value: provider, onValueChange: setProvider,
          items: [{ id: "volcengine", label: "火山引擎" }, { id: "byteplus", label: "BytePlus" }] }]} />
        <Menu label="会话状态" items={[{ type: "radio-group", id: "state", value: state, onValueChange: setState,
          items: [{ id: "ready", label: "正常" }, { id: "loading", label: "加载中" }, { id: "empty", label: "空状态" }, { id: "error", label: "加载失败" }] }]} />
        <Button variant="link" onClick={reset}>重置示例</Button>
        <ModalButton label="查看弹窗" title="组件库弹窗" buttonProps={{ variant: "secondary" }}>
          <EmptyState title="统一的 Modal" description="弹窗随账号菜单中的外观选择同步切换" icon={null} />
        </ModalButton>
        {!fullscreen && <a href="?fullscreen=app-layout#app-layout" target="_blank" rel="noreferrer">全屏预览</a>}
        {fullscreen && <a href="./#app-layout">组件目录</a>}
      </div>
    </div>
    <AppLayout height={fullscreen ? "100%" : 760} sidebar={sidebar}>
      <IndexLayout heading={heading} tabs={<GlassTabs aria-label="Workspace mode" items={[{ value: "development", label: "Development" }, { value: "daily-work", label: "Daily Work" }]} value={mode} onValueChange={setMode} />}
        prompt={<PromptInput ref={promptRef} placeholders={promptPlaceholders} aria-label="Describe your task" onSend={() => showNotice("已发送示例任务")} />}
        shortcuts={<>
          <Item variant="compact" title="From template" description="Create from a template" onAction={() => promptRef.current?.focus()}
            icon={<span className="index-layout-preview__shortcut-icon" style={{ maskImage: `url(${blocksIcon})` }} />} />
          <Item variant="compact" title="Upload code" description="View and one-click deploy" onAction={() => promptRef.current?.focus()} />
          <Item variant="compact" title="Migrate existing" description="Migrate from LangChain" onAction={() => promptRef.current?.focus()}
            icon={<span className="index-layout-preview__shortcut-icon" style={{ maskImage: `url(${codepenIcon})` }} />} />
        </>} />
    </AppLayout>
    <Drawer open={notifications} onOpenChange={setNotifications} title="通知"><EmptyState title="暂无新通知" description="新的通知会显示在这里" /></Drawer>
  </section>;
}

export function AppLayoutPreview({ fullscreen = false }: { fullscreen?: boolean }) {
  return <ToastProvider><AppLayoutExample fullscreen={fullscreen} /></ToastProvider>;
}
