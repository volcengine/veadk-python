import { Switch } from "../../components/primitives/Switch";
import "./SwitchPreview.css";

export function SwitchPreview() {
  return (
    <section aria-labelledby="switch-preview-title">
      <h2 data-preview-heading tabIndex={-1} id="switch-preview-title" className="component-preview-title">Default</h2>
      <div className="switch-preview-example"><Switch label="Short-term memory" defaultChecked /></div>
    </section>
  );
}
