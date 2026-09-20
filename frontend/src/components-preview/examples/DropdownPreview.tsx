import { Dropdown } from "../../components/primitives/Dropdown";

export function DropdownPreview() {
  return <section aria-labelledby="dropdown-preview-title">
    <h2 data-preview-heading tabIndex={-1} id="dropdown-preview-title" className="component-preview-title">Default</h2>
    <Dropdown label="Execution 8steps 7.2s">
      <div style={{ height: 80 }} />
    </Dropdown>
    <h2 data-preview-heading tabIndex={-1} className="component-preview-title">Full width</h2>
    <Dropdown label="任务完成度" fullWidth>
      <p>根据任务要求和实际执行证据评估完成情况</p>
    </Dropdown>
    </section>;
}
