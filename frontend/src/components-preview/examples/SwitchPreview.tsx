import { Switch } from "../../components/primitives/Switch";
import "./SwitchPreview.css";

export function SwitchPreview() {
  return (
    <section aria-labelledby="switch-preview-title">
      <h2 id="switch-preview-title" className="component-preview-title">Switch</h2>
      <div className="switch-preview-example"><Switch label="Short-term memory" defaultChecked /></div>
    </section>
  );
}
