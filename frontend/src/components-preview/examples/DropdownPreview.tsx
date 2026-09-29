import { Dropdown } from "../../components/primitives/Dropdown";

export function DropdownPreview() {
  return <section aria-labelledby="dropdown-preview-title">
    <h2 data-preview-heading tabIndex={-1} id="dropdown-preview-title" className="component-preview-title">Default</h2>
    <Dropdown label="Execution 8steps 7.2s">
      <div style={{ height: 80 }} />
    </Dropdown>
    </section>;
}
