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
import { ToastPreview, ToastHookApi } from "./examples/ToastPreview";
import { TablePreview } from "./examples/TablePreview";
import { RadioPreview } from "./examples/RadioPreview";
import { InputPreview } from "./examples/InputPreview";
import { LoadMoreAreaPreview } from "./examples/LoadMoreAreaPreview";
import { ScrollArea } from "../components/primitives/ScrollArea";
import { ScrollAreaPreview } from "./examples/ScrollAreaPreview";
import { DividerPreview } from "./examples/DividerPreview";
import { DropdownPreview } from "./examples/DropdownPreview";
import { MenuPreview, MenuEntryApi } from "./examples/MenuPreview";
import { PromptInputPreview } from "./examples/PromptInputPreview";
import { ConversationFlowPreview } from "./examples/ConversationFlowPreview";
import { memo, useEffect, useRef, useState, useSyncExternalStore, type ComponentType } from "react";
import { ComponentApi } from "./api/ComponentApi";
import { PreviewContents } from "./PreviewContents";
import { resolvePreviewLocation } from "./navigation";
import { ButtonsPreview, CardsPreview, TabsPreview, ItemPreview, LabelPreview, SidebarPreview, SwitchPreview, CheckboxPreview, FormFieldPreview, DashedZonePreview, CodeBlockPreview, ModalLayoutPreview, HeaderPreview, PillTagPreview, FormLabelPreview, ResourcePageLayoutPreview, DetailPageLayoutPreview, TextareaPreview, SelectPreview, BasicNodePreview, AgentNodePreview, CanvasBackgroundPreview, TokensPreview } from "./examples";
import { useStudioTheme } from "../components/tokens/theme";
import { AppLayoutPreview } from "./examples/AppLayoutPreview";
import { FormLabelRowPreview } from "./examples/FormLabelRowPreview";
import { GlassIconButtonGroupPreview } from "./examples/GlassIconButtonGroupPreview";
import { CardLayoutPreview } from "./examples/CardLayoutPreview";
import { SpecificationPreview } from "./foundation/SpecificationPreview";
import "./components-preview.css";

type PreviewDefinition = {
  id: string;
  label: string;
  Preview: ComponentType;
  group: string;
  apiNames: readonly string[];
  ApiDetails?: ComponentType;
};

