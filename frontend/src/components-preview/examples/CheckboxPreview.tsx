import { Checkbox } from "../../components/primitives/Checkbox";
import "./CheckboxPreview.css";

export function CheckboxPreview() {
  return (
    <section aria-labelledby="checkbox-preview-title">
      <h2 data-preview-heading tabIndex={-1} id="checkbox-preview-title" className="component-preview-title">Default</h2>
      <Checkbox className="checkbox-preview-example" label="Parallel web search" />
    </section>
  );
}
