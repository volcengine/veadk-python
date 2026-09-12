import { EmptyStatePreview } from "./examples/EmptyStatePreview";
import { ErrorStatePreview } from "./examples/ErrorStatePreview";
import { LongRunningStatePreview } from "./examples/LongRunningStatePreview";
import { ModalButtonPreview } from "./examples/ModalButtonPreview";
import { DrawerPreview } from "./examples/DrawerPreview";
import { FileExplorerPreview } from "./examples/FileExplorerPreview";
import { FileUploadPreview } from "./examples/FileUploadPreview";
import { SliderPreview } from "./examples/SliderPreview";
import { IndexLayoutPreview } from "./examples/IndexLayoutPreview";
import { DatePickerPreview } from "./examples/DatePickerPreview";
import { LoadingPreview } from "./examples/LoadingPreview";
import { ToastPreview } from "./examples/ToastPreview";
import { TablePreview } from "./examples/TablePreview";
import { RadioPreview } from "./examples/RadioPreview";
import { InputWithHeaderIconPreview } from "./examples/InputWithHeaderIconPreview";
import { LoadMoreAreaPreview } from "./examples/LoadMoreAreaPreview";
import { ScrollArea } from "../components/primitives/ScrollArea";
import { ScrollAreaPreview } from "./examples/ScrollAreaPreview";
import { DividerPreview } from "./examples/DividerPreview";
import { DropdownPreview } from "./examples/DropdownPreview";
import { MenuPreview } from "./examples/MenuPreview";
import { PromptInputPreview } from "./examples/PromptInputPreview";
import { useState, useSyncExternalStore } from "react";
import { ButtonsPreview, CardsPreview, TabsPreview, InputWithTailIconPreview, ItemPreview, LabelPreview, SidebarPreview, SwitchPreview, CheckboxPreview, FormFieldPreview, DashedZonePreview, CodeBlockPreview, ModalLayoutPreview, HeaderPreview, PillTagPreview, FormLabelPreview, ResourcePageLayoutPreview, DetailPageLayoutPreview, TextareaPreview, SelectPreview, BasicNodePreview, AgentNodePreview, CanvasBackgroundPreview, TokensPreview } from "./examples";
import { applyPreviewTheme, readPreviewTheme, type PreviewTheme } from "./theme";
import "./components-preview.css";

const examples = [
  { id: "date-picker", label: "Date Picker", Preview: DatePickerPreview, group: "primitives" },
  { id: "index-layout", label: "Index layout", Preview: IndexLayoutPreview, group: "layouts" },
  { id: "slider", label: "Slider", Preview: SliderPreview, group: "primitives" },
  { id: "file-upload", label: "File Upload", Preview: FileUploadPreview, group: "composites" },
  { id: "modal-button", label: "Modal Button", Preview: ModalButtonPreview, group: "composites" },
  { id: "drawer", label: "Drawer", Preview: DrawerPreview, group: "composites" },
  { id: "file-explorer", label: "File Explorer", Preview: FileExplorerPreview, group: "composites" },
  { id: "long-running-state", label: "Long-running State", Preview: LongRunningStatePreview, group: "composites" },
  { id: "empty-state", label: "Empty State", Preview: EmptyStatePreview, group: "primitives" },
  { id: "error-state", label: "Error State", Preview: ErrorStatePreview, group: "primitives" },
  { id: "loading", label: "Loading", Preview: LoadingPreview, group: "primitives" },
  { id: "toast", label: "Toast", Preview: ToastPreview, group: "primitives" },
  { id: "table", label: "Table", Preview: TablePreview, group: "primitives" },
  { id: "load-more", label: "下拉加载", Preview: LoadMoreAreaPreview, group: "composites" },
  { id: "scroll-area", label: "Scroll Area", Preview: ScrollAreaPreview, group: "primitives" },
  { id: "divider", label: "分割线", Preview: DividerPreview, group: "primitives" },
  { id: "dropdown", label: "Dropdown", Preview: DropdownPreview, group: "primitives" },
  { id: "prompt-input", label: "Prompt Input", Preview: PromptInputPreview, group: "ai-app" },
  { id: "tokens", label: "Tokens", Preview: TokensPreview, group: "design" },
  { id: "canvas-background", label: "画布背景", Preview: CanvasBackgroundPreview, group: "nodes" },
  { id: "agent-node", label: "Agent 节点", Preview: AgentNodePreview, group: "nodes" },
  { id: "basic-node", label: "普通节点", Preview: BasicNodePreview, group: "nodes" },
  { id: "select", label: "Select", Preview: SelectPreview, group: "primitives" },
  { id: "menu", label: "Menu", Preview: MenuPreview, group: "primitives" },
  { id: "textarea", label: "Textarea", Preview: TextareaPreview, group: "primitives" },
  { id: "detail-page-layout", label: "Detail page", Preview: DetailPageLayoutPreview, group: "layouts" },
  { id: "form-label", label: "Form label", Preview: FormLabelPreview, group: "primitives" },
  { id: "resource-page-layout", label: "Resource page", Preview: ResourcePageLayoutPreview, group: "layouts" },
  { id: "pill-tag", label: "Pill tag", Preview: PillTagPreview, group: "primitives" },
  { id: "card", label: "Card", Preview: CardsPreview, group: "composites" },
  { id: "header", label: "Header", Preview: HeaderPreview, group: "composites" },
  { id: "modal-layout", label: "Modal layout", Preview: ModalLayoutPreview, group: "layouts" },
  { id: "code-block", label: "Code block", Preview: CodeBlockPreview, group: "composites" },
  { id: "button", label: "Button", Preview: ButtonsPreview, group: "primitives" },
  { id: "tabs", label: "Tabs", Preview: TabsPreview, group: "primitives" },
  { id: "input-tail-icon", label: "Input with tail icon", Preview: InputWithTailIconPreview, group: "primitives" },
  { id: "input-header-icon", label: "Input with header icon", Preview: InputWithHeaderIconPreview, group: "primitives" },
  { id: "label", label: "Label", Preview: LabelPreview, group: "primitives" },
  { id: "switch", label: "Switch", Preview: SwitchPreview, group: "primitives" },
  { id: "checkbox", label: "Checkbox", Preview: CheckboxPreview, group: "primitives" },
  { id: "radio", label: "Radio", Preview: RadioPreview, group: "primitives" },
  { id: "sidebar", label: "Sidebar / 会话", Preview: SidebarPreview, group: "composites" },
  { id: "form-field", label: "Form field", Preview: FormFieldPreview, group: "composites" },
  { id: "dashed-zone", label: "Dashed zone", Preview: DashedZonePreview, group: "composites" },
  { id: "item", label: "Item", Preview: ItemPreview, group: "composites" },
];

