import { ComponentApi } from "../api/ComponentApi";
import { Dropdown } from "../../components/primitives/Dropdown";

export function DropdownPreview() {
  return <section aria-labelledby="dropdown-preview-title">
    <h2 id="dropdown-preview-title" className="component-preview-title">Dropdown</h2>
    <Dropdown label="Execution 8steps 7.2s">
      <div style={{ height: 80 }} />
    </Dropdown>
  <ComponentApi names={["Dropdown"]} />
    </section>;
}
