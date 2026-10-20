import { useState } from "react";
import { FilterTabs } from "../../components/primitives/FilterTabs";
import "./FilterTabsPreview.css";

export function FilterTabsPreview() {
  const [value, setValue] = useState("all");
  return (
    <section aria-labelledby="filter-tabs-preview-title">
      <h2 data-preview-heading tabIndex={-1} id="filter-tabs-preview-title" className="component-preview-title">Filter</h2>
      <FilterTabs className="filter-tabs-preview-example" aria-label="Resource ownership" value={value} onValueChange={setValue}
        options={[{value: "all", label: "All"}, {value: "mine", label: "Created by me"}]} />
    </section>
  );
}
