import { Dropdown } from "../../components/primitives/Dropdown";
import { Divider } from "../../components/primitives/Divider";

export function DropdownPreview() {
  return <section aria-labelledby="dropdown-preview-title">
    <h2 id="dropdown-preview-title" className="component-preview-title">Dropdown</h2>
    <Dropdown label="Execution 8steps 7.2s">
      <div style={{ height: 80 }} />
    </Dropdown>
    <Divider />
  </section>;
}