const groups = [
  { id: "ai-app", label: "AI APP", items: examples.filter((item) => item.group === "ai-app") },
  { id: "design", label: "设计规范", items: examples.filter((item) => item.group === "design") },
  { id: "nodes", label: "节点组件", items: examples.filter((item) => item.group === "nodes") },
  { id: "primitives", label: "基础组件", items: examples.filter((item) => item.group === "primitives") },
  { id: "composites", label: "复合组件", items: examples.filter((item) => item.group === "composites") },
  { id: "layouts", label: "布局", items: examples.filter((item) => item.group === "layouts") },
];

function subscribeToHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

function getSelectedExample() {
  const id = window.location.hash.slice(1);
  if (["underline-tabs", "pill-tabs", "filter-tabs"].includes(id)) return "tabs";
  if (["resource-card", "info-card", "card-layout"].includes(id)) return "card";
  if (["glass-icon-button", "glass-icon-button-group"].includes(id)) return "button";
  return id;
}

export function ComponentsPreview() {
  const [theme, setTheme] = useState(readPreviewTheme);
  function changeTheme(next: PreviewTheme) {
    applyPreviewTheme(next);
    setTheme(next);
  }
  const selectedId = useSyncExternalStore(subscribeToHash, getSelectedExample, () => "button");
  const selected = examples.find((example) => example.id === selectedId) ?? examples.find((example) => example.id === "button")!;
  const Preview = selected.Preview;

  return (
    <div className="components-preview">
      <ScrollArea role="complementary" aria-label="组件导航" className="components-preview-sidebar">
        <h1>Components Preview</h1>
        <div className="components-preview-theme" role="group" aria-label="外观模式">
          <button type="button" aria-pressed={theme === "dark"} onClick={() => changeTheme("dark")}>深色</button>
          <button type="button" aria-pressed={theme === "light"} onClick={() => changeTheme("light")}>浅色</button>
        </div>
        <nav aria-label="组件分组">
          {groups.map((group) => (
            <section key={group.id} aria-labelledby={`group-${group.id}`}>
              <h2 id={`group-${group.id}`}>{group.label}</h2>
              {group.items.map((item) => (
                <a
                  key={item.id}
                  className="components-preview-item"
                  href={`#${item.id}`}
                  aria-current={selected.id === item.id ? "page" : undefined}
                >
                  {item.label}
                </a>
              ))}
            </section>
          ))}
        </nav>
      </ScrollArea>
      <ScrollArea role="main" className="components-preview-canvas" aria-label={`${selected.label}预览`}>
        <Preview key={selected.id} />
      </ScrollArea>
    </div>
  );
}