const examples: PreviewDefinition[] = [
  { id: "app-layout", label: "App Layout", Preview: AppLayoutPreview, group: "layout", apiNames: ["AppLayout"] },
  { id: "date-picker", label: "Date Picker", Preview: DatePickerPreview, group: "base", apiNames: ["DatePicker"] },
  { id: "index-layout", label: "Index Layout", Preview: IndexLayoutPreview, group: "layout", apiNames: ["IndexLayout"] },
  { id: "slider", label: "Slider", Preview: SliderPreview, group: "base", apiNames: ["Slider"] },
  { id: "file-upload", label: "File Upload", Preview: FileUploadPreview, group: "block", apiNames: ["FileUpload"] },
  { id: "modal-button", label: "Modal Button", Preview: ModalButtonPreview, group: "block", apiNames: ["ModalButton"] },
  { id: "drawer", label: "Drawer", Preview: DrawerPreview, group: "block", apiNames: ["Drawer"] },
  { id: "file-explorer", label: "File Explorer", Preview: FileExplorerPreview, group: "block", apiNames: ["FileExplorer"] },
  { id: "long-running-state", label: "Progress", Preview: LongRunningStatePreview, group: "block", apiNames: ["LongRunningState"] },
  { id: "empty-state", label: "Empty State", Preview: EmptyStatePreview, group: "base", apiNames: ["EmptyState"] },
  { id: "error-state", label: "Error State", Preview: ErrorStatePreview, group: "base", apiNames: ["ErrorState"] },
  { id: "loading", label: "Loading", Preview: LoadingPreview, group: "base", apiNames: ["Loading"] },
  { id: "toast", label: "Toast", Preview: ToastPreview, group: "base", apiNames: ["Toast", "ToastProvider"], ApiDetails: ToastHookApi },
  { id: "table", label: "Table", Preview: TablePreview, group: "base", apiNames: ["Table", "TableCellText", "TableStatus"] },
  { id: "load-more", label: "Load More", Preview: LoadMoreAreaPreview, group: "block", apiNames: ["LoadMoreArea"] },
  { id: "scroll-area", label: "Scroll Area", Preview: ScrollAreaPreview, group: "base", apiNames: ["ScrollArea"] },
  { id: "divider", label: "Divider", Preview: DividerPreview, group: "base", apiNames: ["Divider"] },
  { id: "dropdown", label: "Dropdown", Preview: DropdownPreview, group: "base", apiNames: ["Dropdown"] },
  { id: "prompt-input", label: "Prompt Input", Preview: PromptInputPreview, group: "ai-app", apiNames: ["PromptInput", "SingleLinePromptInput"] },
  { id: "conversation-flow", label: "Conversation Flow", Preview: ConversationFlowPreview, group: "ai-app", apiNames: ["ConversationFlow", "ConversationMarkdown", "ConversationVisualization", "ConversationSurface"] },
  { id: "tokens", label: "Tokens", Preview: TokensPreview, group: "foundation", apiNames: [] },
  { id: "specification", label: "Specification", Preview: SpecificationPreview, group: "foundation", apiNames: [] },
  { id: "canvas-background", label: "Canvas Background", Preview: CanvasBackgroundPreview, group: "node", apiNames: ["CanvasBackground"] },
  { id: "agent-node", label: "Agent Node", Preview: AgentNodePreview, group: "node", apiNames: ["AgentNode"] },
  { id: "basic-node", label: "Basic Node", Preview: BasicNodePreview, group: "node", apiNames: ["BasicNode"] },
  { id: "select", label: "Select", Preview: SelectPreview, group: "base", apiNames: ["Select"] },
  { id: "menu", label: "Menu", Preview: MenuPreview, group: "base", apiNames: ["Menu"], ApiDetails: MenuEntryApi },
  { id: "textarea", label: "Textarea", Preview: TextareaPreview, group: "base", apiNames: ["Textarea"] },
  { id: "detail-page-layout", label: "Detail Page", Preview: DetailPageLayoutPreview, group: "layout", apiNames: ["DetailPageLayout"] },
  { id: "form-label", label: "Form Label", Preview: FormLabelPreview, group: "base", apiNames: ["FormLabel"] },
  { id: "form-label-row", label: "Form Label Row", Preview: FormLabelRowPreview, group: "block", apiNames: ["FormLabelRow"] },
  { id: "resource-page-layout", label: "Resource Page", Preview: ResourcePageLayoutPreview, group: "layout", apiNames: ["ResourcePageLayout"] },
  { id: "pill-tag", label: "Pill Tag", Preview: PillTagPreview, group: "base", apiNames: ["PillTag"] },
  { id: "card", label: "Card", Preview: CardsPreview, group: "block", apiNames: ["ResourceCard", "InfoCard", "InfoCardTitle", "InfoCardBody", "PromoCard"] },
  { id: "card-layout", label: "Card Layout", Preview: CardLayoutPreview, group: "layout", apiNames: ["CardLayout"] },
  { id: "header", label: "Header", Preview: HeaderPreview, group: "block", apiNames: ["Header"] },
  { id: "modal-layout", label: "Modal Layout", Preview: ModalLayoutPreview, group: "layout", apiNames: ["ModalLayout"] },
  { id: "code-block", label: "Code Block", Preview: CodeBlockPreview, group: "block", apiNames: ["CodeBlock"] },
  { id: "button", label: "Button", Preview: ButtonsPreview, group: "base", apiNames: ["Button", "GlassIconButton"] },
  { id: "glass-icon-button-group", label: "Glass Icon Button Group", Preview: GlassIconButtonGroupPreview, group: "block", apiNames: ["GlassIconButtonGroup"] },
  { id: "tabs", label: "Tabs", Preview: TabsPreview, group: "base", apiNames: ["UnderlineTabs", "PillTabs", "FilterTabs", "GlassTabs"] },
  { id: "input", label: "Input", Preview: InputPreview, group: "base", apiNames: ["InputWithHeaderIcon", "InputWithTailIcon"] },
  { id: "label", label: "Label", Preview: LabelPreview, group: "base", apiNames: ["Label"] },
  { id: "switch", label: "Switch", Preview: SwitchPreview, group: "base", apiNames: ["Switch"] },
  { id: "checkbox", label: "Checkbox", Preview: CheckboxPreview, group: "base", apiNames: ["Checkbox"] },
  { id: "radio", label: "Radio", Preview: RadioPreview, group: "base", apiNames: ["RadioCard", "Radio"] },
  { id: "sidebar", label: "Sidebar", Preview: SidebarPreview, group: "block", apiNames: ["Sidebar", "SidebarAccount", "SidebarGroupTitle", "SidebarItem", "SidebarItemWithIcon"] },
  { id: "form-field", label: "Form Field", Preview: FormFieldPreview, group: "block", apiNames: ["FormField"] },
  { id: "dashed-zone", label: "Dashed Zone", Preview: DashedZonePreview, group: "block", apiNames: ["DashedZone"] },
  { id: "item", label: "Item", Preview: ItemPreview, group: "block", apiNames: ["Item"] },
];

