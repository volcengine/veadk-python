import { ComponentApi } from "../api/ComponentApi";
import { useState } from "react";
import { UnderlineTabs } from "../../components/primitives/UnderlineTabs";
import "./UnderlineTabsPreview.css";

const items = [
  { value: "overview", label: "OverView" },
  { value: "configuration", label: "Configuration" },
  { value: "integration", label: "Integration" },
  { value: "evaluation", label: "Evaluation" },
  { value: "versions", label: "Versions" },
].map((item) => ({
  ...item,
  id: `underline-preview-tab-${item.value}`,
  panelId: `underline-preview-panel-${item.value}`,
}));

export function UnderlineTabsPreview() {
  const [value, setValue] = useState("configuration");
  return (
    <section aria-labelledby="underline-tabs-preview-title">
      <h2 id="underline-tabs-preview-title" className="component-preview-title">Tab with underline</h2>
      <div className="underline-tabs-preview-scroll">
        <UnderlineTabs
          items={items}
          value={value}
          onValueChange={setValue}
          aria-label="Agent sections"
          className="underline-tabs-preview-example"
        />
      </div>
      {items.map((item) => (
        <div key={item.value} role="tabpanel" id={item.panelId} aria-labelledby={item.id} hidden={value !== item.value} />
      ))}
      <h3 className="underline-tabs-preview-overflow-title">多选项横向滚动</h3>
      <div style={{ width: 360, maxWidth: "100%" }}>
        <UnderlineTabs items={[...items.map(({ value, label }) => ({ value, label })),
          { value: "logs", label: "Logs" }, { value: "metrics", label: "Metrics" },
          { value: "permissions", label: "Permissions" }, { value: "settings", label: "Settings" }
        ]} aria-label="Scrollable agent sections" />
      </div>
    <ComponentApi names={["UnderlineTabs"]} />
    </section>
  );
}
