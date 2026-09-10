import { UnderlineTabsPreview } from "./UnderlineTabsPreview";
import { PillTabsPreview } from "./PillTabsPreview";
import { FilterTabsPreview } from "./FilterTabsPreview";

export function TabsPreview() {
  return <div style={{ display: "grid", gap: 40, minWidth: 0 }}>
    <UnderlineTabsPreview />
    <PillTabsPreview />
    <FilterTabsPreview />
  </div>;
}