const groups = [
  { id: "foundation", label: "Foundation" },
  { id: "base", label: "Base" },
  { id: "block", label: "Block" },
  { id: "ai-app", label: "AI App" },
  { id: "node", label: "Node" },
  { id: "layout", label: "Layout" },
].map(group => ({
  ...group,
  items: examples.filter(item => item.group === group.id).sort((a, b) => a.label.localeCompare(b.label, "en")),
}));

function subscribeToHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

const getHash = () => window.location.hash;

const PreviewBody = memo(function PreviewBody({ example }: { example: PreviewDefinition }) {
  const { Preview, ApiDetails } = example;
  return <>
    <div className="components-preview-examples"><Preview /></div>
    {example.apiNames.length > 0 && <section className="components-preview-api" aria-labelledby="component-api-title">
      <h2 id="component-api-title" data-preview-heading>参数与属性</h2>
      <ComponentApi names={example.apiNames} />
      {ApiDetails && <ApiDetails />}
    </section>}
  </>;
});

export function ComponentsPreview() {
  const [theme, changeTheme] = useStudioTheme();
  const [navigationOpen, setNavigationOpen] = useState(false);
  const hash = useSyncExternalStore(subscribeToHash, getHash, () => "#button");
  const location = resolvePreviewLocation(hash);
  const selected = examples.find(example => example.id === location.component) ?? examples.find(example => example.id === "button")!;
  const scrollRef = useRef<HTMLDivElement>(null);
  const fullscreen = new URLSearchParams(window.location.search).get("fullscreen") === "app-layout";

  useEffect(() => {
    document.title = `${selected.label} | AgentKit Studio Components`;
  }, [selected.label]);

  if (fullscreen) return <AppLayoutPreview fullscreen />;

  return (
    <div className="components-preview">
      <ScrollArea role="complementary" aria-label="组件导航" className="components-preview-sidebar" data-navigation-open={navigationOpen}>
        <div className="components-preview-brand">
          <p>Components Preview</p>
          <button type="button" className="components-preview-navigation-toggle" aria-expanded={navigationOpen} aria-controls="components-navigation" onClick={() => setNavigationOpen(open => !open)}>
            组件目录
            <svg viewBox="0 0 16 16" width="16" height="16" fill="none" aria-hidden="true"><path d="m4 6 4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
        </div>
        <div id="components-navigation" className="components-preview-navigation">
          <div className="components-preview-theme" role="group" aria-label="外观模式">
            <button type="button" aria-pressed={theme === "dark"} onClick={() => changeTheme("dark")}>深色</button>
            <button type="button" aria-pressed={theme === "light"} onClick={() => changeTheme("light")}>浅色</button>
          </div>
          <nav aria-label="组件分组">
            {groups.map(group => (
              <section key={group.id} aria-labelledby={`group-${group.id}`}>
                <p className="components-preview-group-label" id={`group-${group.id}`}>{group.label}</p>
                {group.items.map(item => (
                  <a key={item.id} className="components-preview-item" href={`#${item.id}`} aria-current={selected.id === item.id ? "page" : undefined} onClick={() => setNavigationOpen(false)}>
                    {item.label}
                  </a>
                ))}
              </section>
            ))}
          </nav>
        </div>
      </ScrollArea>
      <div className="components-preview-page">
        <PreviewContents scrollRef={scrollRef} componentId={selected.id} sectionId={location.section} />
        <ScrollArea ref={scrollRef} role="main" className="components-preview-canvas" aria-labelledby="component-page-title">
          <h1 id="component-page-title" className="components-preview-page-title">{selected.label}</h1>
          <PreviewBody key={selected.id} example={selected} />
        </ScrollArea>
      </div>
    </div>
  );
}
