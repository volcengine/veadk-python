import { useState, useSyncExternalStore } from "react";
import { ButtonsPreview, CardsPreview, TabsPreview, InputWithTailIconPreview, ItemPreview, LabelPreview, SidebarPreview, SwitchPreview, CheckboxPreview, FormFieldPreview, DashedZonePreview, CodeBlockPreview, ModalLayoutPreview, HeaderPreview, PillTagPreview, FormLabelPreview, ResourcePageLayoutPreview, DetailPageLayoutPreview, TextareaPreview, SelectPreview, BasicNodePreview, AgentNodePreview, CanvasBackgroundPreview, TokensPreview } from "./examples";
import { applyPreviewTheme, readPreviewTheme, type PreviewTheme } from "./theme";
import "./components-preview.css";

const examples = [
  { id: "tokens", label: "Tokens", Preview: TokensPreview, group: "design" },
  { id: "canvas-background", label: "画布背景", Preview: CanvasBackgroundPreview, group: "nodes" },
  { id: "agent-node", label: "Agent 节点", Preview: AgentNodePreview, group: "nodes" },
  { id: "basic-node", label: "普通节点", Preview: BasicNodePreview, group: "nodes" },
  { id: "select", label: "Select", Preview: SelectPreview, group: "primitives" },
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
  { id: "label", label: "Label", Preview: LabelPreview, group: "primitives" },
  { id: "switch", label: "Switch", Preview: SwitchPreview, group: "primitives" },
  { id: "checkbox", label: "Checkbox", Preview: CheckboxPreview, group: "primitives" },
  { id: "sidebar", label: "Sidebar", Preview: SidebarPreview, group: "composites" },
  { id: "form-field", label: "Form field", Preview: FormFieldPreview, group: "composites" },
  { id: "dashed-zone", label: "Dashed zone", Preview: DashedZonePreview, group: "composites" },
  { id: "item", label: "Item", Preview: ItemPreview, group: "composites" },
];

const groups = [
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
      <aside className="components-preview-sidebar">
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
      </aside>
      <main className="components-preview-canvas" aria-label={`${selected.label}预览`}>
        <Preview key={selected.id} />
      </main>
    </div>
  );
}
